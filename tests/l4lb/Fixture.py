"""Bounded, gate-controlled HTTP fixtures; no gateway or L4 implementation here."""
import http.server
import json
import threading


def payload(identity, model):
    return json.dumps({'id': identity, 'model': model}, separators=(',', ':')).encode()


def prefix(identity, model):
    return b'data: ' + payload(identity, model) + b'\n\n'


TAIL = b'data: [DONE]\n\n'


class Backend(http.server.ThreadingHTTPServer):
    daemon_threads = False
    allow_reuse_address = True

    def __init__(self, model):
        self.model = model
        self.records = []
        self.errors = []
        self.gates = {}
        self.unavailable = False
        self.lock = threading.Lock()
        super().__init__(('127.0.0.1', 0), Handler)
        self.worker = threading.Thread(target=self.serve_forever, kwargs={'poll_interval': .05})
        self.worker.start()

    def gate(self, identity):
        event = threading.Event()
        self.gates[identity] = event
        return event

    def close(self):
        for event in self.gates.values():
            event.set()
        self.shutdown()
        self.server_close()
        self.worker.join(2)
        if self.worker.is_alive():
            raise RuntimeError('backend thread remained')

    def handle_error(self, request, client_address):
        self.errors.append('unexpected handler failure')


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def do_POST(self):
        try:
            length = int(self.headers['Content-Length'])
            if not 0 < length <= 8192:
                raise ValueError('fixture request too large')
            request = json.loads(self.rfile.read(length))
            identity = request['messages'][0]['content']
            model = request['model']
            if model != self.server.model:
                raise ValueError('wrong model backend')
            with self.server.lock:
                self.server.records.append({'id': identity, 'model': model})
            self.send_response(503 if self.server.unavailable else 200)
            self.send_header('Connection', 'close')
            if request.get('stream') and not self.server.unavailable:
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                self.chunk(prefix(identity, model))
                event = self.server.gates.get(identity)
                if event is not None and not event.wait(15):
                    raise ValueError('fixture gate timed out')
                self.chunk(TAIL)
                self.wfile.write(b'0\r\n\r\n')
            else:
                data = payload(identity, model)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            # Expected for explicit client/gateway disconnect cases only.
            pass
        except Exception as error:
            self.server.errors.append(repr(error))
        finally:
            self.close_connection = True

    def chunk(self, data):
        self.wfile.write(f'{len(data):X}\r\n'.encode() + data + b'\r\n')
        self.wfile.flush()
