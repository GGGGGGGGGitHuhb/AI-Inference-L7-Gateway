"""Frozen V0.5/S2 topology cost matrix; all artifacts are task-local and bounded."""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
from types import SimpleNamespace

from Common import COUNT, WARMUP, RATE, SLOTS, Owned, free_ports, wait_for, proc, require, write, sha
from Client import attempt, unsent
from Analyze import audit, sessions, paired
from Skew import run as run_skew

MIB = 1024 * 1024


def reserve(output, amount=16 * MIB):
    used = sum(p.stat().st_size for p in Path(output).rglob('*') if p.is_file())
    require(used + amount + 4 * MIB <= 64 * MIB, '64MiB evidence budget: cannot reserve next cell')
    return used


def plan():
    result = []
    for workload in ('A', 'B'):
        for repeat, order in enumerate(('DML', 'MLD', 'LDM')):
            for path in order:
                result.append({'id': f'{workload}-{repeat}-{path}', 'workload': workload, 'repeat': repeat, 'path': path,
                               'ids': [f'{workload}-{repeat}-{path}-{phase}-{n:03}' for phase, count in [('w', WARMUP), ('f', COUNT)] for n in range(count)]})
    return result


class Sampler:
    def __init__(self, pids):
        self.pids = pids
        self.rows = []
        self.errors = []
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.loop)

    def sample(self):
        row = {'start_ns': time.monotonic_ns(), 'processes': {name: proc(pid) for name, pid in self.pids.items()}}
        row['end_ns'] = time.monotonic_ns()
        self.rows.append(row)

    def loop(self):
        while not self.stopped.wait(.1):
            try:
                self.sample()
            except Exception as error:
                self.errors.append(repr(error))
                return

    def start(self):
        self.sample()
        self.thread.start()

    def stop(self):
        self.stopped.set()
        self.thread.join(timeout=2)
        require(not self.thread.is_alive(), 'sampler remained')
        self.sample()
        require(not self.errors, 'sampling errors: ' + repr(self.errors))


