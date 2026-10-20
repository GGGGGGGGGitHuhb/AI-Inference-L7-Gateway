"""P1 timestamps use observed recv boundaries, never EOF as CL/chunked E2E."""
import hashlib
import http.client
import json
import pathlib
import socket
import sys
import time

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1] / 'integration'))
from WireResponse import WireResponse

CLOCKS = ('t0', 't_connect', 't_send', 't_head', 't_first_wire', 't_body',
          't_content', 't_http', 't_eof', 't_validated', 't_closed')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sse_body(size):
    records = []
    for index in range(size // 1024):
        if index == size // 1024 - 1:
            data = '[DONE]'
        else:
            data = json.dumps({'choices': [{'delta': {'content': 'x'},
                'finish_reason': 'stop' if index == size // 1024 - 2 else None}]}, separators=(',', ':'))
        record = ('data: ' + data).encode()
        records.append(record + b' ' * (1022 - len(record)) + b'\n\n')
    return b''.join(records)


PAYLOADS = {'A': b'{"value":"' + b'x' * 1012 + b'"}',
            'B': sse_body(65536), 'C': sse_body(4194304)}
assert len(PAYLOADS['A']) == 1024


def request_bytes(stream, real=False):
    prompt = 'x' * 256
    if real:
        prompt = json.loads((pathlib.Path(__file__).resolve().parents[1] /
                             'integration/Inputs.json').read_text())['short']
    body = json.dumps({'model': 'gateway-qwen', 'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0, 'max_tokens': 32, 'stream': stream, 'n': 1}, separators=(',', ':')).encode()
    return (b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\n'
            b'Content-Type: application/json\r\nConnection: close\r\nContent-Length: ' +
            str(len(body)).encode() + b'\r\n\r\n' + body)


class TimedResponse(WireResponse):
    def __init__(self, sock, result, deadline, timeout, slow=False):
        super().__init__(sock)
        self.result, self.deadline, self.timeout, self.slow = result, deadline, timeout, slow
        self.last_recv = None

    def receive(self):
        remaining = (self.deadline - time.monotonic_ns()) / 1e9
        if remaining <= 0:
            raise TimeoutError('absolute request deadline')
        self.sock.settimeout(min(self.timeout, remaining))
        part = self.sock.recv(16384)
        self.last_recv = time.monotonic_ns()
        if part:
            if self.result['t_first_wire'] is None:
                self.result['t_first_wire'] = self.last_recv
            self.buffer += part
            if self.slow:
                time.sleep(.005)
        else:
            self.result['t_eof'] = self.last_recv
        return bool(part)

    def finish(self):
        if self.result['t_http'] is None:
            self.result['t_http'] = self.last_recv
        return super().finish()

    def read1(self, maximum):
        part = super().read1(maximum)
        if part and self.result['t_body'] is None:
            self.result['t_body'] = self.last_recv
        if self.length == 0 and self.result['t_http'] is None:
            self.result['t_http'] = self.last_recv
        if self.complete and self.result['t_http'] is None:
            self.result['t_http'] = self.result['t_eof']
        return part


def attempt(port, request, meta, group, stream, timeout, slow=False, validator=None):
    result = {**meta, **dict.fromkeys(CLOCKS), 'status': None, 'error': None,
              'error_type': None, 'category': None, 'success': False, 'phase': 'connect',
              'request_sha256': digest(request), 'completion_tokens': None, 'slow': slow}
    body = bytearray()
    sock = response = None
    events = b''
    contents, finishes, done = [], [], 0
    result['t0'] = time.monotonic_ns()
    deadline = result['t0'] + int(timeout * 1e9)
    try:
        sock = socket.create_connection(('127.0.0.1', port), timeout)
        result['t_connect'] = time.monotonic_ns()
        if slow:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            result['actual_rcvbuf'] = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        result['phase'] = 'send'
        remaining = (deadline - time.monotonic_ns()) / 1e9
        if remaining <= 0:
            raise TimeoutError('absolute request deadline before send')
        sock.settimeout(min(timeout, remaining))
        sock.sendall(request)
        result['t_send'] = time.monotonic_ns()
        response = TimedResponse(sock, result, deadline, timeout, slow)
        if slow:
            time.sleep(.5)
        result['phase'] = 'head'
        response.begin()
        result['t_head'] = response.last_recv
        result['status'] = response.status
        result['framing'] = 'chunked' if response.chunked else 'CL' if response.length is not None else 'EOF'
        result['phase'] = 'body'
        while True:
            part = response.read1(16384)
            if not part:
                break
            body.extend(part)
            if len(body) > 8 * 1024**2:
                raise ValueError('response body guard')
            if stream and result['status'] == 200:
                events += part
                while b'\n\n' in events:
                    event, events = events.split(b'\n\n', 1)
                    for line in event.splitlines():
                        if not line.startswith(b'data:'):
                            continue
                        data = line[5:].strip()
                        if done:
                            raise ValueError('SSE data after DONE')
                        if data == b'[DONE]':
                            if len(finishes) != 1 or not contents:
                                raise ValueError('DONE before content/finish')
                            done += 1
                            continue
                        value = json.loads(data)
                        if value.get('usage'):
                            result['completion_tokens'] = value['usage'].get('completion_tokens')
                        for choice in value.get('choices', []):
                            content = choice.get('delta', {}).get('content')
                            if content:
                                if not isinstance(content, str):
                                    raise ValueError('content is not text')
                                contents.append(content)
                                if result['t_content'] is None:
                                    result['t_content'] = response.last_recv
                            if choice.get('finish_reason'):
                                finishes.append(choice['finish_reason'])
        result['phase'] = 'validation'
        if result['status'] != 200:
            result['category'] = 'http_rejection'
            raise ValueError(f'HTTP status {result["status"]}')
        if group in PAYLOADS and bytes(body) != PAYLOADS[group]:
            raise ValueError('deterministic body mismatch')
        if stream:
            if not contents or len(finishes) != 1 or done != 1 or events.strip():
                raise ValueError('SSE content/finish/DONE terminal validation')
        else:
            value = json.loads(body)
            if group.startswith('R'):
                message = value['choices'][0]['message']
                if message.get('role') != 'assistant' or not isinstance(message.get('content'), str) or not message['content']:
                    raise ValueError('invalid/empty assistant response')
                result['completion_tokens'] = value.get('usage', {}).get('completion_tokens')
                result['backend_timings'] = value.get('timings')
        if validator:
            validator(result)
        result['t_validated'] = time.monotonic_ns()
        result['success'] = True
    except BaseException as error:
        result['error'], result['error_type'] = repr(error), type(error).__name__
        if not result['category']:
            result['category'] = ('timeout' if isinstance(error, TimeoutError) else
                'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else
                'connection' if isinstance(error, OSError) else
                'validation' if result['phase'] == 'validation' else 'protocol')
    finally:
        if response:
            result['status'] = response.status
            result['headers'] = response.headers
            result['raw_head'] = response.raw_head.decode('latin1')
        result['decoded_bytes'], result['body_sha256'] = len(body), digest(body)
        result['done_count'], result['finish_reasons'] = done, finishes
        if sock:
            sock.close()
        result['t_closed'] = time.monotonic_ns()
    return result
