"""Owned loopback process for S3 tests; synthetic data only."""
import json
import multiprocessing
import socket
import struct
import threading
import time
from pathlib import Path


def serve(listener, stop, accepted, requests, path, mode, body, delay):
    lock = threading.Lock()
    connections = []
    workers = []

    def record(value):
        with lock:
            with open(path, "a") as output:
                output.write(json.dumps(value) + "\n")

    def handle(connection, identity):
        connection.settimeout(.1)
        pending = b""
        try:
            while not stop.is_set():
                while b"\r\n\r\n" not in pending:
                    try:
                        part = connection.recv(65536)
                    except socket.timeout:
                        if stop.is_set(): return
                        continue
                    if not part: return
                    pending += part
                headers, pending = pending.split(b"\r\n\r\n", 1)
                fields = {}
                for line in headers.split(b"\r\n")[1:]:
                    key, value = line.split(b":", 1)
                    fields[key.lower()] = value.strip()
                length = int(fields[b"content-length"])
                while len(pending) < length:
                    try: part = connection.recv(65536)
                    except socket.timeout:
                        if stop.is_set(): return
                        continue
                    if not part: return
                    pending += part
                request, pending = pending[:length], pending[length:]
                marker = json.loads(request)["messages"][0]["content"]
                with requests.get_lock(): requests.value += 1
                record({"connection": identity, "marker": marker, "close": fields.get(b"connection") == b"close"})
                if delay: time.sleep(delay)
                payload = body if body is not None else json.dumps({"echo": marker}, separators=(",", ":")).encode()
                status = int(mode) if mode.isdigit() else 200
                if status in (204, 304): payload = b""
                prefix = b"HTTP/1.1 " + str(status).encode() + b" OK\r\n"
                extra = b""
                if mode == "close": extra = b"Connection: keep-alive\r\ncOnNeCtIoN: foo, ClOsE\r\n"
                if mode == "informational": prefix = b"HTTP/1.1 100 Continue\r\n\r\n" + prefix
                if mode == "chunked":
                    response = prefix + b"Transfer-Encoding: chunked\r\n\r\n" + hex(len(payload))[2:].encode() + b";foo = bar\r\n" + payload + b"\r\n0\r\n\r\n"
                elif mode == "eof": response = prefix + b"\r\n" + payload
                else: response = prefix + extra + b"Content-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload
                if mode == "truncated": response = response[:-1]
                if mode == "trailing": response += b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nbad"
                connection.sendall(response)
                if mode in ("late", "fin", "rst"):
                    time.sleep(.03)
                    if mode == "late": connection.sendall(b"unsolicited")
                    elif mode == "rst": connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)); return
                    else: return
                if fields.get(b"connection") == b"close" or mode in ("close", "eof", "truncated"): return
        except (OSError, ValueError):
            pass
        finally:
            connection.close()

    listener.settimeout(.1)
    try:
        while not stop.is_set():
            try: connection, _ = listener.accept()
            except socket.timeout: continue
            connections.append(connection)
            with accepted.get_lock():
                accepted.value += 1
                identity = accepted.value
            worker = threading.Thread(target=handle, args=(connection, identity))
            worker.start(); workers.append(worker)
    finally:
        listener.close()
        for connection in connections:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        for worker in workers: worker.join(2)


class PersistentBackend:
    def __init__(self, directory, mode="fixed", body=None, delay=0):
        self.record_path = Path(directory) / ("backend-" + str(time.monotonic_ns()) + ".jsonl")
        self.record_path.write_text("")
        self.stop = multiprocessing.Event()
        self.accepts = multiprocessing.Value("Q", 0)
        self.requests = multiprocessing.Value("Q", 0)
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0)); listener.listen(128)
        self.port = listener.getsockname()[1]
        self.process = multiprocessing.Process(target=serve, args=(listener, self.stop, self.accepts, self.requests, str(self.record_path), mode, body, delay))
        self.process.start(); listener.close()

    def counts(self):
        return {"accepts": self.accepts.value, "requests": self.requests.value}

    def close(self):
        self.stop.set(); self.process.join(3)
        if self.process.is_alive():
            self.process.kill(); self.process.join(2)
            raise AssertionError("backend failed to stop")
        assert self.process.exitcode == 0, self.process.exitcode
        try:
            survivor = socket.create_connection(("127.0.0.1", self.port), timeout=.1)
        except OSError: return
        survivor.close()
        raise AssertionError("backend listener survived")
