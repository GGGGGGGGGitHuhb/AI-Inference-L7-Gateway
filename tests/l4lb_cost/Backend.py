"""Separate synthetic backend process, exact user-space read/write byte accounting."""
import argparse
import http.server
import json
import signal
import socket
import threading
import time
from Common import body, write, require


class Counted:
    def __init__(self, inner):
        self.inner = inner
        self.count = 0

    def read(self, size=-1):
        data = self.inner.read(size)
        self.count += len(data)
        return data

    def readline(self, size=-1):
        data = self.inner.readline(size)
        self.count += len(data)
        return data

    def write(self, data):
        sent = self.inner.write(data)
        self.count += sent
        return sent

    def __getattr__(self, name):
        return getattr(self.inner, name)


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = False
    allow_reuse_address = True

    def __init__(self, port, workload):
        self.workload = workload
        self.records, self.errors = [], []
        self.accepts = 0
        self.lock = threading.Lock()
        super().__init__(('127.0.0.1', port), Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(5)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self.lock:
            self.accepts += 1
        return connection, address

    def handle_error(self, *_):
        self.errors.append('unhandled backend handler failure')


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        pass

    def setup(self):
        super().setup()
        self.rfile, self.wfile = Counted(self.rfile), Counted(self.wfile)

    def do_POST(self):
        row = {'id': None, 'started_ns': time.monotonic_ns(), 'error': None}
        try:
            size = int(self.headers['Content-Length'])
            require(0 < size <= 8192, 'request size')
            data = json.loads(self.rfile.read(size))
            row['id'] = data['messages'][0]['content']
            require(data['model'] == 'cost-model', 'unexpected model')
            require(data['stream'] == (self.server.workload == 'B'), 'unexpected stream flag')
            require(self.headers.get('Connection', '').lower() == 'close', 'reuse must be disabled')
            payload = body(row['id'], self.server.workload)
            self.send_response(200)
            self.send_header('Connection', 'close')
            self.send_header('Content-Type', 'application/json' if self.server.workload == 'A' else 'text/event-stream')
            self.send_header('Content-Length' if self.server.workload == 'A' else 'Transfer-Encoding',
                             str(len(payload)) if self.server.workload == 'A' else 'chunked')
            self.end_headers()
            if self.server.workload == 'A':
                self.wfile.write(payload)
            else:
                for index in range(16):
                    if index:
                        time.sleep(.002)
                    part = payload[index * 1024:(index + 1) * 1024]
                    self.wfile.write(b'400\r\n' + part + b'\r\n')
                self.wfile.write(b'0\r\n\r\n')
            self.wfile.flush()
        except Exception as error:
            row['error'] = repr(error)
        finally:
            row.update(ended_ns=time.monotonic_ns(), rx_bytes=self.rfile.count, tx_bytes=self.wfile.count)
            self.close_connection = True
            with self.server.lock:
                self.server.records.append(row)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--workload', choices=['A', 'B'], required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    server = Server(args.port, args.workload)
    server.timeout = .05
    print('READY', flush=True)
    try:
        while not stopping.is_set():
            server.handle_request()
    finally:
        server.server_close()
        write(args.output, {'accepts': server.accepts, 'records': server.records, 'errors': server.errors})


if __name__ == '__main__':
    main()
