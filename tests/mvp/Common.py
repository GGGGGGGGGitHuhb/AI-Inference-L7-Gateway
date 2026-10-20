"""S3 independent fixtures; imports immutable S3 predecessor utilities only."""
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/integration'))
from Support import WireResponse, check, free_port, get_json, process_stats, sha, INPUTS
from Budget import OwnedProcess, append, save

ZERO = ('sessions', 'reserved', 'capacity', 'pending', 'paused', 'timers', 'upstreams',
        'leased', 'idle', 'pool_total', 'retired', 'inflight', 'queue_count', 'queue_bytes')


def wait_for(predicate, timeout, label):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.005)
    raise AssertionError('gate timeout: ' + label)


def configuration(ports, real=False):
    names = [('gateway-qwen', ports)] if real else [('a', ports[:2]), ('b', ports[2:])]
    return {'listen_port': 0, 'max_connections': 16, 'max_reserved_bytes': 268435456,
            'models': [{'name': name, 'policy': 'least_inflight' if name == 'b' else 'round_robin',
                        'backends': [{'id': name + str(i + 1), 'address': '127.0.0.1', 'port': port}
                                     for i, port in enumerate(group)]} for name, group in names],
            'admission': {'max_inflight': 2, 'max_inflight_per_backend': 1,
                          'max_queue_requests_per_model': 4 if real else 2,
                          'max_queue_bytes_per_model': 65536 if real else 4096,
                          'queue_timeout_ms': 120000 if real else 500},
            'health': {'failure_threshold': 1, 'cooldown_ms': 1000},
            'upstream_pool': {'max_connections': 4, 'max_idle': 1, 'idle_timeout_ms': 1000},
            'stream_buffer': {'high_water_bytes': 196608, 'low_water_bytes': 65536, 'max_total_bytes': 1048576},
            'timeouts_ms': {'request': 10000 if real else 1000, 'connect': 3000 if real else 500,
                            'upstream_write': 5000 if real else 1000, 'response': 120000 if real else 2000,
                            'stream_idle': 30000 if real else 1000, 'downstream_write': 10000 if real else 1000,
                            'total': 150000 if real else 2000, 'shutdown': 3000}}


def body(model, stream=True, long=False, large=False):
    return {'model': model, 'messages': [{'role': 'user', 'content': 'x' * 4200 if large else INPUTS['long' if long else 'short']}],
            'stream': stream, 'temperature': 0, 'n': 1, 'max_tokens': 512 if long else 32}


def check_limits(state, config):
    check(state['peak_inflight'] <= config['admission']['max_inflight'], 'global inflight overflow')
    check(state['inflight'] == sum(row['inflight'] for row in state['backends']), 'unique inflight sum')
    for row in state['backends']:
        check(row['peak_inflight'] <= config['admission']['max_inflight_per_backend'], 'backend inflight overflow')
    for row in state['queues']:
        check(row['peak_count'] <= config['admission']['max_queue_requests_per_model'], 'queue count overflow')
        check(row['peak_bytes'] <= config['admission']['max_queue_bytes_per_model'], 'queue bytes overflow')
    check(state['peak_reserved'] <= config['max_reserved_bytes'], 'reservation overflow')
    check(state['peak_capacity'] <= config['stream_buffer']['max_total_bytes'], 'stream capacity overflow')
    check(state['pending'] <= state['capacity'], 'pending budget overflow')


def check_zero(state):
    check(all(state[key] == 0 for key in ZERO), 'resource residual: ' + repr({k: state[k] for k in ZERO}))


class Host:
    def __init__(self, executable, config, output, label):
        self.output = Path(output)
        self.name = label
        self.config = config
        self.trace = self.output / (label + '-state.json')
        path = self.output / (label + '-config.json')
        save(path, config)
        self.log = self.output / (label + '.log')
        self.owned = OwnedProcess([executable, path, self.trace], self.log, self.output / 'processes.jsonl',
                                  direct_paths=[self.trace, str(self.trace)+'.partial', str(self.trace)+'.jsonl'])
        self.baseline = None
        try:
            wait_for(self.ready, 5, 'host ready')
            self.baseline = process_stats(self.owned.process.pid)
        except BaseException:
            self.owned.stop()
            raise

    def ready(self):
        check(self.owned.process.poll() is None, 'host premature exit')
        for line in self.log.read_text().splitlines():
            if line.startswith('{'):
                self.port = json.loads(line)['ready_port']
                return self.trace.exists()
        return False

    def state(self):
        state = json.loads(self.trace.read_text())
        check_limits(state, self.config)
        return state

    def record(self, attempt):
        port = attempt.row.get('client_port')
        rows = [row for row in self.state()['records'] if row.get('client_port') == port]
        check(len(rows) <= 1, 'ambiguous client-port identity')
        return rows[0] if rows else None

    def waiting(self, attempt):
        row = self.record(attempt)
        return row and row['waiting']

    def active(self, attempt):
        row = self.record(attempt)
        return row if row and row['request_active'] else None

    def drain(self, label, check_rss=True):
        beginning = time.monotonic_ns()
        def drained():
            value = self.state()
            return value if value['now'] >= beginning and all(value[k] == 0 for k in ZERO) else None
        value = wait_for(drained, 5, 'drain ' + label)
        stats = process_stats(self.owned.process.pid)
        check(stats is not None, 'host disappeared during drain')
        check(stats['fd'] == self.baseline['fd'], 'FD baseline mismatch')
        if check_rss:
            check(stats['rss'] <= self.baseline['rss'] + 32 * 1024**2, 'RSS B+32MiB')
        point = {'label': label, 'time': time.monotonic(), 'state': value, **stats}
        append(self.output / 'drains.jsonl', point)
        return point

    def stop(self):
        self.owned.stop()
        check(self.owned.process.returncode == 0, 'host exit failure')
        check_zero(self.state())


