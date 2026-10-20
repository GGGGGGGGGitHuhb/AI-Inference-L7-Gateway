"""One independent synthetic server process; bounded per-cell records, no hot-path files."""
import argparse
import http.server
import json
import pathlib
import signal
import threading
import time
from Client import PAYLOADS


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

    def __init__(self, port, group):
        super().__init__(('127.0.0.1', port), Handler)
        self.group = group
        self.accepts = 0
        self.requests = []
        self.lock = threading.Lock()

    def get_request(self):
        connection, address = super().get_request()
        with self.lock:
            self.accepts += 1
        return connection, address


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_):
        pass

    def do_POST(self):
        request = self.rfile.read(int(self.headers['Content-Length']))
        json.loads(request)
        close = self.headers.get('Connection', '').lower() == 'close'
        self.close_connection = close
        group = self.server.group
        body = PAYLOADS[group]
        self.send_response(200)
        self.send_header('Content-Type', 'application/json' if group == 'A' else 'text/event-stream')
        self.send_header('Connection', 'close' if close else 'keep-alive')
        self.send_header('Content-Length' if group == 'A' else 'Transfer-Encoding',
                         str(len(body)) if group == 'A' else 'chunked')
        self.end_headers()
        times = []
        error = None
        try:
            if group == 'A':
                self.wfile.write(body)
                times.append(time.monotonic_ns())
            else:
                size = 1024 if group == 'B' else 16384
                for offset in range(0, len(body), size):
                    if offset and group == 'B':
                        time.sleep(.001)
                    part = body[offset:offset + size]
                    self.wfile.write(f'{len(part):x}\r\n'.encode() + part + b'\r\n')
                    times.append(time.monotonic_ns())
                self.wfile.write(b'0\r\n\r\n')
        except OSError as failure:
            error = repr(failure)
        finally:
            with self.server.lock:
                self.server.requests.append({'first_send': times[0] if times else None,
                    'last_send': times[-1] if times else None,
                    'interval_ns': [b-a for a, b in zip(times, times[1:])] if group == 'B' else [],
                    'error': error, 'connection_close': close})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--group', choices=['A', 'B', 'C'], required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    server = Server(args.port, args.group)
    server.timeout = .05
    signal.signal(signal.SIGUSR1, lambda *_: pathlib.Path(args.output + ".warmup").write_text(json.dumps({"accepts": server.accepts, "requests": len(server.requests)})))
    print('READY', flush=True)
    try:
        while not stopping.is_set():
            server.handle_request()
    finally:
        server.server_close()
        with open(args.output, 'w') as output:
            json.dump({'accepts': server.accepts, 'requests': server.requests}, output)


if __name__ == '__main__':
    main()
