"""Short independent process failures; no model server or acceptance workload."""
from contextlib import nullcontext
import copy
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

from Attempts import Attempt, FIRST, validate
from Common import Host, OwnedProcess, WireResponse, body, check, check_limits, check_zero, configuration, save, summary, ZERO
from Real import verify_identity

CASES = ['missing_asset', 'wrong_asset', 'bad_http', 'missing_done', 'timeout', 'child_exit',
         'missing_sample', 'duplicate_sample', 'quota', 'residual', 'false_success']


class BytesSocket:
    def __init__(self, data):
        self.data = data

    def recv(self, maximum):
        result, self.data = self.data[:maximum], self.data[maximum:]
        return result


def negative_case(case, output):
    row = {'case': case, 'began': time.monotonic(), 'error': None}
    owned = None
    listener = None
    worker = None
    try:
        if case == 'missing_asset':
            verify_identity(output / 'absent', 1, 'bad')
        elif case == 'wrong_asset':
            (output / 'asset').write_bytes(b'x')
            verify_identity(output / 'asset', 1, '0' * 64)
        elif case == 'bad_http':
            response = WireResponse(BytesSocket(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nx\r\nZ\r\n'))
            response.begin()
            received = b''
            while True:
                part = response.read1(1024)
                if not part:
                    break
                received += part
                row['partial_body'] = received.decode()
        elif case in ('missing_done', 'false_success'):
            sample = {'status': 200, 'complete': case == 'missing_done', 'error': None,
                      'stream': True, 'content_times': [1.0], 'done': 0, 'finishes': 0}
            validate(sample, 'success')
        elif case == 'timeout':
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0)); listener.listen()
            def stall():
                connection, _ = listener.accept()
                with connection:
                    connection.recv(4096)
                    time.sleep(.25)
            worker = threading.Thread(target=stall)
            worker.start()
            attempt = Attempt('negative', 'detector', listener.getsockname()[1], body('a'), output, timeout=.1)
            attempt.join()
        elif case == 'child_exit':
            owned = OwnedProcess(['/bin/false'], output / 'child.log', output / 'processes.jsonl')
            check(owned.process.wait(2) == 0, 'child process failure')
        elif case in ('missing_sample', 'duplicate_sample'):
            sample = {'id': 'one', 'group': 'probe', 'outcome': 'success'}
            summary([sample] if case == 'missing_sample' else [sample, sample], ['one', 'two'])
        elif case == 'quota':
            state = {'peak_inflight': 3}
            check_limits(state, configuration([9001, 9002, 9003]))
        elif case == 'residual':
            state = {key: 0 for key in ZERO}; state['inflight'] = 1
            check_zero(state)
        raise AssertionError('negative control unexpectedly accepted')
    except BaseException as error:
        row['error'] = repr(error)
        row['rejected'] = 'unexpectedly accepted' not in str(error)
        return 2 if row['rejected'] else 0
    finally:
        if owned:
            owned.stop()
        if worker:
            worker.join(1)
        if listener:
            listener.close()
        row['ended'] = time.monotonic()
        save(output / 'negative-proof.json', row)


def main():
    if '--case' in sys.argv:
        output = Path(sys.argv[3]); output.mkdir()
        return negative_case(sys.argv[2], output)
    destination = Path(sys.argv[sys.argv.index('--output') + 1]) if '--output' in sys.argv else None
    if destination:
        destination.mkdir(parents=True, exist_ok=False)
    with (nullcontext(destination) if destination else tempfile.TemporaryDirectory(prefix='mvp-detectors-')) as temp:
        root = Path(temp)
        for case in CASES:
            output = root / case
            result = subprocess.run([sys.executable, __file__, '--case', case, str(output)], timeout=5, capture_output=True, text=True)
            check(result.returncode != 0, 'negative detector returned success: ' + case)
            proof = json.loads((output / 'negative-proof.json').read_text())
            check(proof['rejected'] and proof['error'], 'negative evidence missing')
            if case == 'timeout':
                attempt = json.loads((output / 'negative.json').read_text())
                check(attempt['outcome'] == 'failure' and not attempt['complete'], 'timeout falsely accepted')
        host = Host(sys.argv[1], configuration([9001, 9002, 9003]), root, 'short-host')
        try:
            host.drain('idle-startup')
        finally:
            host.stop()
    print('MvpDetectors: 11 subprocess negative cases, timeout attempt retained, host idle/stop passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
