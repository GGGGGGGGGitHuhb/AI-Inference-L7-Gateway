"""固定 seed/配比的显式模拟稳定性；正文严格 hash 比对。"""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import random
import socket
import socketserver
import threading
import time
from Support import (Host, Sampler, append, check, exchange, gateway_config,
                     request_body, reset_client, save, sha, validate_rss, install_interrupt_handlers, source_identity, recorded_exchange)

SAMPLE_LOCK = threading.Lock()

PATTERN = b'data: abcdef0123456789\n\n'
BODIES = {'fast': PATTERN * 1024, 'slow': PATTERN * 190000,
          'nonstream': b'{"synthetic":"complete"}', 'cancel': PATTERN * 190000,
          'bad': PATTERN * 32, 'truncated': PATTERN * 32}


class BackendHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(15)
        try:
            request_line = self.rfile.readline(8192)
            if not request_line:
                return
            headers = {}
            while True:
                line = self.rfile.readline(8192)
                if line == b'\r\n':
                    break
                check(line and b':' in line, 'synthetic request headers')
                key, value = line.split(b':', 1)
                headers[key.lower()] = value.strip()
            size = int(headers[b'content-length'])
            check(size <= 65536, 'synthetic request size')
            value = json.loads(self.rfile.read(size))
            kind = value['messages'][0]['content']
            with self.server.count_lock:
                self.server.requests += 1
            body = BODIES[kind]
            if kind == 'nonstream':
                self.connection.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: '
                                        + str(len(body)).encode() + b'\r\n\r\n' + body)
                return
            self.connection.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n')
            for offset in range(0, len(body), 16384):
                part = body[offset:offset + 16384]
                self.connection.sendall(f'{len(part):x}\r\n'.encode() + part + b'\r\n')
            if kind in ('bad', 'truncated'):
                time.sleep(.1)
                if kind == 'bad':
                    self.connection.sendall(b'NOTHEX\r\n')
            else:
                self.connection.sendall(b'0\r\n\r\n')
        except (BrokenPipeError, ConnectionResetError):
            # 取消请求的预期上游关闭；正常请求由客户端完整性断言兜底。
            pass
        except BaseException as error:
            with self.server.count_lock:
                self.server.errors.append(repr(error))


