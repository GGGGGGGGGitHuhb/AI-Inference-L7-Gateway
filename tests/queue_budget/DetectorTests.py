"""S2 offline counterexamples and bounded real lifecycle controls, not samples."""
import argparse
import copy
import json
from pathlib import Path
import signal
import socket
import threading
import time
from types import SimpleNamespace

from QueuePlan import build_plan, configuration, CONFIG_FILES, normalize_config
from QueueAudit import phase_summary, check_trace, pair_decision
from RunQueueBudget import QueueCell, close_unstarted
from Budget import RunBudget, save
from Client import attempt, PAYLOADS
from Plan import request
from Infrastructure import Host, wait_for, validate_empty
from Association import associate


def reject(action):
    try:
        action()
    except (AssertionError, ValueError, RuntimeError):
        return
    raise AssertionError('counterexample incorrectly accepted')


def parse_headers(head):
    return {name.strip().lower(): value.strip() for name, value in
            (line.split(b':', 1) for line in head.split(b'\r\n')[1:])}


def unit_checks(root):
    for length, identity in [(b'content-length', b'x-experiment-id'),
                             (b'CoNtEnT-LeNgTh', b'X-ExPeRiMeNt-Id')]:
        headers = parse_headers(b'POST / HTTP/1.1\r\n' + length + b': 42\r\n' + identity + b': test')
        assert headers[b'content-length'] == b'42' and headers[b'x-experiment-id'] == b'test'
    plan = build_plan()
    assert len(plan['cells']) == 21
    ids = [a['id'] for c in plan['cells'] for a in c['attempts']]
    assert len(ids) == len(set(ids)) == 2970
    assert sum(c['formal'] for c in plan['cells']) == 2760
    cell = copy.deepcopy(plan['cells'][2]); cell['rate'] = 5
    items = [dict(id='one', index=0, long=False), dict(id='two', index=1, long=True)]
    row = dict(id='one', index=0, long=False, outcome='success', status=200, http_valid=True,
               scheduled=1000000000, dispatch=1100000000, connect=1100000001,
               send=1100000002, content=1300000000, http_complete=1400000000, closed=1400000001)
    second = dict(id='two', index=1, long=True, outcome='http_timeout', status=504,
                  error_code='queue_timeout', scheduled=1200000000, dispatch=1200000001,
                  closed=1400000001)
    result = phase_summary(cell, items, [row, second], 1000000000)
    assert result['slo_met'] == 0 and result['window_seconds'] == .4
    assert result['classes']['long']['planned'] == 1 and result['classes']['long']['goodput'] == 0
    reject(lambda: phase_summary(cell, items, [row], 1000000000))
    reject(lambda: phase_summary(cell, items, [row, row], 1000000000))
    reject(lambda: phase_summary(cell, items, [row, dict(second, outcome='success')], 1000000000))
    reject(lambda: phase_summary(cell, items, [dict(row, scheduled=row['send']), second], 1000000000))
    # A successful short request plus a rejected long request retains full window.
    good = dict(row, content=1200000000)
    result = phase_summary(cell, items, [good, second], 1000000000)
    assert result['goodput'] == 2.5 and result['classes']['short']['goodput'] == 2.5
    trace = dict(accepted=1, enqueued=2, dispatched=0, finished=100000002,
                 upstream_complete=0, active=False, waiting=False, outcome='queue_timeout')
    assert check_trace(second, trace, [], 100)[0] == 'expired'
    reject(lambda: check_trace(second, dict(trace, dispatched=3), [], 100))
    reject(lambda: check_trace(second, trace, [dict(id='two')], 100))
    reject(lambda: check_trace(second, dict(trace, enqueued=0), [], 100))
    reject(lambda: check_trace(second, dict(trace, finished=50000002), [], 100))
    reject(lambda: check_trace(dict(second, outcome='success'), trace, [], 100))

    def decision_rows(low=10., high=10.5, baseline=10.):
        rows = []
        for c in plan['cells']:
            if c['group'] != 'Q':
                continue
            value = (high if c['rate'] == 60 else low) if c['variant'] == 'C' else baseline
            summary = dict(arrival_limited=False, goodput=value, counts={'success': 120},
                           classes={name: dict(goodput=value/2) for name in ('short', 'long')})
            rows.append({**c, 'phases': {'formal': summary}})
        return rows

    flags = dict(machine_drift=False, generator_sensitive=False, client_cpu_at_least_085=False)
    assert pair_decision(decision_rows(low=9.5), flags)['recommendation_eligible']
    assert not pair_decision(decision_rows(high=10.499), flags)['numeric_thresholds_met']
    assert not pair_decision(decision_rows(low=9.499), flags)['numeric_thresholds_met']
    assert not pair_decision(decision_rows(), dict(flags, generator_sensitive=True))['recommendation_eligible']
    assert not pair_decision(decision_rows(baseline=0), flags)['recommendation_eligible']
    invalid = decision_rows()
    for r in invalid:
        if r['rate'] == 60 and r['repeat'] < 2:
            r['phases']['formal']['arrival_limited'] = True
    assert pair_decision(invalid, flags)['status'] == 'BLOCKED'
    low = decision_rows()
    low[1]['phases']['formal']['counts']['http_timeout'] = 1
    assert pair_decision(low, flags)['status'] == 'BLOCKED'
    reject(lambda: pair_decision(decision_rows()[:-1], flags))
    save(root/'offline.json', dict(plan_cells=21, ids=2970,
         controls=['missing/duplicate ID', 'false timeout success', 'scheduled versus send',
                   'rejection denominator', 'expired dispatch/backend', 'missing enqueue',
                   'premature timeout', 'valid triplet count', 'low-load false rejection',
                   '5 percent boundary', 'zero baseline', 'tool limitation',
                   'lowercase and mixed-case HTTP fields']))


