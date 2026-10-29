"""Owned process lifecycle, rotating lossless capture and cumulative reservations."""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import threading
import time
import traceback
from Common import Chunks, MIB, now, proc, write


class Ledger:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.budget_root = self.root.parent if self.root.name == 'run' else self.root
        self.path = self.root / 'ledger.json'
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {'cells': [], 'active_seconds': 0}

    def save(self):
        tmp = self.path.with_suffix('.next')
        with tmp.open('w') as handle:
            json.dump(self.data, handle, indent=2)
        tmp.replace(self.path)

    def reserve(self, spec):
        if any(row['id'] == spec['id'] for row in self.data['cells']) or (self.root / spec['id']).exists():
            raise RuntimeError('duplicate cell output')
        if any(row['state'] == 'running' for row in self.data['cells']):
            raise RuntimeError('unclosed previous cell: investigate retained reservation')
        limits = {'E1': 28, 'E2': 8, 'formal': 72, 'diagnostic': 12}
        # E0 negative controls are charged to diagnostics, never an extra allocation.
        kind = spec['kind']
        if len(self.data['cells']) >= 120 or sum(row['kind'] == kind for row in self.data['cells']) >= limits[kind]:
            raise RuntimeError('cell count budget')
        if self.data['active_seconds'] + 45 > 90 * 60:
            raise RuntimeError('active time budget')
        count = int(spec['rate'] * (spec['warm'] + spec['duration']))
        reservation = count * (512 + 192 * spec.get('backend_workers', 1) + (256 if spec['path'] == 'L' else 0)) + 3 * MIB
        used = sum(p.stat().st_size for p in self.budget_root.rglob('*') if p.is_file())
        if used + reservation + 16 * MIB > 2 * 1024 * MIB:
            raise RuntimeError('evidence reservation budget')
        row = {'id': spec['id'], 'kind': kind, 'reserved': reservation, 'used_before': used,
               'state': 'running', 'started_ns': now(), 'spec': spec}
        self.data['cells'].append(row)
        # Charge the whole 45-second reservation before launch: crashes never refund it.
        self.data['active_seconds'] += 45
        self.save()
        return row

    def close(self, row, elapsed, state):
        row.update(state=state, elapsed_seconds=elapsed)
        self.data['active_seconds'] -= max(0, 45 - elapsed)
        self.save()


