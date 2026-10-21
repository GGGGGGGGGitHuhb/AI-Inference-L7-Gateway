"""Bounded admission probes; --mixed performs the fixed 24-request observation once."""
import concurrent.futures
import http.client
import http.server
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time

HOST = sys.argv[1]
checks = 0


def check(condition, detail=''):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(detail)


def wait_for(predicate, timeout=4):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(.005)
    raise AssertionError('state gate timeout')


class Backend(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(('127.0.0.1', 0), Handler)
        self.gate = threading.Event()
        self.gate.set()
        self.started = threading.Event()
        self.count = 0
        self.worker = threading.Thread(target=self.serve_forever, daemon=True)
        self.worker.start()

    def close(self):
        self.gate.set()
        self.shutdown()
        self.server_close()
        self.worker.join(2)
        check(not self.worker.is_alive())


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.count += 1
            self.server.started.set()
            if body.get('stream'):
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                self.wfile.write(b'9\r\ndata: x\n\n\r\n')
                self.wfile.flush()
                check(self.server.gate.wait(12), 'backend gate timeout')
                time.sleep(.2)
                self.wfile.write(b'0\r\n\r\n')
                self.wfile.flush()
            else:
                check(self.server.gate.wait(12), 'backend gate timeout')
                time.sleep(.01)
                payload = b'{"ok":true}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                self.wfile.flush()
        except (OSError, ValueError):
            self.close_connection = True


def configuration(backends):
    return {'listen_port': 0, 'models': [
        {'name': name, 'policy': 'round_robin', 'backends': [
            {'id': str(index), 'address': '127.0.0.1', 'port': backend.server_port}
            for index, backend in enumerate(group)]}
        for name, group in [('a', backends[:2]), ('b', backends[2:])]],
        'max_connections': 64, 'max_reserved_bytes': 1073741824,
        'admission': {'max_inflight': 2, 'max_inflight_per_backend': 1,
                      'max_queue_requests_per_model': 16,
                      'max_queue_bytes_per_model': 4194304, 'queue_timeout_ms': 5000},
        'timeouts_ms': {'total': 10000, 'response': 8000, 'shutdown': 100}}


class Gateway:
    def __init__(self, folder, config):
        self.trace = Path(folder) / 'trace.json'
        self.trace.unlink(missing_ok=True)
        path = Path(folder) / 'config.json'
        path.write_text(json.dumps(config))
        self.process = subprocess.Popen([HOST, str(path), str(self.trace)], stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True)
        self.stop_requested = False
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                check(bool(selector.select(5)), 'host ready timeout')
            self.port = int(self.process.stdout.readline())
        except BaseException:
            self.process.kill()
            self.process.communicate()
            raise

    def state(self):
        if not self.trace.exists():
            return {}
        return json.loads(self.trace.read_text())

    def request_stop(self):
        # The explicit shutdown probe and finally cleanup share one stop owner.
        # A second SIGTERM during runtime destruction can outlive signalfd.
        if not self.stop_requested and self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            self.stop_requested = True

    def close(self):
        self.request_stop()
        try:
            out, err = self.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate()
            raise
        check(self.process.returncode == 0,
              {'returncode': self.process.returncode,
               'stop_requested': self.stop_requested, 'stderr': err[:4096]})
        check('AddressSanitizer' not in err and 'runtime error:' not in err, err)
        state = self.state()
        for key in ('final_queue', 'final_bytes', 'final_inflight', 'final_sessions', 'final_reserved', 'final_timers'):
            check(state[key] == 0, (key, state))
        return state


def connect(port, model='a', stream=False):
    sock = socket.create_connection(('127.0.0.1', port), timeout=12)
    body = json.dumps({'model': model, 'stream': stream,
                       'messages': [{'role': 'user', 'content': 'fixed'}]}).encode()
    sock.sendall(b'POST /v1/chat/completions HTTP/1.1\r\nHost: test\r\nContent-Type: application/json\r\nContent-Length: ' +
                 str(len(body)).encode() + b'\r\n\r\n' + body)
    return sock


def response(sock):
    reply = http.client.HTTPResponse(sock)
    reply.begin()
    payload = reply.read()
    return reply.status, payload


def negative_checks(folder, backends):
    config = configuration(backends)
    config['admission'].update(max_inflight=1, max_queue_requests_per_model=1)
    backends[0].gate.clear()
    gateway = Gateway(folder, config)
    sockets = []
    try:
        active = connect(gateway.port)
        sockets.append(active)
        check(backends[0].started.wait(4))
        queued = connect(gateway.port)
        sockets.append(queued)
        wait_for(lambda: gateway.state().get('final_queue') == 1)
        rejected = connect(gateway.port)
        sockets.append(rejected)
        status, body = response(rejected)
        check(status == 503 and b'queue_full' in body)
        queued.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
        queued.close()
        wait_for(lambda: gateway.state().get('final_queue') == 0)
        half = connect(gateway.port)
        sockets.append(half)
        half.shutdown(socket.SHUT_WR)
        wait_for(lambda: gateway.state().get('final_queue') == 1)
        backends[0].gate.set()
        check(response(active)[0] == 200)
        check(response(half)[0] == 200)
        wait_for(lambda: gateway.state().get('final_inflight') == 0)
    finally:
        backends[0].gate.set()
        for sock in sockets:
            sock.close()
        state = gateway.close()
    check(state['peak_inflight'] == 1 and state['peak_backend'] == 1)
    check(any(row['outcome'] == 'cancelled' for row in state['records']))

    config['admission'].update(queue_timeout_ms=20)
    backends[0].gate.clear()
    backends[0].started.clear()
    gateway = Gateway(folder, config)
    sockets = []
    try:
        active = connect(gateway.port)
        sockets.append(active)
        check(backends[0].started.wait(4))
        queued = connect(gateway.port)
        sockets.append(queued)
        status, body = response(queued)
        check(status == 504 and b'queue_timeout' in body)
        backends[0].gate.set()
        check(response(active)[0] == 200)
    finally:
        backends[0].gate.set()
        for sock in sockets:
            sock.close()
        gateway.close()

    config['admission'].update(queue_timeout_ms=5000)
    backends[0].gate.clear()
    backends[0].started.clear()
    gateway = Gateway(folder, config)
    sockets = []
    try:
        active = connect(gateway.port, stream=True)
        sockets.append(active)
        check(backends[0].started.wait(4))
        queued = connect(gateway.port)
        sockets.append(queued)
        wait_for(lambda: gateway.state().get('final_queue') == 1)
        gateway.request_stop()
        status, body = response(queued)
        check(status == 503 and b'gateway_stopping' in body)
    finally:
        backends[0].gate.set()
        for sock in sockets:
            sock.close()
        gateway.close()


def mixed(folder, backends, output):
    config = configuration(backends)
    gateway = Gateway(folder, config)
    latch = threading.Barrier(25)
    attempts = []
    lock = threading.Lock()
    send_order = threading.Condition()
    next_send = [0]

    def run_one(index):
        model = 'a' if index % 2 == 0 else 'b'
        ordinal = index // 2 + 1
        stream = ordinal in (1, 5, 9)
        latch.wait(timeout=5)
        started = time.monotonic_ns()
        row = {'input_index': index, 'model': model, 'stream': stream, 'started': started}
        sock = None
        try:
            with send_order:
                check(send_order.wait_for(lambda: next_send[0] == index, timeout=10), 'send order timeout')
                try:
                    sock = connect(gateway.port, model, stream)
                finally:
                    next_send[0] += 1
                    send_order.notify_all()
            status, body = response(sock)
            row.update(status=status, bytes=len(body), outcome='success' if status == 200 else 'rejected')
        except BaseException as error:
            row.update(outcome='error', error=repr(error))
        finally:
            if sock:
                sock.close()
            row['finished'] = time.monotonic_ns()
            with lock:
                attempts.append(row)

    started = time.monotonic()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=24) as executor:
            futures = [executor.submit(run_one, index) for index in range(24)]
            latch.wait(timeout=5)
            for future in futures:
                future.result(timeout=30)
    finally:
        close_error = None
        try:
            state = gateway.close()
        except BaseException as error:
            close_error = error
            state = gateway.state()
        artifact = {'config': config, 'client_attempts': attempts, 'trace': state,
                    'host_error': repr(close_error) if close_error else None,
                    'elapsed_seconds': time.monotonic() - started}
        Path(output).write_text(json.dumps(artifact, indent=2))
        if close_error:
            raise close_error
    check(len(attempts) == 24 and all(row.get('status') == 200 for row in attempts), attempts)
    check(artifact['elapsed_seconds'] < 30)
    records = state['records']
    check(len(records) == 24, records)
    check(state['peak_inflight'] <= 2 and state['peak_backend'] <= 1, state)
    check(all(row['count'] <= 16 and row['bytes'] <= 4194304 for row in state['model_peaks']))
    summary = []
    for model in ('a', 'b'):
        queue = [row for row in records if row['model'] == model and row['enqueued']]
        check([row['id'] for row in sorted(queue, key=lambda row: row['enqueued'])] ==
              [row['id'] for row in sorted(queue, key=lambda row: row['dispatched'])], 'actual FIFO')
        for stream in (False, True):
            group = [row for row in records if row['model'] == model and row['stream'] == stream]
            waits = [(row['dispatched'] - row['enqueued']) / 1e6 for row in group if row['enqueued']]
            check(all(row['accepted'] <= row['dispatched'] <= row['upstream_complete'] <= row['finished'] and
                      row['outcome'] == 'complete' for row in group), group)
            summary.append({'model': model, 'stream': stream, 'count': len(group), 'queued': len(waits),
                            'unqueued': len(group) - len(waits), 'median_wait_ms': statistics.median(waits) if waits else None,
                            'max_wait_ms': max(waits) if waits else None, 'completed': len(group),
                            'timeouts': 0, 'rejected': 0, 'cancelled': 0})
    artifact['summary'] = summary
    Path(output).write_text(json.dumps(artifact, indent=2))
    print(json.dumps(summary))


def main():
    backends = [Backend() for _ in range(4)]
    try:
        with tempfile.TemporaryDirectory(prefix='admission-') as folder:
            if '--mixed' in sys.argv:
                mixed(folder, backends, sys.argv[sys.argv.index('--mixed') + 1])
            else:
                negative_checks(folder, backends)
        print('AdmissionE2E checks:', checks)
    finally:
        for backend in backends:
            backend.close()


if __name__ == '__main__':
    main()