def load_configs(root, host_path):
    root.mkdir()
    with RunBudget(root) as budget:
        for variant, filename in CONFIG_FILES.items():
            folder = root/variant; folder.mkdir()
            static = json.loads((Path(__file__).parent/'configs'/filename).read_text())
            cell = next(c for c in build_plan()['cells'] if c['variant'] == variant)
            assert normalize_config(static) == configuration(cell, [1, 2])
            static['listen_port'] = 0
            host = Host(host_path, static, folder)
            try:
                host.drain('loaded')
            finally:
                host.stop()
        budget.finish()


def real_timeout(root, host_path):
    """Two actual backend connections hold both slots until the queued 504."""
    root.mkdir(); release = threading.Event(); received = []; errors = []; sockets = []
    threads = []; clients = []; rows = {}; host = None
    gates = []; original_error = None
    with RunBudget(root) as budget:
        try:
            for index in range(2):
                listener = socket.socket(); listener.bind(('127.0.0.1', 0)); listener.listen()
                listener.settimeout(5); sockets.append(listener)

                def serve(listener=listener, index=index):
                    try:
                        connection, _ = listener.accept()
                        with connection:
                            connection.settimeout(5); data = b''
                            while b'\r\n\r\n' not in data:
                                data += connection.recv(8192)
                            head, body = data.split(b'\r\n\r\n', 1)
                            headers = parse_headers(head)
                            while len(body) < int(headers[b'content-length']):
                                body += connection.recv(8192)
                            received.append(dict(id=headers[b'x-experiment-id'].decode(),
                                backend=index, error=None, received=time.monotonic_ns()))
                            if not release.wait(5):
                                raise RuntimeError('control release gate absent')
                            payload = PAYLOADS['H']
                            connection.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\nContent-Length: ' + str(len(payload)).encode() + b'\r\n\r\n' + payload)
                    except BaseException as error:
                        errors.append(repr(error))

                thread = threading.Thread(target=serve); threads.append(thread); thread.start()
            cell = copy.deepcopy(next(c for c in build_plan()['cells'] if c['variant'] == 'C'))
            cell['id'] = 'timeout-control'
            items = [dict(id=f'timeout-control-formal-{i:03}', index=i, phase='formal', long=False, slow=False) for i in range(3)]
            host = Host(host_path, configuration(cell, [s.getsockname()[1] for s in sockets]), root)
            for item in items[:2]:
                def call(item=item):
                    rows[item['id']] = attempt(host.port, request(cell, item), item, 'Q')
                thread = threading.Thread(target=call); clients.append(thread); thread.start()
            wait_for(lambda: len(received) == 2 and host.state['inflight'] == 2, 3, 'actual two occupied slots')
            gates.append('two actual backend requests and inflight=2')
            occupied = dict(host.state)
            item = items[2]
            def queued_call():
                rows[item['id']] = attempt(host.port, request(cell, item), item, 'Q')
            queued = threading.Thread(target=queued_call); clients.append(queued); queued.start()
            enqueued = wait_for(lambda: next((dict(t) for t in host.records.values()
                if t['enqueued'] and not t['dispatched'] and not t['finished']), None),
                2, 'actual queued session before timeout')
            gates.append('third session enqueued before timeout')
            queued.join(3)
            assert not queued.is_alive()
            expired = rows[item['id']]
            assert expired['status'] == 504 and expired['error_code'] == 'queue_timeout'
            assert not release.is_set() and len(received) == 2
            gates.append('504 queue_timeout while both slots held')
            release.set()
            for thread in clients + threads:
                thread.join(5)
                assert not thread.is_alive()
            assert not errors, errors
            state = host.drain('control'); validate_empty(state)
            gates.append('released and drained')
            records = list(host.records.values())
            mapping, excluded = associate(list(rows.values()), records, cell_id=cell['id'],
                host_pid=host.owned.process.pid, target_port=host.port)
            assert not excluded
            for row in rows.values():
                check_trace(row, mapping[row['id']], [r for r in received if r['id'] == row['id']], 100)
            save(root/'proof.json', dict(occupied=occupied, enqueued=enqueued, rows=list(rows.values()),
                 backend_requests=received, host_records=records, drained=state,
                 timeout_wait_seconds=(mapping[expired['id']]['finished']-mapping[expired['id']]['enqueued'])/1e9))
        except BaseException as error:
            original_error = repr(error)
            raise
        finally:
            release.set()
            for listener in sockets:
                listener.close()
            for thread in clients + threads:
                thread.join(6)
            cleanup_errors = []
            if host:
                try:
                    host.stop()
                except BaseException as error:
                    cleanup_errors.append(repr(error))
            snapshot = dict(original_error=original_error, gates=gates, backend_requests=received,
                backend_errors=errors, client_rows=list(rows.values()),
                alive_threads=sum(t.is_alive() for t in clients + threads),
                host_state=host.state if host else None,
                host_records=list(host.records.values()) if host else [], cleanup_errors=cleanup_errors)
            try:
                if len(json.dumps(snapshot).encode()) > 65536:
                    raise RuntimeError('control forensic snapshot bound')
                save(root/'forensic.json', snapshot)
            except BaseException as error:
                # Preserve the original failure if evidence writing also fails.
                if original_error is None:
                    raise
                print('control forensic write failed:', repr(error), flush=True)
            if original_error is None and cleanup_errors:
                raise RuntimeError('control cleanup: ' + '; '.join(cleanup_errors))
        budget.finish()


