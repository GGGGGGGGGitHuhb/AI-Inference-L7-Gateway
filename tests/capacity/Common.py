"""Bounded artifacts and exact workload bytes; no product or old-tool imports."""
import hashlib
import json
import os
from pathlib import Path
import time

MIB = 1024 * 1024
COLUMNS = ['id', 'phase', 'scheduled', 'dispatch', 'connect', 'send', 'wire', 'body',
           'http', 'eof', 'closed', 'outcome', 'status', 'tx', 'rx', 'digest', 'error']


def payload(identity, workload):
    if workload == 'A':
        data = json.dumps({'id': identity, 'value': 'x'}, separators=(',', ':')).encode()
        return data + b' ' * (1024 - len(data))
    parts = []
    for i in range(16):
        data = '[DONE]' if i == 15 else json.dumps({'id': identity, 'choices': [{'delta': {'content': 'x'}}]}, separators=(',', ':'))
        data = ('data: ' + data).encode()
        parts.append(data + b' ' * (1022 - len(data)) + b'\n\n')
    return b''.join(parts)


def request(identity, workload, close=True):
    data = json.dumps({'model': 'capacity-model', 'messages': [{'role': 'user', 'content': identity}],
                       'stream': workload == 'S'}, separators=(',', ':')).encode()
    return (b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nConnection: '
            + (b'close' if close else b'keep-alive') + b'\r\nContent-Length: ' + str(len(data)).encode() + b'\r\n\r\n' + data)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data, limit=MIB):
    data = json.dumps(data, indent=2).encode() + b'\n'
    if len(data) > limit:
        raise RuntimeError('single artifact exceeds 1MiB')
    with Path(path).open('xb') as handle:
        handle.write(data)


class Chunks:
    """Each writer receives an exclusive reservation, preventing concurrent overspend."""
    def __init__(self, root, prefix, limit, row_limit=None):
        self.root, self.prefix, self.limit = Path(root), prefix, limit
        self.row_limit = row_limit
        self.total = self.size = self.index = 0
        self.file = None

    def put(self, data):
        if len(data) > MIB or self.total + len(data) > self.limit:
            raise RuntimeError('artifact reservation exceeded: ' + self.prefix)
        if self.file is None or self.size + len(data) > MIB:
            if self.file:
                self.file.close()
            self.file = (self.root / f'{self.prefix}-{self.index:04d}.jsonl').open('xb')
            self.index += 1
            self.size = 0
        self.file.write(data)
        self.total += len(data)
        self.size += len(data)

    def row(self, data):
        encoded = json.dumps(data, separators=(',', ':')).encode() + b'\n'
        if self.row_limit is not None and len(encoded) > self.row_limit:
            raise RuntimeError('record hard cap exceeded: ' + self.prefix)
        self.put(encoded)

    def close(self):
        if self.file:
            self.file.close()


def rows(root, prefix):
    for path in sorted(Path(root).glob(prefix + '-*.jsonl')):
        with path.open() as handle:
            for line in handle:
                yield json.loads(line)


def proc(pid):
    root = Path('/proc') / str(pid)
    fields = (root / 'stat').read_text().split(') ')[1].split()
    threads = {}
    missing_threads = []
    for path in (root / 'task').glob('*/stat'):
        try:
            values = path.read_text().split(') ')[1].split()
        except (FileNotFoundError, ProcessLookupError):
            try:
                path.parent.stat()
            except (FileNotFoundError, ProcessLookupError):
                missing_threads.append(path.parent.name)
                continue
            raise
        threads[path.parent.name] = int(values[11]) + int(values[12])
    result = {'pid': pid, 'ticks': int(fields[11]) + int(fields[12]), 'threads': threads,
            'rss': int((root / 'statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE'),
            'fds': len(list((root / 'fd').iterdir())), 'affinity': sorted(os.sched_getaffinity(pid))}
    if missing_threads:
        result['unavailable_exited_threads'] = missing_threads
    return result


def now():
    return time.monotonic_ns()