class SyntheticBackend(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = False

    def __init__(self):
        super().__init__(('127.0.0.1', 0), BackendHandler)
        self.requests = 0
        self.errors = []
        self.count_lock = threading.Lock()
        self.thread = threading.Thread(target=self.serve_forever)
        self.thread.start()

    def stop(self):
        self.shutdown()
        self.server_close()
        self.thread.join(5)


def run_sample(port, index, kind, sample_path=None):
    request = request_body(kind != 'nonstream')
    request['messages'][0]['content'] = kind
    return recorded_exchange(port, request, sample_path, {'index': index, 'kind': kind},
                             lock=SAMPLE_LOCK, validator=validate_sample,
                             slow=kind == 'slow', synthetic=True,
                             on_content=reset_client if kind == 'cancel' else None)


def validate_sample(result):
    kind = result['kind']
    check(result['status'] == 200, 'synthetic committed 200')
    if kind == 'cancel':
        check(result.get('cancelled') and not result['complete'], 'planned cancel')
    elif kind in ('bad', 'truncated'):
        check(not result['complete'] and result['error'], 'planned truncated response')
        check(result['body_sha256'] == hashlib.sha256(BODIES[kind]).hexdigest(), 'fault prefix exact')
    else:
        check(result['complete'] and not result['error'], 'synthetic normal completion')
        check(result['body_sha256'] == hashlib.sha256(BODIES[kind]).hexdigest(), 'synthetic full bytes exact')


def run(args):
    output = pathlib.Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    save(output / 'manifest.json', {'minimum_seconds': 300, 'minimum_requests': 300,
          'guard_seconds': 900, 'concurrency': 4, 'seed': 20261019,
          'source_sha256': source_identity(), 'calibration': args.calibration, 'host_sha256': sha(args.host),
          'bodies': {key: {'size': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
                     for key, value in BODIES.items()}})
    backend = SyntheticBackend()
    host = sampler = None
    try:
        host = Host(args.host, gateway_config(backend.server_address[1], False), output)
        sampler = Sampler(host, None, output / 'resources.jsonl')
        # 未支持字段必须在网关拒绝，不能让请求到达后端。
        unsupported = request_body(False); unsupported['seed'] = 1
        before = backend.requests
        rejected = recorded_exchange(host.port, unsupported, output / 'negative-request.jsonl',
                                     {'label': 'unsupported-field'})
        check(rejected['status'] == 400 and rejected['complete'] and backend.requests == before,
              'unsupported fields rejected before backend')
        for index, kind in enumerate(('fast', 'slow', 'nonstream', 'cancel', 'bad')):
            result = run_sample(host.port, index, kind, output / 'warmup.jsonl')
            validate_sample(result)
        baseline = host.drain()
        start = time.monotonic()
        count = 0
        drains = []
        kinds = ['fast'] * 4 + ['slow'] * 2 + ['nonstream'] * 2 + ['cancel', 'bad']
        rng = random.Random(20261019)
        next_progress = start + 60
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            while (count < (50 if args.calibration else 300) or
                   (not args.calibration and time.monotonic() - start < 300)):
                check(time.monotonic() - start < 900, 'synthetic 900s guard')
                batch = []
                for block in range(5):
                    ordered = list(kinds)
                    ordered[-1] = 'bad' if (count // 10 + block) % 2 == 0 else 'truncated'
                    rng.shuffle(ordered)
                    batch.extend(ordered)
                # 每批最多四个真实在途请求；完成后补位，不积压网关队列。
                pending = {}
                cursor = 0
                while cursor < 50 or pending:
                    while cursor < 50 and len(pending) < 4:
                        future = executor.submit(run_sample, host.port, count + cursor, batch[cursor],
                                                 output / 'synthetic-soak.jsonl')
                        pending[future] = batch[cursor]
                        cursor += 1
                    completed, _ = concurrent.futures.wait(pending, timeout=.1,
                                      return_when=concurrent.futures.FIRST_COMPLETED)
                    host.refresh()
                    for future in completed:
                        result = future.result()
                        validate_sample(result)
                        del pending[future]
                    if completed:
                        completed_at = time.monotonic()
                        retirement_deadline = completed_at + 5
                        while True:
                            snapshot = host.refresh()
                            if snapshot['monotonic'] > completed_at and snapshot['sessions'] <= len(pending):
                                append(output / 'retirement-gates.jsonl',
                                       {'after': completed_at, 'pending_clients': len(pending),
                                        'snapshot': snapshot})
                                break
                            check(time.monotonic() < retirement_deadline, 'completed sessions retirement')
                            time.sleep(.01)
                    if time.monotonic() >= next_progress:
                        print('synthetic-soak', round(time.monotonic()-start, 1),
                              'seconds', count + cursor-len(pending), 'complete',
                              'snapshot', host.latest, flush=True)
                        next_progress += 60
                count += 50
                drains.append(host.drain())
                check(drains[-1]['rss'] <= baseline['rss'] + 32 * 1024**2, 'RSS fixed bound')
        if not args.calibration:
            validate_rss(baseline['rss'], drains)
        check(host.maxima.get('pauses', 0) > 0 and host.maxima.get('resumes', 0) > 0,
              'real synthetic high-water pause and resume')
        check(not backend.errors, f'backend unexpected errors {backend.errors}')
        save(output / 'summary.json', {'status': 'CALIBRATION_PASS' if args.calibration else 'PASS',
             'seconds': time.monotonic()-start, 'count': count, 'expected_success': count*8//10,
             'expected_cancel': count//10, 'expected_fault': count//10, 'unexpected_failures': 0,
             'baseline': baseline, 'last_five': drains[-5:], 'maxima': host.maxima})
    except BaseException as error:
        save(output / 'result.json', {'status': 'FAIL', 'error': repr(error)})
        raise
    finally:
        try:
            if sampler: sampler.stop()
        finally:
            try:
                if host: host.stop()
            finally:
                backend.stop()
        check(sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) < 128 * 1024**2,
              'run evidence limit')


def main():
    install_interrupt_handlers()
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--calibration', action='store_true')
    run(parser.parse_args())


if __name__ == '__main__':
    main()