class Cell:
    def __init__(self, spec, args, output):
        self.spec, self.args, self.output = spec, args, output
        self.output.mkdir()
        self.owned, self.gateways = [], []
        self.lb = None
        self.warm, self.rows, self.samples = [], [], []
        self.boundary = {}
        self.cleanup_errors = []
        self.pool = None
        self.pending = {}
        self.deadline = None

    def own(self, command, name, marker):
        owned = Owned(command, self.output, name)
        self.owned.append(owned)
        owned.ready(marker)
        return owned

    def setup(self):
        backend_port, lb_port, *gateway_ports = free_ports(4)
        self.backend = self.own([sys.executable, str(Path(__file__).parent / 'Backend.py'), '--port', str(backend_port),
                                 '--workload', self.spec['workload'], '--output', str(self.output / 'backend.json')], 'backend', 'READY')
        count = 1 if self.spec['path'] == 'D' else 2
        for index in range(count):
            capacity = 32 // count
            config = {'listen_address': '127.0.0.1', 'listen_port': gateway_ports[index], 'max_connections': 64,
                      'models': [{'name': 'cost-model', 'policy': 'round_robin', 'backends': [
                          {'id': 'shared', 'address': '127.0.0.1', 'port': backend_port}]}],
                      'health': {'failure_threshold': 2, 'cooldown_ms': 1000},
                      'upstream_pool': {'max_connections': capacity, 'max_idle': 0, 'idle_timeout_ms': 1000},
                      'admission': {'max_inflight': capacity, 'max_inflight_per_backend': capacity,
                                    'max_queue_requests_per_model': 0, 'max_queue_bytes_per_model': 65536, 'queue_timeout_ms': 1000}}
            path = self.output / f'gateway-{index}.json'
            write(path, config)
            self.gateways.append(self.own([self.args.gateway, '--config', str(path)], f'gateway-{index}', 'READY '))
        self.targets = gateway_ports[:count]
        if self.spec['path'] == 'L':
            path = self.output / 'l4lb.conf'
            path.write_text(f'protocol=tcp\nlisten=127.0.0.1:{lb_port}\n' + ''.join(f'backend=127.0.0.1:{p}\n' for p in gateway_ports) +
                            'scheduler=round_robin\nhealth_check=tcp_connect\nmetrics=off\n')
            self.lb = self.own([self.args.l4lb, '--run', str(path)], 'l4lb', 'TCP 服务已启动')
            wait_for(lambda: self.lb.text(True).count('to=Healthy') == 2, 'L4 warm health', 12)
            self.targets = [lb_port]
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=SLOTS)

    def batch(self, phase, count, start):
        rows, jobs = [], []
        slots = threading.BoundedSemaphore(SLOTS)
        guard = self.deadline
        try:
            for n in range(count):
                scheduled = start + int(n / RATE * 1e9)
                delay = (scheduled - time.monotonic_ns()) / 1e9
                if delay > 0:
                    time.sleep(delay)
                require(time.monotonic() < guard, 'cell batch deadline')
                identity = f'{self.spec["id"]}-{phase}-{n:03}'
                target = self.targets[n % len(self.targets)]
                if slots.acquire(blocking=False):
                    future = self.pool.submit(attempt, identity, scheduled, target, self.spec['workload'])
                    future.add_done_callback(lambda _: slots.release())
                    jobs.append(future)
                    self.pending[identity] = future
                else:
                    rows.append(unsent(identity, scheduled, target, 'not_sent'))
            for future in jobs:
                rows.append(future.result(timeout=max(.001, guard - time.monotonic())))
        finally:
            # Every ID remains represented even if the batch is interrupted.
            cleanup_deadline = time.monotonic() + 5.5
            for future in jobs:
                try:
                    row = future.result(timeout=max(.001, cleanup_deadline - time.monotonic()))
                except concurrent.futures.TimeoutError:
                    continue  # close() collects the actual result after bounded request shutdown.
                if row['id'] not in {r['id'] for r in rows}:
                    rows.append(row)
            ids = {r['id'] for r in rows}
            for n in range(count):
                identity = f'{self.spec["id"]}-{phase}-{n:03}'
                if identity not in ids:
                    state = 'interrupted_unknown' if identity in self.pending else 'not_started'
                    placeholder = unsent(identity, start + int(n / RATE * 1e9), self.targets[n % len(self.targets)], state)
                    if state == 'interrupted_unknown':
                        placeholder['tx_bytes'] = placeholder['rx_bytes'] = None
                    rows.append(placeholder)
            rows.sort(key=lambda r: r['id'])
            if phase == 'w':
                self.warm = rows
            else:
                self.rows = rows
        return rows

    def drain_l4(self, count):
        if self.lb:
            wait_for(lambda: len(sessions(self.lb.text(True))[1]) == count, 'L4 closed sessions')

    def measure(self):
        self.batch('w', WARMUP, time.monotonic_ns() + 100_000_000)
        self.drain_l4(WARMUP)
        self.boundary['warm_sessions'] = list(sessions(self.lb.text(True))[0]) if self.lb else []
        sampler = Sampler({**{p.name: p.process.pid for p in self.owned}, 'client': os.getpid()})
        sampler.start()
        try:
            start = time.monotonic_ns() + 100_000_000
            self.boundary['scheduled_start_ns'] = start
            self.batch('f', COUNT, start)
            self.drain_l4(COUNT + WARMUP)
            for owned in [*self.gateways, *([self.lb] if self.lb else [])]:
                wait_for(lambda: proc(owned.process.pid)['fds'] <= owned.baseline_fd + 2, owned.name + ' FD drain')
        finally:
            sampler.stop()
            self.samples = sampler.rows

    def close(self):
        if self.pool:
            self.pool.shutdown(wait=True, cancel_futures=True)
            for rows in (self.warm, self.rows):
                for index, row in enumerate(rows):
                    future = self.pending.get(row['id'])
                    if future is not None and not future.cancelled():
                        rows[index] = future.result()
        processes = []
        for owned in reversed(self.owned):
            try:
                value = owned.close()
                processes.append(value)
                if value['exit'] != 0 or value['forced_cleanup']:
                    self.cleanup_errors.append(value)
            except Exception as error:
                self.cleanup_errors.append({'name': owned.name, 'error': repr(error)})
        for filename, data in [('processes.json', processes), ('warm.json', self.warm), ('requests.json', self.rows),
                               ('samples.json', self.samples), ('boundary.json', self.boundary), ('cleanup-errors.json', self.cleanup_errors)]:
            write(self.output / filename, data)

    def run(self):
        error = None
        result = None
        active_started = time.monotonic()
        self.deadline = active_started + 30
        outer_timer = signal.getitimer(signal.ITIMER_REAL)[0]
        signal.setitimer(signal.ITIMER_REAL, min(30, outer_timer) if outer_timer else 30)
        try:
            self.setup()
            self.measure()
        except Exception as failure:
            error = repr(failure)
        finally:
            # No active workload is allowed beyond 30s; cleanup has its own finite grace.
            signal.setitimer(signal.ITIMER_REAL, 0)
            self.close()
            if outer_timer:
                remaining = outer_timer - (time.monotonic() - active_started)
                if remaining <= 0:
                    error = str(error) + '; global deadline exceeded'
                else:
                    signal.setitimer(signal.ITIMER_REAL, remaining)
        try:
            require(error is None and not self.cleanup_errors, str(error) + str(self.cleanup_errors))
            result = audit(self.spec, self.warm, self.rows, json.loads((self.output / 'backend.json').read_text()),
                           self.samples, self.boundary, self.lb.text(True) if self.lb else '')
        except Exception as failure:
            error = repr(failure)
        write(self.output / 'result.json', {'status': 'FAIL' if error else 'PASS', 'error': error, 'summary': result})
        require(error is None, self.spec['id'] + ': ' + str(error))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--l4lb', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    args.gateway, args.l4lb = str(Path(args.gateway).resolve()), str(Path(args.l4lb).resolve())
    for binary in (args.gateway, args.l4lb):
        require(Path(binary).is_file() and os.access(binary, os.X_OK), 'executable missing')
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'plan.json', plan())
    write(output / 'identity.json', {'gateway': sha(args.gateway), 'l4lb': sha(args.l4lb),
          'tools': {p.name: sha(p) for p in Path(__file__).parent.glob('*.py')},
          'clock_ticks': os.sysconf('SC_CLK_TCK'), 'affinity_cpus': sorted(os.sched_getaffinity(0))})
    started = time.monotonic()
    def interrupted(signum, frame):
        raise RuntimeError(f'run signal {signum}')
    signal.signal(signal.SIGALRM, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    signal.alarm(600)
    results, error, skew = [], None, None
    try:
        for cell in plan():
            reserve(output)
            result = Cell(cell, args, output / cell['id']).run()
            results.append(result)
            print('PASS', cell['id'], 'p95_ms', round(result['e2e_ms']['p95'], 3), 'limited', result['quality_limited'], flush=True)
        reserve(output)
        skew = run_skew(SimpleNamespace(gateway=args.gateway, l4lb=args.l4lb, output=str(output / 'skew')))
        write(output / 'comparisons.json', paired(results))
    except Exception as failure:
        error = repr(failure)
    finally:
        signal.alarm(0)
        represented_ids = set()
        recorded_not_started = 0
        for path in list(output.glob('*/warm.json')) + list(output.glob('*/requests.json')):
            rows = json.loads(path.read_text())
            represented_ids.update(r['id'] for r in rows)
            recorded_not_started += sum(r['outcome'] == 'not_started' for r in rows)
        missing = [identity for cell in plan() for identity in cell['ids'] if identity not in represented_ids]
        write(output / 'not-started-ids.json', missing)
        total = sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
        if total > 64 * MIB:
            error = str(error) + '; evidence budget exceeded'
        result = {'status': 'FAIL' if error else 'PASS', 'error': error, 'cells': len(results),
                  'planned_application_requests': 18 * (COUNT + WARMUP), 'seconds': time.monotonic() - started,
                  'quality_limited_cells': [r['id'] for r in results if r['quality_limited']],
                  'skew': skew, 'bytes_before_summary': total, 'not_started': len(missing) + recorded_not_started}
        write(output / 'summary.json', result)
    print(json.dumps(result), flush=True)
    return int(error is not None)


if __name__ == '__main__':
    raise SystemExit(main())