class ExitCell(QueueCell):
    def collect_worker(self, reader):
        super().collect_worker(reader)
        if self.started and not getattr(self, 'injected', False):
            self.injected = True
            for owned, _ in self.workers:
                if owned.process.poll() is None:
                    owned.process.kill()


class ExhaustCell(QueueCell):
    def start_gateway(self):
        super().start_gateway()
        # Charge fails before allocating/writing; real owned processes are killed.
        self.budget.charge(self.budget.limits['managed'], 'managed')


def failure_closure(root, host_path, kind):
    root.mkdir()
    cell = copy.deepcopy(next(c for c in build_plan()['cells'] if c['variant'] == 'C'))
    cell['attempts'] = [a for a in cell['attempts'] if a['index'] < 4]
    cell.update(formal=4, warmup=4, rate=60)
    later = copy.deepcopy(cell); later['id'] = 'future-cell'
    later['attempts'] = [dict(a, id='future-'+a['id']) for a in later['attempts']]
    plan = dict(cells=[cell, later]); caught = None
    budget = RunBudget(root)
    with budget:
        try:
            fixture = (ExitCell if kind == 'exit' else ExhaustCell)(cell, SimpleNamespace(host=host_path), root, None, budget)
            fixture.run()
        except BaseException as error:
            caught = repr(error)
        finally:
            close_unstarted(root, plan)
        assert caught is not None
        assert all(child.poll() is not None for child in budget.children)
        actual = [json.loads((fixture.output/(a['id']+'.json')).read_text()) for a in cell['attempts']]
        future = json.loads((root/'unstarted.json').read_text())
        assert len(actual) + len(future) == 16 and len({r['id'] for r in actual + future}) == 16
        assert all(r['outcome'] == 'not_started' for r in future)
        save(root/'result.json', dict(status='EXPECTED_FAILURE', injected=kind, error=caught,
             rows=actual, future=future, children=[dict(pid=p.pid, exit=p.returncode) for p in budget.children]))
        # A deliberately exhausted budget must retain its error until __exit__.
        if kind == 'budget':
            raise ExpectedBudget(caught)


class ExpectedBudget(RuntimeError):
    pass


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--host', required=True)
    parser.add_argument('--output', required=True); args = parser.parse_args()
    root = Path(args.output).resolve(); root.mkdir(parents=True, exist_ok=False)
    unit_checks(root)
    load_configs(root/'config-load', args.host)
    real_timeout(root/'real-timeout', args.host)
    failure_closure(root/'child-exit', args.host, 'exit')
    try:
        failure_closure(root/'budget-exhausted', args.host, 'budget')
    except ExpectedBudget:
        pass
    save(root/'result.json', dict(status='PASS', formal_matrix=False,
         cases=['offline counterexamples', 'three real config loads', 'held-slot queue timeout',
                'child exit 16-ID closure', 'budget exhaustion 16-ID closure']))
    print('QueueBudgetDetectors PASS: offline, config load, real timeout, exit/budget closure')


if __name__ == '__main__':
    main()
