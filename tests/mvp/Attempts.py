"""Every started attempt has one finally record, including incomplete HTTP and cancellation."""
import hashlib
import http.client
import json
from pathlib import Path
import socket
import struct
import threading
import time

from Common import WireResponse, append, check
from Budget import save_attempt

FIRST = b'data: {"choices":[{"delta":{"content":"fixed"},"finish_reason":null}]}\n\n'
LAST = b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
SIM_BODY = FIRST + LAST


def validate(row, expected, code=None, synthetic=False):
    if expected == 'success':
        check(row['status'] == 200 and row['complete'] and not row['error'], 'normal HTTP failed')
        if row['stream']:
            check(row['content_times'] and row['done'] == 1 and row['finishes'] == 1, 'SSE terminal/content')
            check(not row.get('event_tail'), 'unfinished event')
        else:
            value = json.loads(row['body'])
            check(value['choices'][0]['message']['content'].strip(), 'empty JSON content')
        if synthetic:
            check(row['body_sha256'] == hashlib.sha256(SIM_BODY).hexdigest(), 'synthetic byte identity')
            check(row['bytes'] == len(SIM_BODY), 'synthetic body length')
        return 'success'
    if expected == 'cancelled':
        check(row.get('cancelled') and row['content_times'] or row.get('cancelled') and row.get('queued_cancel'), 'cancel gate missing')
        check(not row['complete'], 'cancel misclassified complete')
        return 'cancelled'
    if expected in ('rejected', 'queue_timeout'):
        check(row['complete'] and not row['error'], 'error HTTP incomplete')
        check(row['status'] == (504 if expected == 'queue_timeout' else 503), 'wrong rejection status')
        check(json.loads(row['body'])['error']['code'] == code, 'wrong rejection code')
        return expected
    if expected == 'backend_failure':
        if code:
            check(row['status'] == 502 and row['complete'] and not row['error'], '502 backend failure')
            check(json.loads(row['body'])['error']['code'] == code, 'backend error code')
        else:
            check(row['status'] == 200 and row['content_times'] and not row['complete'] and row['error'], 'committed truncation missing')
            check(row['done'] == 0 and b'HTTP/1.1' not in row['body'].encode(), 'truncation repaired')
        return expected
    raise AssertionError('unrecognized expected outcome')


