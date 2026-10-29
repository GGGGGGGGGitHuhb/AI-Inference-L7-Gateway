"""Open-loop requests retain scheduled origins and count actual TCP payload bytes."""
import socket
import time
from Common import WireResponse, body, request, digest, require


class Response(WireResponse):
    def __init__(self, sock, row, deadline):
        super().__init__(sock)
        self.row, self.deadline = row, deadline
        self.last_recv = None

    def receive(self):
        remaining = (self.deadline - time.monotonic_ns()) / 1e9
        if remaining <= 0:
            raise TimeoutError('absolute request deadline')
        self.sock.settimeout(remaining)
        data = self.sock.recv(16384)
        self.last_recv = time.monotonic_ns()
        self.row['rx_bytes'] += len(data)
        if data:
            if self.row['first_wire_ns'] is None:
                self.row['first_wire_ns'] = self.last_recv
            self.buffer += data
        return bool(data)

    def finish(self):
        if self.row['http_ns'] is None:
            self.row['http_ns'] = self.last_recv
        return super().finish()

    def read1(self, limit):
        data = super().read1(limit)
        if data and self.row['first_body_ns'] is None:
            self.row['first_body_ns'] = self.last_recv
        if self.length == 0 and self.row['http_ns'] is None:
            self.row['http_ns'] = self.last_recv
        return data


def unsent(identity, scheduled, target, reason):
    return {'id': identity, 'scheduled_ns': scheduled, 'target_port': target, 'outcome': reason,
            'dispatch_ns': None, 'http_ns': None, 'first_wire_ns': None,
            'first_body_ns': None, 'closed_ns': time.monotonic_ns(),
            'tx_bytes': 0, 'rx_bytes': 0, 'status': None, 'error': None}


def attempt(identity, scheduled, target, workload):
    started = time.monotonic_ns()
    if started - scheduled > 50_000_000:
        return unsent(identity, scheduled, target, 'not_sent')
    row = unsent(identity, scheduled, target, 'failure')
    row['dispatch_ns'] = started
    data = request(identity, workload)
    row['request_sha256'] = digest(data)
    deadline = started + 5_000_000_000
    sock = None
    try:
        sock = socket.create_connection(('127.0.0.1', target), timeout=5)
        row['connect_ns'] = time.monotonic_ns()
        sock.settimeout(max(.001, (deadline - time.monotonic_ns()) / 1e9))
        view = memoryview(data)
        while view:
            remaining = (deadline - time.monotonic_ns()) / 1e9
            if remaining <= 0:
                raise TimeoutError('absolute send deadline')
            sock.settimeout(remaining)
            count = sock.send(view)
            require(count > 0, 'zero send')
            row['tx_bytes'] += count
            view = view[count:]
        row['send_ns'] = time.monotonic_ns()
        response = Response(sock, row, deadline)
        response.begin()
        row['head_ns'] = response.last_recv
        row['status'] = response.status
        require(response.chunked or response.length is not None, 'framed response required')
        payload = bytearray()
        while True:
            part = response.read1(16384)
            if not part:
                break
            payload.extend(part)
            require(len(payload) <= 16384, 'response budget')
        require(response.status == 200, 'HTTP response not successful')
        require(bytes(payload) == body(identity, workload), 'response body differs')
        require(response.complete and row['http_ns'] is not None, 'HTTP completion missing')
        row['body_sha256'] = digest(payload)
        row['outcome'] = 'success'
    except Exception as error:
        row['error'] = repr(error)
    finally:
        if sock is not None:
            sock.close()
        row['closed_ns'] = time.monotonic_ns()
    return row
