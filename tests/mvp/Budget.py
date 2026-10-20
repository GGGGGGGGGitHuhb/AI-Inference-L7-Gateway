"""Run-wide storage partition: 96 MiB direct + 28 MiB managed + 4 MiB emergency.

Direct paths reserve their entire hard RLIMIT_FSIZE allowance before spawning.
Managed writes charge cumulative bytes (including replacements) before writing.
Thus even partial/atomic/failed writes cannot exceed the partition sum.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

ACTIVE = None


class BudgetExceeded(RuntimeError):
    pass


class RunBudget:
    def __init__(self, root, direct=96*1024**2, managed=28*1024**2,
                 emergency=4*1024**2, file_limit=4*1024**2):
        self.root = Path(root).resolve()
        self.limits = dict(direct=direct, managed=managed, emergency=emergency)
        self.used = dict(direct=0, managed=0, emergency=0)
        self.file_limit = file_limit
        self.lock = threading.RLock()
        self.error = None
        self.direct_paths = set()
        self.children = []
        self.done = threading.Event()
        self.previous = None

    def __enter__(self):
        global ACTIVE
        if ACTIVE is not None:
            raise RuntimeError('nested run budget')
        ACTIVE = self
        self.previous = signal.signal(signal.SIGUSR1, self.interrupt)
        self.monitor = threading.Thread(target=self.watch, daemon=True)
        self.monitor.start()
        return self

    def interrupt(self, signum, frame):
        raise BudgetExceeded(self.error or 'storage budget exceeded')

    def fail(self, message):
        first = False
        with self.lock:
            if self.error is None:
                self.error = message
                first = True
        if first:
            for child in list(self.children):
                if child.poll() is None:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            if threading.current_thread() is not threading.main_thread():
                os.kill(os.getpid(), signal.SIGUSR1)
        raise BudgetExceeded(self.error)

    def check(self):
        if self.error:
            raise BudgetExceeded(self.error)
        for path in tuple(self.direct_paths):
            if path.exists() and path.stat().st_size >= self.file_limit:
                self.fail('direct output reached hard limit: ' + path.name)

    def charge(self, size, partition):
        with self.lock:
            if partition != 'emergency':
                self.check()
            if self.used[partition] + size > self.limits[partition]:
                self.fail('storage budget exhausted: ' + partition)
            self.used[partition] += size

    def path(self, path):
        path = Path(path).resolve()
        if not path.is_relative_to(self.root):
            raise RuntimeError('output outside run budget')
        return path

    def write(self, path, data, mode='wb', emergency=False):
        path = self.path(path)
        with self.lock:
            if path in self.direct_paths:
                raise RuntimeError('direct path cannot have managed writer')
            self.charge(len(data), 'emergency' if emergency else 'managed')
            with path.open(mode) as stream:
                stream.write(data)

    def reserve_direct(self, paths):
        paths = {self.path(p) for p in paths}
        with self.lock:
            if paths & self.direct_paths or any(p.exists() for p in paths):
                raise RuntimeError('direct output already exists')
            self.charge(len(paths)*self.file_limit, 'direct')
            self.direct_paths.update(paths)

    def watch(self):
        try:
            while not self.done.wait(.01):
                for path in tuple(self.direct_paths):
                    try:
                        if path.stat().st_size >= self.file_limit:
                            self.fail('direct output reached hard limit: ' + path.name)
                    except FileNotFoundError:
                        pass
        except BudgetExceeded:
            pass

    def finish(self):
        if any(child.poll() is None for child in self.children):
            self.fail('live child at run completion')
        self.check()

    def __exit__(self, kind, value, traceback):
        global ACTIVE
        self.done.set()
        self.monitor.join(1)
        for child in self.children:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(5)
        # Final check covers a last write followed by immediate child exit.
        for path in self.direct_paths:
            if path.exists() and path.stat().st_size >= self.file_limit:
                self.error = self.error or 'direct output reached hard limit: ' + path.name
        signal.signal(signal.SIGUSR1, self.previous)
        ACTIVE = None
        if kind is None:
            self.check()


def write(path, data, mode='wb', emergency=False):
    if ACTIVE:
        ACTIVE.write(path, data, mode, emergency)
    else:
        with Path(path).open(mode) as destination:
            destination.write(data)


def save(path, value):
    name = Path(path).name
    emergency = name in ('result.json', 'cleanup-errors.json', 'budget-error.json')
    write(path, json.dumps(value, indent=2, ensure_ascii=False).encode(), emergency=emergency)


def append(path, value):
    write(path, (json.dumps(value, ensure_ascii=False)+'\n').encode(), 'ab',
          emergency=Path(path).name == 'processes.jsonl')


def save_attempt(path, row):
    try:
        write(path, json.dumps(row, indent=2).encode(), 'xb')
    except BudgetExceeded as error:
        # The bounded failure record preserves identity, error, bytes/hash and prefix.
        # Never silently truncate a successful sample or claim its body is complete.
        failed = {k: row.get(k) for k in ('id', 'group', 'cohort', 'expected', 'started', 'ended',
                  'status', 'request_sha256', 'bytes', 'body_sha256', 'client_port')}
        failed.update(outcome='failure', complete=False, storage_error=str(error),
                      error=str(row.get('error'))[:4096], body_prefix=row.get('body', '')[:4096],
                      evidence_truncated=True)
        row.update(outcome='failure', complete=False, persistence_error=str(error))
        write(path, json.dumps(failed, ensure_ascii=True).encode(), 'xb', emergency=True)


class OwnedProcess:
    def __init__(self, command, log, record, direct_paths=()):
        self.command = [str(v) for v in command]
        self.record = record
        self.stopped = False
        budget = ACTIVE
        if budget:
            budget.reserve_direct([log, *direct_paths])
        self.log = open(log, 'wb')
        launch = (['/usr/bin/prlimit', '--core=0:0', '--fsize=' + str(budget.file_limit) + ':' +
                   str(budget.file_limit), '--'] + self.command) if budget else self.command
        try:
            self.process = subprocess.Popen(launch, stdout=self.log, stderr=self.log,
                start_new_session=True)
            if budget:
                budget.children.append(self.process)
            append(record, {'event': 'start', 'pid': self.process.pid,
                            'command': self.command, 'time': time.time()})
        except BaseException:
            if hasattr(self, 'process'):
                self.stop()
            self.log.close()
            raise

    def stop(self, signum=signal.SIGTERM):
        if self.stopped:
            return
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signum)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(5)
        self.log.close()
        self.stopped = True
        append(self.record, {'event': 'reaped', 'pid': self.process.pid,
                            'exit': self.process.returncode, 'time': time.time()})