class Attempt:
    def __init__(self, identity, group, port, request, output, expected='success', code=None,
                 timeout=155, slow=False, half=False, synthetic=False, cohort='formal'):
        self.row = {'id': identity, 'group': group, 'cohort': cohort, 'stream': request['stream'],
                    'model': request['model'], 'expected': expected, 'expected_code': code,
                    'started': time.monotonic(), 'status': None, 'complete': False,
                    'error': None, 'done': 0, 'finishes': 0, 'content_times': [], 'pieces': [],
                    'outcome': 'failure', 'ttft': None, 'e2e': None, 'slow': slow, 'half': half}
        self.request, self.port, self.output = request, port, Path(output)
        self.timeout, self.slow, self.half, self.synthetic = timeout, slow, half, synthetic
        self.first = threading.Event()
        self.sent = threading.Event()
        self.finished = threading.Event()
        self.cancel = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def retry(self, operation):
        while True:
            if self.cancel.is_set():
                self.row['cancelled'] = True
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
                raise InterruptedError('planned RST')
            if time.monotonic() >= self.row['started'] + self.timeout:
                raise TimeoutError('fixed client deadline')
            try:
                return operation()
            except socket.timeout:
                continue

    def run(self):
        received = bytearray()
        event_buffer = b''
        self.sock = None
        response = None
        try:
            payload = json.dumps(self.request, ensure_ascii=False).encode()
            self.row['request_sha256'] = hashlib.sha256(payload).hexdigest()
            headers = (f'POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n'
                       f'Content-Type: application/json\r\nContent-Length: {len(payload)}\r\nX-Mvp-Id: {self.row["id"]}\r\nConnection: close\r\n\r\n').encode()
            self.row['logical_charge'] = 1024 + len(b'POST') + len(b'/v1/chat/completions') + len(payload) + sum(
                len(line.split(b':', 1)[0]) + len(line.split(b':', 1)[1].strip()) + 4
                for line in headers.split(b'\r\n')[1:] if b':' in line)
            self.sock = socket.create_connection(('127.0.0.1', self.port), timeout=self.timeout)
            self.row['client_port'] = self.sock.getsockname()[1]
            self.sock.sendall(headers + payload)
            self.row['sent'] = time.monotonic()
            if self.half:
                self.sock.shutdown(socket.SHUT_WR)
            self.sock.settimeout(.05)
            self.sent.set()
            response = WireResponse(self.sock)
            self.retry(response.begin)
            self.row.update(status=response.status, headers=response.getheaders(), raw_head=response.raw_head.decode('latin1'))
            paused = False
            while True:
                part = self.retry(lambda: response.read1(1024 if self.slow else 16384))
                if not part:
                    self.row['complete'] = True
                    self.row['e2e'] = time.monotonic() - self.row['sent']
                    break
                now = time.monotonic()
                received.extend(part)
                check(len(received) <= 16 * 1024**2, 'response byte bound')
                self.row['pieces'].append([now, len(part)])
                if self.request['stream'] and response.status == 200:
                    event_buffer += part
                    while b'\n\n' in event_buffer:
                        event, event_buffer = event_buffer.split(b'\n\n', 1)
                        check(event.startswith(b'data: '), 'invalid SSE event')
                        data = event[6:]
                        if data == b'[DONE]':
                            self.row['done'] += 1
                            continue
                        check(self.row['done'] == 0, 'event after DONE')
                        choice = json.loads(data)['choices'][0]
                        self.row['finishes'] += int(choice.get('finish_reason') is not None)
                        if choice.get('delta', {}).get('content'):
                            self.row['content_times'].append(now)
                            if self.row['ttft'] is None:
                                self.row['ttft'] = now - self.row['sent']
                            self.first.set()
                    if self.slow and self.first.is_set() and not paused:
                        paused = True
                        self.row['slow_pause_start'] = time.monotonic()
                        time.sleep(1)
                        self.row['slow_pause_end'] = time.monotonic()
                    elif self.slow and paused:
                        time.sleep(.02)
        except BaseException as error:
            self.row['error'] = repr(error)
            self.row['error_type'] = type(error).__name__
        finally:
            self.row.update(ended=time.monotonic(), bytes=len(received), body=received.decode('utf-8', errors='replace'),
                            body_sha256=hashlib.sha256(received).hexdigest(), event_tail=event_buffer.decode('utf-8', errors='replace'))
            if response and self.row['status'] is None:
                self.row['status'] = response.status
                self.row['raw_head'] = response.raw_head.decode('latin1')
            if self.sock:
                self.sock.close()
            try:
                self.row['outcome'] = validate(self.row, self.row['expected'], self.row['expected_code'], self.synthetic)
            except BaseException as error:
                self.row['validation_error'] = repr(error)
            finally:
                # Each attempt owns its file, so concurrent finally paths cannot overwrite another.
                path = self.output / (self.row['id'] + '.json')
                try:
                    save_attempt(path, self.row)
                except BaseException as error:
                    self.row['persistence_error'] = repr(error)
                finally:
                    self.finished.set()

    def join(self):
        self.thread.join(max(0, self.row['started'] + self.timeout + 1 - time.monotonic()))
        check(not self.thread.is_alive(), 'attempt thread stuck')
        check('persistence_error' not in self.row, self.row.get('persistence_error', ''))
        check('validation_error' not in self.row, self.row.get('validation_error', ''))
        return self.row

    def cancel_at_gate(self, queued=False):
        check(not self.finished.is_set(), 'cancel after completion')
        self.row['queued_cancel'] = queued
        self.row['cancel_requested'] = time.monotonic()
        self.cancel.set()

    def stop(self):
        if self.thread.is_alive():
            self.cancel.set()
            self.thread.join(2)
            check(not self.thread.is_alive(), 'attempt not reaped')
