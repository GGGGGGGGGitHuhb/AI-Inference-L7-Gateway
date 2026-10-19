import json
import selectors
import signal
import socket
import subprocess
import time
from pathlib import Path


def request_wire(marker="synthetic", close=True):
    body = json.dumps({"model": "demo", "messages": [{"role": "user", "content": marker}]}, separators=(",", ":")).encode()
    return b"POST /v1/chat/completions HTTP/1.1\r\nHost: test\r\nContent-Type: application/json\r\n" + (b"Connection: close\r\n" if close else b"") + b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


def receive(connection):
    data = b""
    while True:
        part = connection.recv(65536)
        if not part: return data
        data += part


class GatewayProcess:
    def __init__(self, executable, directory, backend, **overrides):
        self.config = {"listen_port": 0, "upstream_address": "127.0.0.1", "upstream_port": backend.port}
        self.config.update(overrides)
        self.config_path = Path(directory) / ("gateway-" + str(time.monotonic_ns()) + ".json")
        self.config_path.write_text(json.dumps(self.config))
        self.process = subprocess.Popen([executable, "--config", str(self.config_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                assert selector.select(5), "READY timeout"
            ready = self.process.stdout.readline()
            assert ready.startswith("READY 127.0.0.1:"), ready
            self.port = int(ready.rsplit(":", 1)[1])
        except BaseException:
            self.process.kill(); self.process.communicate(timeout=3)
            raise

    def client(self):
        return socket.create_connection(("127.0.0.1", self.port), timeout=5)

    def close(self):
        if self.process.poll() is None: self.process.send_signal(signal.SIGTERM)
        try: stdout, stderr = self.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.communicate(timeout=3)
            raise AssertionError("gateway failed to stop")
        assert self.process.returncode == 0, (self.process.returncode, stderr)
        assert "AddressSanitizer" not in stderr and "runtime error:" not in stderr, stderr
        try: survivor = self.client()
        except OSError: return
        survivor.close(); raise AssertionError("gateway listener survived")
