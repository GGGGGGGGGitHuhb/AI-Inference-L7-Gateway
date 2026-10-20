"""F-001 持久负控：每次异常尝试恰好一条，传播非零且socket关闭。"""
import concurrent.futures
import hashlib
import json
import os
import signal
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
from unittest import mock

from Support import (check, free_port, recorded_exchange, request_body, validate_real, install_interrupt_handlers)
from SyntheticRun import run_sample


def callback_failure(sock):
    raise RuntimeError('callback failure')


def callback_interrupt(sock):
    raise KeyboardInterrupt('callback interrupt')


def callback_signal(sock):
    os.kill(os.getpid(), signal.SIGTERM)


def response_wire(body, status=b'200', length=None):
    size = str(len(body)).encode() if length is None else length
    return b'HTTP/1.1 ' + status + b' OK\r\nContent-Type: text/event-stream\r\nContent-Length: ' + size + b'\r\nConnection: close\r\n\r\n' + body


def serve_once(listener, wire, delay, observed):
    connection, _ = listener.accept()
    with connection:
        connection.settimeout(2)
        connection.recv(65536)
        connection.sendall(wire)
        if delay:
            time.sleep(delay)
        connection.shutdown(socket.SHUT_WR)
        # 客户端finally必须主动关闭；既允许FIN也允许未读数据导致RST。
        try:
            observed.append(connection.recv(1) == b'')
        except ConnectionResetError:
            observed.append(True)
    listener.close()


def run_case(name, output):
    path = output / 'attempts.jsonl'
    request = request_body(True)
    content = b'data: {"choices":[{"delta":{"content":"x"},"finish_reason":null}]}\n\n'
    cases = {
        'bad-status': response_wire(b'', status=b'bad'),
        'bad-length': response_wire(b'', length=b'bad'),
        'sse': response_wire(b'not-data\n\n'),
        'json': response_wire(b'data: {bad}\n\n'),
        'shape': response_wire(b'data: {}\n\n'),
        'content-type': response_wire(b'data: {"choices":[{"delta":{"content":{"invalid":1}}}]}\n\n'),
        'callback': response_wire(content),
        'interrupt': response_wire(content),
        'signal': response_wire(content),
        'read-timeout': response_wire(b'data: ', length=b'100'),
        'validation': response_wire(b'{bad}'),
    }
    listener = thread = None
    observed = []
    port = free_port()
    options = {'timeout': .05 if name == 'read-timeout' else 1}
    validator = None
    if name in cases:
        listener = socket.socket(); listener.bind(('127.0.0.1', port)); listener.listen()
        thread = threading.Thread(target=serve_once,
            args=(listener, cases[name], .15 if name == 'read-timeout' else 0, observed))
        thread.start()
    if name == 'callback': options['on_content'] = callback_failure
    if name == 'interrupt': options['on_content'] = callback_interrupt
    if name == 'signal': options['on_content'] = callback_signal
    if name == 'validation':
        request['stream'] = False
        validator = lambda result: validate_real(result, False)
    error = None
    try:
        if name == 'connect-timeout':
            with mock.patch('Support.socket.create_connection', side_effect=TimeoutError('injected connect timeout')):
                recorded_exchange(port, request, path, {'label': name}, **options)
        else:
            result = recorded_exchange(port, request, path, {'label': name}, validator=validator, **options)
            # 原有OSError失败结果继续由调用者判失败，不能因为记日志而成功退出。
            check(not result['error'], 'expected failed attempt')
    except BaseException as failure:
        error = failure
    finally:
        if thread: thread.join(3)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    check(error is not None, 'negative must propagate/fail')
    check(len(rows) == 1, 'one record exactly')
    row = rows[0]
    check(row['label'] == name and row['error'] and row['end'] >= row['start'], 'identity/error/times')
    check(row['request_sha256'] and 'attempt_id' in row, 'request/attempt identity')
    check(row['body_sha256'] == hashlib.sha256(row['body'].encode()).hexdigest(), 'partial body hash')
    check(row['bytes'] == len(row['body'].encode()), 'partial byte count')
    if thread: check(observed == [True] and not thread.is_alive(), 'socket cleaned')
    expected_types = {'connect-refused': 'ConnectionRefusedError', 'connect-timeout': 'TimeoutError',
        'bad-status': 'ValueError', 'bad-length': 'ValueError', 'sse': 'AssertionError',
        'json': 'JSONDecodeError', 'shape': 'KeyError', 'content-type': 'TypeError',
        'callback': 'RuntimeError', 'interrupt': 'KeyboardInterrupt', 'signal': 'KeyboardInterrupt', 'read-timeout': 'TimeoutError',
        'validation': 'JSONDecodeError'}
    check(row['error_type'] == expected_types[name], 'expected specific exception')
    if name in ('interrupt', 'signal'): check(row['interrupted'], 'interruption classification')
    print(name, 'one retained', row['error_type'] if 'error_type' in row else row['error'], flush=True)
    raise error


def late_failures(output):
    path = output / 'late.jsonl'
    port = free_port()
    def worker(index):
        time.sleep(index * .03)
        return run_sample(port, index, 'fast', path)
    failed = False
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(worker, index) for index in range(4)]
            futures[0].result()
    except Exception:
        failed = True
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    check(failed and len(rows) == 4, 'late failures retained after first exception')
    check({row['index'] for row in rows} == set(range(4)), 'all indexes exactly once')
    check(len({row['attempt_id'] for row in rows}) == 4 and all(row['error'] for row in rows), 'unique failed attempts')
    print('late failures 4/4 retained')


def main():
    install_interrupt_handlers()
    if len(sys.argv) == 3:
        run_case(sys.argv[1], pathlib.Path(sys.argv[2]))
        return
    with tempfile.TemporaryDirectory() as directory:
        output = pathlib.Path(directory)
        for name in ('connect-refused', 'connect-timeout', 'bad-status', 'bad-length', 'sse',
                     'json', 'shape', 'content-type', 'callback', 'interrupt', 'signal', 'read-timeout', 'validation'):
            case_output = output / name; case_output.mkdir()
            result = subprocess.run([sys.executable, __file__, name, str(case_output)],
                                    capture_output=True, text=True, timeout=8)
            print(result.stdout, result.stderr, flush=True)
            check(result.returncode != 0 and 'one retained' in result.stdout,
                  f'{name}: negative propagation and evidence checks')
        late_failures(output)
        print('13 attempt negatives and 4 late failures passed')


if __name__ == '__main__':
    main()
