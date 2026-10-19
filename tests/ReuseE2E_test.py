import concurrent.futures
import json
import os
import signal
import socket
import struct
import sys
import tempfile
import time
from support.PersistentBackend import PersistentBackend
from support.ReuseHarness import GatewayProcess, request_wire, receive

EXE = sys.argv[1]
checks = 0


def check(condition, context=""):
    global checks
    checks += 1
    assert condition, context


def exchange(gateway, marker):
    with gateway.client() as client:
        client.sendall(request_wire(marker))
        return receive(client)


def verify(result, marker, status=200):
    headers, body = result.split(b"\r\n\r\n", 1)
    expected = b"" if status in (204, 304) else json.dumps({"echo": marker}, separators=(",", ":")).encode()
    check(headers.startswith(b"HTTP/1.1 " + str(status).encode()), result[:100])
    check(body == expected and result.count(b"HTTP/1.1 ") == 1, (body, expected))


def sequential(directory):
    for mode in ["fixed", "chunked", "informational", "204", "304", "400", "500"]:
        backend = PersistentBackend(directory, mode)
        gateway = GatewayProcess(EXE, directory, backend)
        try:
            for index in range(20):
                marker = mode + "-" + str(index)
                verify(exchange(gateway, marker), marker, int(mode) if mode.isdigit() else 200)
            check(backend.counts() == {"accepts": 1, "requests": 20}, (mode, backend.counts()))
            print("sequential", mode, backend.counts())
        finally:
            try: gateway.close()
            finally: backend.close()


def invalidation(directory):
    for mode in ["close", "eof", "trailing", "late", "fin", "rst", "truncated"]:
        backend = PersistentBackend(directory, mode)
        gateway = GatewayProcess(EXE, directory, backend)
        try:
            for index in range(3):
                marker = mode + str(index)
                result = exchange(gateway, marker)
                if mode == "truncated": check(result.startswith(b"HTTP/1.1 502"))
                else: verify(result, marker)
                if mode in ("late", "fin", "rst"): time.sleep(.07)
            check(backend.counts() == {"accepts": 3, "requests": 3}, (mode, backend.counts()))
            print("invalidation", mode, backend.counts())
        finally:
            try: gateway.close()
            finally: backend.close()
    for pool in [{"max_connections": 2, "max_idle": 0}, {"max_connections": 2, "max_idle": 1, "idle_timeout_ms": 10}]:
        backend = PersistentBackend(directory)
        gateway = GatewayProcess(EXE, directory, backend, upstream_pool=pool)
        try:
            for index in range(3):
                verify(exchange(gateway, str(index)), str(index)); time.sleep(.04)
            check(backend.accepts.value == 3)
        finally:
            try: gateway.close()
            finally: backend.close()


def capacity(directory):
    backend = PersistentBackend(directory, delay=.15)
    gateway = GatewayProcess(EXE, directory, backend, max_connections=8, upstream_pool={"max_connections": 2, "max_idle": 1})
    first = gateway.client(); second = gateway.client()
    try:
        first.sendall(request_wire("first")); second.sendall(request_wire("second"))
        deadline = time.monotonic() + 2
        while backend.requests.value != 2 and time.monotonic() < deadline: time.sleep(.001)
        check(backend.requests.value == 2)
        started = time.monotonic()
        result = exchange(gateway, "capacity-rejected")
        check(result.startswith(b"HTTP/1.1 503") and b"upstream_capacity" in result, result)
        check(time.monotonic() - started < .12)
        check(backend.requests.value == 2)
        verify(receive(first), "first"); verify(receive(second), "second")
        first.close(); second.close()
        verify(exchange(gateway, "recovery"), "recovery")
        check(backend.counts() == {"accepts": 2, "requests": 3}, backend.counts())
        records = [json.loads(row) for row in backend.record_path.read_text().splitlines()]
        check(all(row["marker"] != "capacity-rejected" for row in records))
    finally:
        first.close(); second.close()
        try: gateway.close()
        finally: backend.close()


def closing_isolation(directory):
    backend = PersistentBackend(directory)
    gateway = GatewayProcess(EXE, directory, backend)
    old = gateway.client()
    try:
        old.sendall(request_wire("old")); verify(receive(old), "old")
        verify(exchange(gateway, "new"), "new")
        old.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)); old.close()
        verify(exchange(gateway, "after-old-reset"), "after-old-reset")
        check(backend.counts() == {"accepts": 1, "requests": 3}, backend.counts())
    finally:
        old.close()
        try: gateway.close()
        finally: backend.close()


def stop_paths(directory):
    for force in [False, True]:
        backend = PersistentBackend(directory, delay=.05)
        gateway = GatewayProcess(EXE, directory, backend, timeouts_ms={"shutdown": 150})
        try:
            verify(exchange(gateway, "idle"), "idle")
            pending = gateway.client(); pending.sendall(b"POST ")
            time.sleep(.02)
            gateway.process.send_signal(signal.SIGTERM)
            time.sleep(.02)
            if force:
                gateway.process.send_signal(signal.SIGINT)
                check(receive(pending) == b"")
            else:
                pending.sendall(request_wire("stopping")[5:])
                result = receive(pending)
                check(result.startswith(b"HTTP/1.1 503") and b"gateway_stopping" in result, result)
            pending.close()
            check(backend.requests.value == 1)
            gateway.process.wait(timeout=2) # Explicit signal already sent; do not signal again during sanitizer teardown.
        finally:
            try: gateway.close()
            finally: backend.close()


with tempfile.TemporaryDirectory(prefix="reuse-e2e-", dir=os.environ["TMPDIR"]) as directory:
    sequential(directory)
    invalidation(directory)
    capacity(directory)
    closing_isolation(directory)
    stop_paths(directory)
print("S3 real socket checks", checks)
