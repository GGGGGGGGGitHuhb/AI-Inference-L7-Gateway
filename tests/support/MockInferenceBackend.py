"""S1 deterministic loopback-only backend; fixed synthetic fixtures only."""
import argparse
import json
import socket
import time
from pathlib import Path

BODY = b'{"result":"mock"}'


def response_fragments(scenario):
    normal = b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(BODY)).encode() + b"\r\nContent-Type: application/json\r\n\r\n" + BODY
    if scenario == "fixed":
        return [normal]
    if scenario == "chunked":
        return [b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n", hex(len(BODY))[2:].encode() + b"\r\n", BODY, b"\r\n0\r\n\r\n"]
    if scenario == "delayed":
        return [normal[index:index + 7] for index in range(0, len(normal), 7)]
    if scenario == "truncated":
        return [normal[:-4]]
    return [b"HTTP/1.1 200 OK\r\nBad Header: x\r\nContent-Length: 0\r\n\r\n"]


def serve(scenario, record):
    with socket.socket() as listener:
        listener.settimeout(5)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        print(json.dumps({"host": "127.0.0.1", "port": listener.getsockname()[1]}), flush=True)
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(5)
            request = bytearray()
            while b"\r\n\r\n" not in request:
                fragment = connection.recv(1024)
                if not fragment or len(request) + len(fragment) > 16384:
                    raise RuntimeError("invalid fixture request")
                request.extend(fragment)
            Path(record).write_bytes(request)
            for fragment in response_fragments(scenario):
                connection.sendall(fragment)
                if scenario == "delayed":
                    time.sleep(0.002)


if __name__ == "__main__":
    arguments = argparse.ArgumentParser()
    arguments.add_argument("--scenario", choices=["fixed", "chunked", "delayed", "truncated", "malformed"], required=True)
    arguments.add_argument("--record", required=True)
    options = arguments.parse_args()
    serve(options.scenario, options.record)
