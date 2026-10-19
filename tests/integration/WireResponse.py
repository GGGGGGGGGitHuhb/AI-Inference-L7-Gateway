"""有界 HTTP/1.1 测试客户端：保留原始头，增量解帧并检查唯一终止。"""
import http.client


class WireResponse:
    def __init__(self, sock):
        self.sock = sock
        self.buffer = b''
        self.raw_head = b''
        self.headers = []
        self.status = None
        self.chunked = False
        self.length = None
        self.remaining_chunk = 0
        self.need_chunk_crlf = False
        self.complete = False

    def receive(self):
        part = self.sock.recv(16384)
        if part:
            self.buffer += part
        return bool(part)

    def take_until(self, marker, limit):
        while marker not in self.buffer:
            if len(self.buffer) > limit or not self.receive():
                raise http.client.HTTPException('incomplete/oversize HTTP metadata')
        value, self.buffer = self.buffer.split(marker, 1)
        if len(value) > limit:
            raise http.client.HTTPException('oversize HTTP metadata')
        return value

    def begin(self):
        self.raw_head = self.take_until(b'\r\n\r\n', 65536) + b'\r\n\r\n'
        lines = self.raw_head[:-4].split(b'\r\n')
        fields = lines.pop(0).split(b' ', 2)
        if len(fields) < 2 or fields[0] != b'HTTP/1.1':
            raise http.client.HTTPException('invalid HTTP status line')
        self.status = int(fields[1])
        for line in lines:
            if b':' not in line:
                raise http.client.HTTPException('invalid header')
            name, value = line.split(b':', 1)
            self.headers.append((name.decode('ascii'), value.strip().decode('latin1')))
        values = {}
        for name, value in self.headers:
            values.setdefault(name.lower(), []).append(value)
        transfer = values.get('transfer-encoding', [])
        lengths = values.get('content-length', [])
        if transfer and (transfer != ['chunked'] or lengths):
            raise http.client.HTTPException('ambiguous response framing')
        if len(lengths) > 1:
            raise http.client.HTTPException('duplicate Content-Length')
        self.chunked = bool(transfer)
        self.length = int(lengths[0]) if lengths else None
        if self.length is not None and self.length < 0:
            raise http.client.HTTPException('negative Content-Length')

    def getheaders(self):
        return self.headers

    def finish(self):
        # 所有本阶段请求显式 Connection: close；完整终态后不允许第二尾块或额外字节。
        if self.buffer or self.receive():
            raise http.client.HTTPException('trailing bytes after HTTP completion')
        self.complete = True
        return b''

    def read1(self, maximum):
        if self.complete:
            return b''
        if self.chunked:
            if self.need_chunk_crlf:
                if self.take_until(b'\r\n', 2) != b'':
                    raise http.client.HTTPException('invalid chunk terminator')
                self.need_chunk_crlf = False
            if not self.remaining_chunk:
                line = self.take_until(b'\r\n', 128)
                try:
                    if not line or any(char not in b'0123456789abcdefABCDEF' for char in line):
                        raise ValueError('chunk size')
                    self.remaining_chunk = int(line, 16)
                except ValueError as error:
                    raise http.client.HTTPException('invalid chunk size') from error
                if not self.remaining_chunk:
                    if self.take_until(b'\r\n', 2) != b'':
                        raise http.client.HTTPException('unexpected trailers')
                    return self.finish()
            wanted = min(maximum, self.remaining_chunk)
        elif self.length is not None:
            if not self.length:
                return self.finish()
            wanted = min(maximum, self.length)
        else:
            wanted = maximum
        if not self.buffer and not self.receive():
            if not self.chunked and self.length is None:
                self.complete = True
                return b''
            raise http.client.IncompleteRead(b'', wanted)
        part, self.buffer = self.buffer[:wanted], self.buffer[wanted:]
        if self.chunked:
            self.remaining_chunk -= len(part)
            self.need_chunk_crlf = self.remaining_chunk == 0
        elif self.length is not None:
            self.length -= len(part)
        return part

    def close(self):
        pass