class Owned:
    def __init__(self, command, name, root, limit):
        self.name = name
        self.capture = Chunks(root, 'log-' + name, limit)
        self.tail = bytearray()
        self.error = None
        self.blocks = self.bytes = self.read_ns = self.write_ns = 0
        self.command = command
        # Child address-space ceilings bound startup; aggregate RSS/FD is checked live.
        command = ['prlimit', '--as=134217728', '--nofile=600', '--', *command]
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
        self.thread = threading.Thread(target=self.read, name='capture-' + name, daemon=True)
        self.thread.start()
        self.baseline_fd = None

    def read(self):
        try:
            while True:
                start = now()
                data = self.process.stdout.read(32768)
                self.read_ns += now() - start
                if not data:
                    break
                start = now()
                self.capture.put(data)
                self.write_ns += now() - start
                self.bytes += len(data)
                self.blocks += 1
                self.tail = (self.tail + data)[-32768:]
        except Exception as error:
            self.error = repr(error)
        finally:
            self.capture.close()
            self.process.stdout.close()

    def ready(self, marker, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.error or self.process.poll() is not None:
                raise RuntimeError(self.name + ' startup: ' + self.tail.decode(errors='replace'))
            if marker.encode() in self.tail:
                self.baseline_fd = proc(self.process.pid)['fds']
                return
            time.sleep(.01)
        raise RuntimeError(self.name + ' readiness timeout')

    def close(self):
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        self.thread.join(timeout=2)
        if self.thread.is_alive() or self.error:
            raise RuntimeError('capture failed ' + self.name + ': ' + str(self.error))
        return {'name': self.name, 'pid': self.process.pid, 'returncode': self.process.returncode,
                'capture_bytes': self.bytes, 'capture_blocks': self.blocks, 'capture_write_ns': self.write_ns,
                'capture_read_wait_ns': self.read_ns, 'capture_loss_bytes': 0}


class Monitor:
    def __init__(self, owned, root, interval=.1):
        self.owned = owned
        self.interval = interval
        self.stop = threading.Event()
        self.error = None
        self.output = Chunks(root, 'resources', 2 * MIB)
        self.events = Chunks(root, 'monitor-events', 65536, row_limit=8192)
        self.phase = 'setup'
        self.windows = None
        self.activity_deadline_ns = now() + 45_000_000_000
        self.failure_recorded = False
        self.thread = threading.Thread(target=self.loop, name='resource-monitor', daemon=True)
        self.thread.start()

    def observed_phase(self, stamp):
        phase = self.phase
        if phase == 'requests' and self.windows:
            phase = 'warmup' if stamp < self.windows[0] else ('measurement' if stamp < self.windows[1] else 'request-drain')
        return phase

    def record_error(self, name, pid, error, action, returncode=None, stamp=None, wait_info=None, original_phase=None):
        stamp = now() if stamp is None else stamp
        self.events.row({'time_ns': stamp, 'name': name, 'pid': pid, 'phase': original_phase or self.observed_phase(stamp),
                         'exception_type': type(error).__name__, 'exception': repr(error),
                         'traceback': ''.join(traceback.format_exception(type(error), error, error.__traceback__)),
                         'action': action, 'returncode': returncode, **(wait_info or {})})

    def snapshot(self, name, pid, owned=None):
        try:
            return proc(pid)
        except Exception as error:
            stamp = now()
            phase = self.observed_phase(stamp)
            returncode = owned.process.poll() if owned is not None else None
            wait_info = {'initial_returncode': returncode, 'exit_wait_start_ns': None,
                         'exit_wait_end_ns': None, 'exit_wait_elapsed_ns': 0,
                         'exit_wait_timed_out': False, 'exit_wait_error': None}
            exit_read_outside = bool(owned is not None and self.windows and stamp >= self.windows[1]
                                      and phase in ('request-drain', 'fd-drain', 'cleanup'))
            exit_read_error = isinstance(error, (PermissionError, FileNotFoundError, ProcessLookupError))
            if exit_read_error and exit_read_outside and returncode is None:
                wait_info['exit_wait_start_ns'] = now()
                timeout = min(.1, max(0, (getattr(self, 'activity_deadline_ns', wait_info['exit_wait_start_ns'] + 100_000_000) - wait_info['exit_wait_start_ns']) / 1e9))
                wait_info['exit_wait_timeout_seconds'] = timeout
                try:
                    if timeout <= 0:
                        raise subprocess.TimeoutExpired('cell activity deadline', 0)
                    returncode = owned.process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    wait_info['exit_wait_timed_out'] = True
                except Exception as wait_error:
                    wait_info['exit_wait_error'] = repr(wait_error)
                finally:
                    wait_info['exit_wait_end_ns'] = now()
                    wait_info['exit_wait_elapsed_ns'] = wait_info['exit_wait_end_ns'] - wait_info['exit_wait_start_ns']
            exited = (exit_read_error and exit_read_outside and returncode is not None)
            self.record_error(name, pid, error, 'skip-confirmed-exit' if exited else 'fatal', returncode, stamp, wait_info, phase)
            if exited:
                return None
            self.failure_recorded = True
            raise

    def loop(self):
        try:
            while not self.stop.is_set():
                start = now()
                processes = {'controller': self.snapshot('controller', os.getpid())}
                for owned in list(self.owned):
                    if owned.process.poll() is None:
                        value = self.snapshot(owned.name, owned.process.pid, owned)
                        if value is not None:
                            processes[owned.name] = value
                self.output.row({'start': start, 'end': now(), 'processes': processes})
                if sum(p['rss'] for p in processes.values()) > 1024 * MIB:
                    raise RuntimeError('aggregate RSS budget')
                if sum(p['fds'] for p in processes.values()) > 2048:
                    raise RuntimeError('aggregate FD budget')
                self.stop.wait(self.interval)
        except Exception as error:
            self.error = repr(error)
            if not self.failure_recorded:
                try:
                    self.record_error('monitor', os.getpid(), error, 'fatal')
                except Exception as evidence_error:
                    self.error += '; error-evidence ' + repr(evidence_error)
        finally:
            self.output.close()
            self.events.close()

    def check(self):
        if self.error:
            raise RuntimeError(self.error)
        for owned in self.owned:
            if owned.error:
                raise RuntimeError(owned.error)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        self.check()
