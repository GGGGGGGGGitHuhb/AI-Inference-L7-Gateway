"""Synthetic S2 upstream, bounded socket waits and owned thread lifecycle."""
import socket
import threading
import time

BODY = b'{"result":"synthetic"}'

class ProxyBackend:
    def __init__(self, mode="fixed", response_body=BODY, delay=0):
        self.mode, self.response_body, self.delay = mode, response_body, delay
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(16)
        self.listener.settimeout(.1)
        self.port = self.listener.getsockname()[1]
        self.requests = []
        self.accepted = 0
        self.errors = []
        self.stop = threading.Event()
        self.request_seen = threading.Event()
        self.thread = threading.Thread(target=self.serve)
        self.thread.start()

    def response(self):
        body = self.response_body
        if self.mode == "chunked":
            return b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n' + hex(len(body))[2:].encode() + b';foo = "bar" ;next=x\r\n' + body + b'\r\n0;end = yes\r\n\r\n'
        if self.mode == "eof":
            return b"HTTP/1.1 200 OK\r\n\r\n" + body
        if self.mode == "malformed":
            return b"HTTP/1.1 200 OK\r\nBad Header: invalid\r\n\r\n"
        if self.mode in ["204", "304"]:
            return b"HTTP/1.1 " + self.mode.encode() + b" Empty\r\n\r\n"
        code = self.mode.encode() if self.mode.isdigit() else b"200"
        if self.mode == "early":
            code = b"413"
        header = b"HTTP/1.1 " + code + b" Test\r\nContent-Length: " + str(len(body)).encode() + b"\r\nContent-Type: " + (b"text/event-stream" if self.mode == "sse" else b"application/json") + b"\r\nX-Reply: one\r\nX-Reply: two\r\nConnection: X-Hop\r\nX-Hop: stripped\r\n\r\n"
        result = header + body
        if self.mode == "truncated":
            result = result[:-3]
        if self.mode == "informational":
            result = b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 103 Hints\r\nLink: </x>\r\n\r\n" + result
        return result

    def serve(self):
        while not self.stop.is_set():
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.accepted += 1
            try:
                with connection:
                    connection.settimeout(3)
                    request = bytearray()
                    while b"\r\n\r\n" not in request:
                        piece = connection.recv(1024)
                        if not piece:
                            break
                        request.extend(piece)
                    if b"\r\n\r\n" not in request:
                        continue
                    headers, body = bytes(request).split(b"\r\n\r\n", 1)
                    length = next(int(line.split(b":",1)[1]) for line in headers.split(b"\r\n") if line.lower().startswith(b"content-length:"))
                    if self.mode != "early":
                        while len(body) < length:
                            piece = connection.recv(min(4096, length-len(body)))
                            if not piece:
                                break
                            body += piece
                            if self.mode == "slow_read":
                                time.sleep(.001)
                    self.requests.append((headers, body))
                    self.request_seen.set()
                    if self.delay:
                        self.stop.wait(self.delay)
                    response = self.response()
                    if self.mode == "fragmented":
                        for offset in range(0, len(response), 3):
                            connection.sendall(response[offset:offset+3])
                    else:
                        connection.sendall(response)
                    if self.mode == "early":
                        connection.shutdown(socket.SHUT_WR)
                        while connection.recv(4096):
                            pass
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                pass
            except Exception as error:
                self.errors.append(repr(error))

    def close(self):
        self.stop.set()
        self.listener.close()
        self.thread.join(4)
        assert not self.thread.is_alive(), "backend worker survived"
        assert not self.errors, self.errors
