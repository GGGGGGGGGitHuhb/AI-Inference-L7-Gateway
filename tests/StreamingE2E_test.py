"""Real socket gates: the backend cannot finish until the client sees a prefix."""
import json
import os
import signal
import socket
import struct
import sys
import tempfile
import threading
import time
from support.ReuseHarness import GatewayProcess
from support.PersistentBackend import PersistentBackend
from support.ReuseHarness import request_wire, receive

EXE = sys.argv[1]
PREFIX = b"data: hel"
TAIL = b"lo\n\n\xef\xbb\xbf: comment\r\ndata: \xe4\xbd\xa0\ndata: two\n\ndata: [DONE]\n\ndata: after\n\n"
checks = 0


def check(value, detail=""):
    global checks
    checks += 1
    assert value, detail


def stream_request(stream=True):
    body = json.dumps({"model": "demo", "messages": [{"role": "user", "content": "synthetic"}], "stream": stream}, separators=(",", ":")).encode()
    return b"POST /v1/chat/completions HTTP/1.1\r\nHost: client\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


class Decoder:
    def __init__(self):
        self.pending = b""
        self.headers = None
        self.body = bytearray()
        self.remaining = None
        self.complete = False
        self.need_crlf = False
        self.zero = False

    def feed(self, data):
        self.pending += data
        if self.headers is None:
            if b"\r\n\r\n" not in self.pending: return
            self.headers, self.pending = self.pending.split(b"\r\n\r\n", 1)
            check(self.headers.startswith(b"HTTP/1.1 200"), self.headers)
            check(b"transfer-encoding: chunked" in self.headers.lower() and b"content-length:" not in self.headers.lower())
        while not self.complete:
            if self.zero:
                if len(self.pending) < 2: return
                check(self.pending.startswith(b"\r\n"))
                self.pending = self.pending[2:]; self.complete = True; return
            if self.need_crlf:
                if len(self.pending) < 2: return
                check(self.pending.startswith(b"\r\n"))
                self.pending = self.pending[2:]; self.need_crlf = False; self.remaining = None
            if self.remaining is None:
                if b"\r\n" not in self.pending: return
                line, self.pending = self.pending.split(b"\r\n", 1)
                self.remaining = int(line, 16)
                if self.remaining == 0: self.zero = True; continue
            count = min(self.remaining, len(self.pending))
            self.body.extend(self.pending[:count]); self.pending = self.pending[count:]; self.remaining -= count
            if self.remaining: return
            self.need_crlf = True


def read_until(client, decoder, predicate):
    deadline = time.monotonic() + 5
    while not predicate():
        check(time.monotonic() < deadline, "client gate timeout")
        data = client.recv(65536)
        check(bool(data), "EOF before gate")
        decoder.feed(data)


class GatedBackend:
    def __init__(self, framing="chunked", ending="normal", long_size=0):
        self.listener = socket.socket(); self.listener.bind(("127.0.0.1", 0)); self.listener.listen(2); self.listener.settimeout(5)
        self.port = self.listener.getsockname()[1]
        self.framing = framing; self.ending = ending; self.long_size = long_size
        self.headers_seen = threading.Event(); self.prefix_seen = threading.Event(); self.release = threading.Event(); self.closed_before_read = threading.Event()
        self.progress = threading.Condition(); self.received = 0
        self.errors = []; self.observed_request = b""
        self.thread = threading.Thread(target=self.serve); self.thread.start()

    def serve(self):
        try:
            connection, _ = self.listener.accept()
            with connection:
                connection.settimeout(20 if self.ending == "slow" else 5)
                request = b""
                while b"\r\n\r\n" not in request: request += connection.recv(65536)
                headers, body = request.split(b"\r\n\r\n", 1)
                length = int(next(line.split(b":", 1)[1] for line in headers.split(b"\r\n") if line.lower().startswith(b"content-length:")))
                while len(body) < length: body += connection.recv(65536)
                self.observed_request = headers
                size = self.long_size or len(PREFIX + TAIL)
                framing = b"Transfer-Encoding: chunked\r\n" if self.framing == "chunked" else (b"Content-Length: " + str(size).encode() + b"\r\n" if self.framing == "cl" else b"")
                connection.sendall(b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\nContent-Type: Text/Event-Stream; charset = \"UTF-8\"\r\n" + framing + b"\r\n")
                assert self.headers_seen.wait(5), "client never received final headers"
                if self.framing == "chunked": connection.sendall(hex(size)[2:].encode() + b";foo = bar\r\n")
                connection.sendall(PREFIX)
                assert self.prefix_seen.wait(5), "client never received incomplete event/chunk"
                if self.ending == "cancel":
                    if connection.recv(1) == b"": self.closed_before_read.set()
                    return
                if self.ending in ("timeout", "stop", "stop_deadline"): self.release.wait(2); return
                if self.ending == "rst": connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)); return
                if self.ending == "truncated": return
                if self.long_size:
                    sent = len(PREFIX)
                    while sent < size:
                        block = b"x" * min(8192, size - sent)
                        connection.sendall(block); sent += len(block)
                        if self.ending != "slow":
                            with self.progress:
                                assert self.progress.wait_for(lambda: self.received >= sent or self.release.is_set(), timeout=5), "long stream prefix stalled"
                else: connection.sendall(TAIL)
                if self.framing == "chunked":
                    connection.sendall(b"\r\n" + (b"invalid\r\n" if self.ending == "badchunk" else b"0\r\nBad: trailer\r\n\r\n" if self.ending == "trailer" else b"0\r\n\r\n"))
                if self.ending == "slow":
                    if connection.recv(1) == b"": self.closed_before_read.set()
        except OSError as error:
            if self.ending in ("slow", "cancel") and not isinstance(error, socket.timeout): self.closed_before_read.set()
            if self.ending not in ("slow", "stop", "cancel"): self.errors.append(repr(error))
        except BaseException as error: self.errors.append(repr(error))

    def close(self):
        self.release.set()
        with self.progress: self.progress.notify_all()
        self.thread.join(6); self.listener.close()
        check(not self.thread.is_alive(), "backend thread survived")
        check(not self.errors, self.errors)


