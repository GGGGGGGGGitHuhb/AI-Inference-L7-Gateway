"""Bounded closed-loop workers and passive /proc sampling (not an admission gate)."""
import concurrent.futures
import json
import multiprocessing
import os
import pathlib
import queue
import threading
import time
from Client import attempt, request_bytes

CANCEL = threading.Event()
CURRENT_CANCEL = None


def request_cancel():
    CANCEL.set()
    if CURRENT_CANCEL is not None:
        CURRENT_CANCEL.set()


def process_sample(pid):
    root = pathlib.Path('/proc') / str(pid)
    try:
        stat = (root / 'stat').read_text().split(') ')[1].split()
        status = (root / 'status').read_text().splitlines()
        return {'pid': pid, 'cpu_seconds': (int(stat[11]) + int(stat[12])) / os.sysconf('SC_CLK_TCK'),
            'rss_bytes': int((root / 'statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE'),
            'fd': len(list((root / 'fd').iterdir())),
            'context_switches': {line.split(':')[0]: int(line.split(':')[1]) for line in status
                                if 'ctxt_switches:' in line}}
    except (FileNotFoundError, ProcessLookupError):
        return None


class Sampler:
    def __init__(self, pids, interval):
        self.pids, self.interval = pids, interval
        self.rows, self.stop_event = [], threading.Event()
        self.cost_ns = 0
        self.thread = threading.Thread(target=self.loop)

    def sample(self):
        start = time.monotonic_ns()
        self.rows.append({'time_ns': start, 'loadavg': pathlib.Path('/proc/loadavg').read_text().strip(),
            'system_cpu_ticks': list(map(int, pathlib.Path('/proc/stat').read_text().splitlines()[0].split()[1:])),
            'mem_available_kib': next(int(line.split()[1]) for line in
                pathlib.Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')),
            'processes': {name: process_sample(pid) for name, pid in self.pids.items()}})
        self.cost_ns += time.monotonic_ns() - start

    def loop(self):
        while not self.stop_event.wait(self.interval):
            self.sample()

    def start(self):
        self.sample()
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join()
        self.sample()


def worker(port, request, cell, worker_id, sequences, barrier, stop_at, rows, lock, cancel=None):
    barrier.wait()
    previous = None
    for sequence in sequences:
        if time.monotonic_ns() >= stop_at or (cancel is not None and cancel.is_set()):
            break
        meta = {'attempt_id': f'{cell["id"]}:{cell["phase"]}:{sequence}', 'cell': cell['id'],
            'repeat': cell['repeat'], 'worker': worker_id, 'sequence': sequence, 'phase_kind': cell['phase']}
        if cell.get('started_audit'):
            fd = os.open(cell['started_audit'], os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(fd, (json.dumps(meta) + '\n').encode())
            finally:
                os.close(fd)
        result = attempt(port, request, meta, cell['group'], cell['stream'], cell['timeout'],
                         cell['group'] == 'C' and sequence % 4 == 0)
        result['turnaround_ns'] = None if previous is None else result['t0'] - previous
        previous = result['t_closed']
        with lock:
            rows.append(result)


def batch(port, cell, count, output, pids, processes=1):
    global CURRENT_CANCEL
    rows, lock = [], threading.Lock()
    request = request_bytes(cell['stream'], cell['group'].startswith('R'))
    sampler = Sampler({**pids, 'client': os.getpid()}, .05 if cell['group'] in ('A', 'B') else 1)
    started = ended = None
    error = None
    children = []
    received = set()
    child_payloads = []
    shared_rows = ready = child_cancel = None
    try:
        if processes == 2:
            # Spawned clients each prepare eight threads before the shared release event.
            context = multiprocessing.get_context('spawn')
            start_event, ready, shared_rows = context.Event(), context.Queue(), context.Queue()
            child_cancel = context.Event()
            CURRENT_CANCEL = child_cancel
            children = [context.Process(target=child_batch, args=(port, cell, count, i, start_event,
                        ready, shared_rows, child_cancel)) for i in range(2)]
            for child in children:
                child.start()
            for _ in children:
                ready.get(timeout=10)
            sampler.pids.update({f'client_child_{i}': p.pid for i, p in enumerate(children)})
            sampler.start()
            started = time.monotonic_ns()
            start_event.set()
            collect_deadline = time.monotonic() + cell['guard'] + cell['timeout'] + 10
            while len(received) < len(children):
                try:
                    payload = shared_rows.get(timeout=.1)
                    if payload['pid'] in received:
                        raise RuntimeError('duplicate child result')
                    received.add(payload['pid'])
                    child_payloads.append(payload)
                    rows.extend(payload['rows'])
                except queue.Empty:
                    if time.monotonic() >= collect_deadline:
                        raise TimeoutError('client child result deadline')
            ended = max((row['t_closed'] for row in rows), default=time.monotonic_ns())
            for child in children:
                child.join(10)
                if child.exitcode != 0:
                    raise RuntimeError(f'client process exit {child.exitcode}')
            if any(payload['error'] for payload in child_payloads):
                raise RuntimeError('client child error')
        else:
            sampler.start()
            with concurrent.futures.ThreadPoolExecutor(max_workers=cell['concurrency']) as pool:
                # C is deliberately wave-based; A/B/R are continuous closed loop.
                waves = [range(offset, min(offset + 4, count)) for offset in range(0, count, 4)] if cell['group'] == 'C' else [range(count)]
                stop_at = time.monotonic_ns() + int(cell['guard'] * 1e9)
                for wave in waves:
                    barrier = threading.Barrier(cell['concurrency'] + 1, timeout=10)
                    futures = [pool.submit(worker, port, request, cell, index,
                        list(wave)[index::cell['concurrency']], barrier, stop_at, rows, lock, CANCEL)
                        for index in range(cell['concurrency'])]
                    if started is None:
                        # All threads reach barrier before release; creation excluded.
                        readiness_deadline = time.monotonic() + 10
                        while barrier.n_waiting < cell['concurrency']:
                            if time.monotonic() >= readiness_deadline:
                                barrier.abort()
                                raise TimeoutError('worker readiness')
                            time.sleep(.0001)
                        started = time.monotonic_ns()
                    barrier.wait()
                    for future in futures:
                        future.result()
                ended = max((row['t_closed'] for row in rows), default=time.monotonic_ns())
    except BaseException as failure:
        error = repr(failure)
        raise
    finally:
        if child_cancel is not None:
            child_cancel.set()
            deadline = time.monotonic() + cell['timeout'] + 5
            while len(received) < len(children) and time.monotonic() < deadline:
                try:
                    payload = shared_rows.get(timeout=.1)
                    if payload['pid'] not in received:
                        received.add(payload['pid'])
                        child_payloads.append(payload)
                        rows.extend(payload['rows'])
                except queue.Empty:
                    pass
        for child in children:
            if child.is_alive():
                child.terminate()
            child.join(5)
            if child.is_alive():
                child.kill()
                child.join(5)
        CURRENT_CANCEL = None
        for channel in (ready, shared_rows):
            if channel is not None:
                channel.close()
                channel.join_thread()
        if sampler.thread.is_alive():
            sampler.stop()
        else:
            sampler.sample()
        output.mkdir(parents=True, exist_ok=True)
        rows.sort(key=lambda row: row['sequence'])
        (output / 'attempts.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        (output / 'resources.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in sampler.rows))
        completed = {row['sequence'] for row in rows}
        result = {**cell, 'requested': count, 'attempted': len(rows),
            'not_started': [i for i in range(count) if i not in completed], 'start_ns': started,
            'end_ns': ended or time.monotonic_ns(), 'error': error, 'processes': processes,
            'child_processes': [{'pid': child.pid, 'exit_code': child.exitcode, 'alive': child.is_alive()} for child in children],
            'cancel_requested': CANCEL.is_set(), 'sampling_cost_ns': sampler.cost_ns, 'sampling_interval_seconds': sampler.interval}
        (output / 'cell.json').write_text(json.dumps(result, indent=2))
    return result


def child_batch(port, cell, count, index, start_event, ready, shared_rows, cancel):
    rows, lock = [], threading.Lock()
    request = request_bytes(False)
    barrier = threading.Barrier(9, timeout=10)
    error = None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(worker, port, request, cell, index * 8 + i,
                range(index * 8 + i, count, 16), barrier,
                time.monotonic_ns() + int(cell['guard'] * 1e9), rows, lock, cancel)
                for i in range(8)]
            readiness_deadline = time.monotonic() + 10
            while barrier.n_waiting < 8:
                if time.monotonic() >= readiness_deadline:
                    barrier.abort()
                    raise TimeoutError('child worker readiness')
                time.sleep(.0001)
            ready.put(os.getpid())
            if not start_event.wait(15):
                cancel.set()
            barrier.wait()
            for future in futures:
                future.result()
    except BaseException as failure:
        error = repr(failure)
        cancel.set()
        raise
    finally:
        # Executor has joined all late workers before the single parent handoff.
        shared_rows.put({'pid': os.getpid(), 'rows': rows, 'error': error})
