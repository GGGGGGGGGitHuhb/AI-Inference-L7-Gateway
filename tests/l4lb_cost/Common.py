"""Small shared primitives; existing S1 and HTTP parser remain unmodified."""
import hashlib
import json
import os
from pathlib import Path
import sys

TESTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS / 'l4lb'))
sys.path.insert(0, str(TESTS / 'integration'))
from RunTopology import Owned, free_ports, wait_for
from Identity import snapshot, sha
from WireResponse import WireResponse

COUNT = 240
WARMUP = 12
RATE = 60
SLOTS = 32


def require(value, detail):
    if not value:
        raise AssertionError(detail)


def body(identity, workload):
    if workload == 'A':
        value = json.dumps({'id': identity, 'value': 'x'}, separators=(',', ':')).encode()
        return value + b' ' * (1024 - len(value))
    parts = []
    for index in range(16):
        data = '[DONE]' if index == 15 else json.dumps({'id': identity, 'choices': [{'delta': {'content': 'x'}}]}, separators=(',', ':'))
        value = ('data: ' + data).encode()
        parts.append(value + b' ' * (1022 - len(value)) + b'\n\n')
    return b''.join(parts)


def request(identity, workload):
    data = json.dumps({'model': 'cost-model', 'messages': [{'role': 'user', 'content': identity}],
                       'stream': workload == 'B'}, separators=(',', ':')).encode()
    return (b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\n'
            b'Connection: close\r\nContent-Length: ' + str(len(data)).encode() + b'\r\n\r\n' + data)


def proc(pid):
    root = Path('/proc') / str(pid)
    fields = (root / 'stat').read_text().split(') ')[1].split()
    return {'pid': pid, 'ticks': int(fields[11]) + int(fields[12]),
            'rss_bytes': int((root / 'statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE'),
            'fds': len(list((root / 'fd').iterdir()))}


def write(path, data):
    encoded = json.dumps(data, indent=2).encode() + b'\n'
    # These caps plus at most eight 1MiB stdout/stderr files and backend.json
    # stay below the runner's 16MiB cell reservation even on failure.
    caps = {'requests.json': 2048, 'warm.json': 256, 'samples.json': 512,
            'processes.json': 128, 'boundary.json': 64, 'cleanup-errors.json': 64,
            'result.json': 128, 'backend.json': 1024, 'gateway-0.json': 64, 'gateway-1.json': 64,
            'summary.json': 128, 'not-started-ids.json': 1024, 'comparisons.json': 128,
            'identity.json': 256, 'plan.json': 1024}
    require(len(encoded) <= caps.get(Path(path).name, 2048) * 1024, 'structured artifact budget exceeded')
    with Path(path).open('xb') as file:
        file.write(encoded)


def digest(data):
    return hashlib.sha256(data).hexdigest()