def normal_during_slow(backend):
    try:
        connection, _ = backend.listener.accept()
        with connection:
            connection.settimeout(5)
            request = b""
            while b"\r\n\r\n" not in request: request += connection.recv(65536)
            headers, body = request.split(b"\r\n\r\n", 1)
            length = int(next(line.split(b":", 1)[1] for line in headers.split(b"\r\n") if line.lower().startswith(b"content-length:")))
            while len(body) < length: body += connection.recv(65536)
            connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
    except BaseException as error: backend.errors.append(repr(error))


def gated_case(directory, framing, ending="normal", long_size=0, halfclose=False):
    backend = GatedBackend(framing, ending, long_size)
    overrides = {"timeouts_ms": {"response": 150, "total": 2000}} if ending == "timeout" else ({"timeouts_ms": {"shutdown": 70}} if ending in ("stop", "stop_deadline") else {})
    gateway = GatewayProcess(EXE, directory, backend, **overrides)
    decoder = Decoder()
    try:
        with gateway.client() as client:
            client.sendall(stream_request())
            if halfclose: client.shutdown(socket.SHUT_WR)
            read_until(client, decoder, lambda: decoder.headers is not None)
            check(len(decoder.body) == 0, "backend body escaped header gate")
            backend.headers_seen.set()
            read_until(client, decoder, lambda: len(decoder.body) >= len(PREFIX))
            check(bytes(decoder.body) == PREFIX and not decoder.complete, "must see partial SSE event before backend finishes HTTP chunk")
            backend.prefix_seen.set()
            if ending == "cancel":
                client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                client.close()
                check(backend.closed_before_read.wait(3), "downstream RST did not invalidate upstream")
                check(not decoder.complete)
                print("gated", framing, ending, "upstream_closed", True)
                return
            if ending == "slow":
                normal = threading.Thread(target=normal_during_slow, args=(backend,)); normal.start()
                with gateway.client() as other:
                    other.sendall(stream_request(False)); check(receive(other).endswith(b"ok"), "normal request blocked by slow stream")
                normal.join(5); check(not normal.is_alive())
                check(backend.closed_before_read.wait(20), "slow-reader upstream was not boundedly closed")
            if ending in ("stop", "stop_deadline"):
                gateway.process.send_signal(signal.SIGTERM)
                if ending == "stop": time.sleep(.02); gateway.process.send_signal(signal.SIGINT)
            while True:
                try: data = client.recv(65536)
                except ConnectionResetError: break
                if not data: break
                decoder.feed(data)
                with backend.progress:
                    backend.received = len(decoder.body); backend.progress.notify_all()
            if ending == "normal":
                expected = PREFIX + b"x" * (long_size - len(PREFIX)) if long_size else PREFIX + TAIL
                check(decoder.complete and bytes(decoder.body) == expected, (framing, len(decoder.body), decoder.complete))
            else: check(not decoder.complete, (ending, "false terminal chunk"))
            check(b"Connection: close" in backend.observed_request)
        if ending in ("stop", "stop_deadline"): gateway.process.wait(timeout=2)
        print("gated", framing, ending, "body_bytes", len(decoder.body), "complete", decoder.complete)
    finally:
        backend.release.set()
        try: gateway.close()
        finally: backend.close()


def mixed(directory):
    backend = PersistentBackend(directory)
    gateway = GatewayProcess(EXE, directory, backend)
    try:
        for stream in [False, False, True, False, False]:
            with gateway.client() as client:
                client.sendall(stream_request(stream)); result = receive(client)
            check(result.startswith(b"HTTP/1.1 200") and b'Transfer-Encoding: chunked' not in result)
        check(backend.counts() == {"accepts": 2, "requests": 5}, backend.counts())
    finally:
        try: gateway.close()
        finally: backend.close()


with tempfile.TemporaryDirectory(prefix="stream-e2e-", dir=os.environ["TMPDIR"]) as directory:
    for framing in ["cl", "chunked", "eof"]: gated_case(directory, framing, halfclose=True)
    for framing, ending in [("cl", "truncated"), ("chunked", "truncated"), ("chunked", "badchunk"), ("chunked", "trailer"), ("eof", "rst"), ("chunked", "timeout")]: gated_case(directory, framing, ending)
    gated_case(directory, "chunked", long_size=4*1024*1024+123)
    gated_case(directory, "chunked", "slow", long_size=8*1024*1024)
    gated_case(directory, "chunked", "stop")
    gated_case(directory, "chunked", "stop_deadline")
    gated_case(directory, "chunked", "cancel")
    mixed(directory)
print("Streaming real gate checks", checks)
