"""Offline, local-loopback negative controls; never requires the model."""
import concurrent.futures
import os
import pathlib
import signal
import socketserver
import tempfile
import json
import socket
import subprocess
import sys
import threading
import time
from Client import attempt, PAYLOADS, request_bytes
from Summarize import distribution


def serve(parts):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    def run():
        try:
            connection, _ = listener.accept()
            with connection:
                connection.recv(8192)
                for delay, body in parts:
                    time.sleep(delay)
                    if body:
                        connection.sendall(body)
        except OSError:
            pass
        finally:
            listener.close()
    thread = threading.Thread(target=run)
    thread.start()
    return port, thread


def probe(parts, stream=False, group='A', timeout=1, validator=None):
    port, thread = serve(parts)
    try:
        return attempt(port, request_bytes(stream), {'attempt_id': 'probe'}, group, stream, timeout, validator=validator)
    finally:
        thread.join(2)
        assert not thread.is_alive()


def cancel_child():
    from Measure import batch, request_cancel
    port, output, processes = int(sys.argv[2]), pathlib.Path(sys.argv[3]), int(sys.argv[4])
    output.mkdir()
    signal.signal(signal.SIGTERM, lambda *_: request_cancel())
    cell = {'id': 'cancel', 'group': 'A', 'phase': 'formal', 'repeat': 0,
            'concurrency': 16, 'stream': False, 'timeout': 2, 'guard': 10,
            'started_audit': str(output / 'started.jsonl')}
    result = batch(port, cell, 128, output, {}, processes)
    print(json.dumps(result))
    return 1 if result['cancel_requested'] and result['not_started'] else 0


def cancel_controls(output):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.recv(8192)
            time.sleep(.2)
            self.request.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 1024\r\n\r\n' + PAYLOADS['A'])
    class Server(socketserver.ThreadingTCPServer):
        daemon_threads = True
    server = Server(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        for processes in (1, 2):
            path = output / f'cancel-{processes}'
            child = subprocess.Popen([sys.executable, __file__, '--cancel-child',
                str(server.server_address[1]), str(path), str(processes)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                deadline = time.monotonic() + 10
                while not (path / 'started.jsonl').exists():
                    assert child.poll() is None and time.monotonic() < deadline
                    time.sleep(.01)
                time.sleep(.05)
                os.kill(child.pid, signal.SIGTERM)
                stdout, stderr = child.communicate(timeout=15)
                (output / f'cancel-{processes}.log').write_text(stdout + stderr)
                started = [json.loads(line) for line in (path / 'started.jsonl').read_text().splitlines()]
                saved = [json.loads(line) for line in (path / 'attempts.jsonl').read_text().splitlines()]
                cell = json.loads((path / 'cell.json').read_text())
                assert child.returncode == 1 and 0 < len(saved) < 128, (child.returncode, stdout, stderr)
                assert len({r['attempt_id'] for r in saved}) == len(saved)
                assert {r['attempt_id'] for r in started} == {r['attempt_id'] for r in saved}
                assert len(saved) + len(cell['not_started']) == 128
                assert all(r['success'] for r in saved)
                assert len(cell['child_processes']) == (2 if processes == 2 else 0)
                for item in cell['child_processes']:
                    assert item['exit_code'] == 0 and not item['alive']
                    assert not pathlib.Path('/proc', str(item['pid'])).exists()
                print(json.dumps({'SIGTERM_processes': processes, 'exit': child.returncode,
                    'started': len(started), 'saved': len(saved), 'not_started': len(cell['not_started']),
                    'child_processes': cell['child_processes']}))
            finally:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(5)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main(output=None):
    if len(sys.argv) > 1 and sys.argv[1] == '--negative':
        row = probe([(0, b'bad\r\n\r\n')])
        print(json.dumps(row))
        return 1 if not row['success'] else 0
    head = b'HTTP/1.1 200 OK\r\nContent-Length: 1024\r\n\r\n'
    row = probe([(0, head + PAYLOADS['A']), (.2, b'')])
    print(json.dumps({'control': 'CL-delayed-EOF', 'attempt': row}))
    assert row['success'], row
    assert row['t_eof']-row['t_http'] > 150_000_000
    assert row['t_http']-row['t0'] < 150_000_000
    assert row['t0'] <= row['t_connect'] <= row['t_send'] <= row['t_first_wire'] <= row['t_head'] <= row['t_http'] <= row['t_eof'] <= row['t_validated'] <= row['t_closed']
    role = b'data: {"choices":[{"delta":{"role":"assistant"},"finish_reason":null}]}\n\n'
    content = b'data: {"choices":[{"delta":{"content":"x"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    sse_head = b'HTTP/1.1 200 OK\r\nContent-Length: ' + str(len(role)+len(content)).encode() + b'\r\n\r\n'
    row = probe([(0, sse_head+role), (.1, content)], True, 'R1')
    print(json.dumps({'control': 'role-content-delay', 'attempt': row}))
    assert row['success'] and row['t_content']-row['t_body'] > 75_000_000, row
    chunk = b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n400\r\n' + PAYLOADS['A'] + b'\r\n'
    row = probe([(0, chunk+b'0\r\n\r\n'), (.2, b'')])
    print(json.dumps({'control': 'chunked-delayed-EOF', 'attempt': row}))
    assert row['success'] and row['t_eof']-row['t_http'] > 150_000_000, row
    failures = []
    for wire in [head + b'x'*1024, chunk, chunk+b'0\r\n\r\n0\r\n\r\n']:
        failures.append(probe([(0, wire)]))
    failures.append(probe([(.2, b'')], timeout=.05))
    failures.append(probe([(0, head+PAYLOADS['A'])], validator=lambda _: (_ for _ in ()).throw(AssertionError('validation'))))
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]
        failures.append(attempt(port, request_bytes(False), {}, 'A', False, .1))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(probe, [(delay, b'bad\r\n\r\n')]) for delay in (.01, .02, .03, .04)]
        failures.extend(f.result() for f in futures)
    assert len(failures) == 10 and all(not r['success'] and r['error'] and r['t_closed'] for r in failures)
    assert distribution([], [50, 99]) == {'n': 0, 'p50': None, 'p99': None, 'max': None}
    from RunBaseline import schedule
    cells = schedule()
    assert len(cells) == 69
    assert sum(c['count'] for c in cells if c['group'].startswith('R')) == 720
    child = subprocess.run([sys.executable, __file__, '--negative'], capture_output=True, text=True, timeout=5)
    assert child.returncode == 1 and json.loads(child.stdout)['error']
    print(json.dumps({'negative_exit': child.returncode, 'attempt': json.loads(child.stdout)}))
    print(json.dumps({'failures': failures}))
    with tempfile.TemporaryDirectory(prefix='p1-check-') as temporary:
        target = pathlib.Path(temporary) if output is None else pathlib.Path(output)
        if output is not None:
            target.mkdir(parents=True, exist_ok=False)
        cancel_controls(target)
        bad = subprocess.run([sys.executable, str(pathlib.Path(__file__).with_name('RunBaseline.py')), '--gateway', str(target / 'missing'), '--host', str(target / 'missing-host'), '--assets', str(target / 'missing-assets'), '--output', str(target / 'should-not-exist')], capture_output=True, text=True)
        assert bad.returncode == 2 and not (target / 'should-not-exist').exists()
        print(json.dumps({'missing_asset_exit': bad.returncode}))
    print(json.dumps({'PASS': True, 'timing_controls': 3, 'negative_attempts': len(failures), 'cells': len(cells)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(cancel_child() if len(sys.argv) > 1 and sys.argv[1] == '--cancel-child' else main())