class ResourceSampler:
    def __init__(self, processes, output):
        self.processes = processes
        self.path = Path(output) / 'resources.jsonl'
        self.event = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            while not self.event.is_set():
                rows = {name: process_stats(owned.process.pid) for name, owned in self.processes.items()}
                for name, value in rows.items():
                    if name.startswith('backend') and value:
                        check(value['rss'] <= 2 * 1024**3, 'backend RSS bound')
                append(self.path, {'time': time.monotonic(), 'processes': rows})
                self.event.wait(1)
        except BaseException as error:
            self.error = error

    def stop(self):
        self.event.set()
        self.thread.join(2)
        check(not self.thread.is_alive(), 'sampler stuck')
        if self.error:
            raise self.error


def summary(rows, expected_ids):
    check(len(rows) == len(expected_ids), 'missing attempts')
    check({row['id'] for row in rows} == set(expected_ids), 'wrong or duplicate attempt IDs')
    check(len({row['id'] for row in rows}) == len(rows), 'duplicate attempts')
    import statistics
    result = {}
    for group in sorted({row['group'] for row in rows}):
        selected = [row for row in rows if row['group'] == group]
        counts = {kind: sum(row['outcome'] == kind for row in selected)
                  for kind in ['success', 'cancelled', 'rejected', 'queue_timeout', 'backend_failure', 'failure']}
        times = {}
        for metric in ['ttft', 'e2e']:
            values = [row[metric] for row in selected if row['outcome'] == 'success' and row.get(metric) is not None]
            times[metric] = {'n': len(values), 'min': min(values) if values else None,
                             'median': statistics.median(values) if values else None, 'max': max(values) if values else None}
        result[group] = {'attempts': len(selected), 'counts': counts, 'latency_seconds': times}
    return result


def join_observations(output, mode):
    output = Path(output)
    plan = json.loads((output / 'plan.json').read_text())
    rows = [json.loads((output / (identity + '.json')).read_text()) for identity in plan['attempt_ids']]
    queue_samples, terminal_waits = [], []
    for row in rows:
        if mode == 'real' and row['cohort'] in ('direct', 'official'):
            continue
        path = output / ('real-state.json' if mode == 'real' else row['group'] + '-state.json')
        state = json.loads(path.read_text())
        matches = [record for record in state['records'] if record.get('client_port') == row.get('client_port')]
        check(len(matches) == 1, 'attempt/Session identity missing or ambiguous')
        record = matches[0]
        row['host_record'] = record
        if record['enqueued']:
            if record['dispatched'] and row['outcome'] == 'success':
                wait = (record['dispatched'] - record['enqueued']) / 1e9
                check(wait >= 0, 'negative queue wait')
                queue_samples.append({'id': row['id'], 'seconds': wait})
            elif row['outcome'] in ('cancelled', 'queue_timeout'):
                terminal_waits.append({'id': row['id'], 'outcome': row['outcome'],
                    'seconds': (record['finished'] - record['enqueued']) / 1e9})
    save(output / 'joined-attempts.json', rows)
    save(output / 'queue-waits.json', {'dispatched_successful': queue_samples,
                                      'cancelled_or_expired': terminal_waits})
    result = summary(rows, plan['attempt_ids'])
    # Compatibility/preheat and formal latency have explicitly separate cohorts.
    for group in result:
        result[group]['cohorts'] = {}
        for cohort in sorted({row['cohort'] for row in rows if row['group'] == group}):
            subset = [row for row in rows if row['group'] == group and row['cohort'] == cohort]
            result[group]['cohorts'][cohort] = summary(subset, [row['id'] for row in subset])[group]
        if group == 'R0':
            del result[group]['latency_seconds']
    save(output / 'summary.json', result)


def cleanup_all(actions, output):
    errors = []
    for label, action in actions:
        try:
            action()
        except BaseException as error:
            errors.append({'resource': label, 'error': repr(error)})
    if errors:
        save(Path(output) / 'cleanup-errors.json', errors)
        raise RuntimeError('cleanup failures: ' + repr(errors))
