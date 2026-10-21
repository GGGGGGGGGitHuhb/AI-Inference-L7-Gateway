"""Strict S2 raw audit and preregistered decision, no parameter selection."""
import json
import statistics
from collections import Counter
from pathlib import Path

from QueuePlan import build_plan, configuration, normalize_config, CONFIG_FILES
from Statistics import summarize, quantiles
from Association import associate
from Budget import save


def phase_summary(cell, items, rows, t0):
    if cell['rate']:
        for item, row in zip(items, rows):
            if row.get('scheduled') != t0 + int(item['index'] / cell['rate'] * 1e9):
                raise ValueError('scheduled origin differs from immutable plan')
    result = summarize(cell, items, rows, t0)
    result['classes'] = {}
    for label, long in [('short', False), ('long', True)]:
        selected = [r for r in rows if bool(r.get('long')) == long]
        passed = sum(r['outcome'] == 'success' and
                     (r['http_complete'] - r['scheduled']) <= 500000000 and
                     r.get('content') is not None and
                     (r['content'] - r['scheduled']) <= 250000000 for r in selected) if cell['rate'] else None
        result['classes'][label] = dict(planned=len(selected),
            counts=dict(Counter(r['outcome'] for r in selected)), slo_met=passed,
            goodput=passed / result['window_seconds'] if passed is not None else None)
    return result


def check_trace(row, trace, backend_rows, timeout_ms):
    """Use host enqueue/terminal clocks, never client arrival as queue origin."""
    for name in ('accepted', 'enqueued', 'dispatched', 'finished', 'upstream_complete'):
        if not isinstance(trace.get(name), int) or trace[name] < 0:
            raise ValueError('missing host clock: ' + name)
    if not trace['finished'] or trace['active'] or trace['waiting']:
        raise ValueError('nonterminal host session')
    if trace['enqueued'] and not trace['accepted'] <= trace['enqueued'] <= trace['finished']:
        raise ValueError('enqueue clock order')
    if trace['dispatched'] and not (trace['enqueued'] or trace['accepted']) <= trace['dispatched'] <= trace['finished']:
        raise ValueError('dispatch clock order')
    if row['outcome'] == 'success':
        if trace['outcome'] != 'complete' or not trace['dispatched'] or len(backend_rows) != 1:
            raise ValueError('false success or missing backend dispatch')
        if backend_rows[0]['backend'] != trace.get('backend') or backend_rows[0]['error']:
            raise ValueError('backend identity or completion error')
    elif row['outcome'] in ('http_timeout', 'http_rejection'):
        if trace['outcome'] != row['error_code'] or trace['dispatched'] or backend_rows:
            raise ValueError('rejected/expired request dispatched')
    else:
        raise ValueError('unexpected connected terminal outcome')
    if row.get('error_code') == 'queue_timeout':
        if not trace['enqueued'] or trace['upstream_complete']:
            raise ValueError('queue timeout without pure waiting lifecycle')
        seconds = (trace['finished'] - trace['enqueued']) / 1e9
        # Host exports microsecond-clock-derived nanoseconds; allow <1 ms
        # truncation at the deadline, but retain every late timer observation.
        if seconds < timeout_ms / 1000 - .001:
            raise ValueError('premature queue timeout')
        return 'expired', seconds
    if trace['enqueued'] and trace['dispatched']:
        return 'dispatched', (trace['dispatched'] - trace['enqueued']) / 1e9
    return None, None


def pair_decision(rows, flags):
    pairs = {}; blocked = []
    for rate in (5, 60):
        pairs[rate] = []
        for repeat in range(3):
            group = [r for r in rows if r['group'] == 'Q' and r['rate'] == rate and r['repeat'] == repeat]
            if len(group) != 3 or {r['variant'] for r in group} != {'Z', 'B', 'C'}:
                raise ValueError('missing or duplicate complete triplet')
            by = {r['variant']: r['phases']['formal'] for r in group}
            valid = not any(s['arrival_limited'] for s in by.values())
            b, c = by['B'], by['C']
            comparisons = {}
            for label in ('all', 'short', 'long'):
                left = b['goodput'] if label == 'all' else b['classes'][label]['goodput']
                right = c['goodput'] if label == 'all' else c['classes'][label]['goodput']
                comparisons[label] = dict(baseline=left, candidate=right, delta=right-left,
                                           relative=(right-left)/left if left else None)
            pairs[rate].append(dict(repeat=repeat, valid=valid, comparison=comparisons))
            if rate == 5 and valid:
                for variant in ('B', 'C'):
                    if by[variant]['counts'].get('http_timeout', 0) or by[variant]['counts'].get('http_rejection', 0):
                        blocked.append(f'low-load rejection: repeat{repeat}/{variant}')
        if sum(p['valid'] for p in pairs[rate]) < 2:
            blocked.append(f'arrival control at {rate}')

    def nondegraded(rate, label):
        values = [p['comparison'][label] for p in pairs[rate] if p['valid']]
        ratios = [v['relative'] for v in values if v['relative'] is not None]
        return bool(values) and all(v['delta'] >= 0 for v in values if v['relative'] is None) and (
            not ratios or statistics.median(ratios) >= -.05 - 1e-12)

    high = [p['comparison']['all'] for p in pairs[60] if p['valid']]
    ratios = [v['relative'] for v in high if v['relative'] is not None]
    numeric = (sum(v['delta'] > 0 for v in high) >= 2 and bool(ratios) and
               statistics.median(ratios) >= .05 - 1e-12 and
               nondegraded(5, 'all') and
               all(nondegraded(rate, label) for rate in (5, 60) for label in ('short', 'long')))
    limited = any(flags[k] for k in ('machine_drift', 'generator_sensitive', 'client_cpu_at_least_085'))
    return dict(status='BLOCKED' if blocked else 'PASS', blocked=blocked, pairings=pairs,
                numeric_thresholds_met=numeric, tool_limited=limited,
                recommendation_eligible=not blocked and numeric and not limited,
                recommendation='not recommended to replace baseline' if blocked or not numeric or limited
                else 'conditional on independent reviewer agreement; measured synthetic workload only')


def analyze(root):
    root = Path(root)
    plan = json.loads((root/'plan.json').read_text())
    if plan != build_plan():
        raise ValueError('plan differs from frozen 21-cell design')
    results = []; all_ids = set()
    for cell in plan['cells']:
        folder = root/cell['id']; phases = {}; rows = []
        for phase in ('warmup', 'formal'):
            items = [a for a in cell['attempts'] if a['phase'] == phase]
            observed = [json.loads((folder/(a['id']+'.json')).read_text()) for a in items]
            old = json.loads((folder/(phase+'-summary.json')).read_text())
            computed = phase_summary(cell, items, observed, old['t0'])
            for key in summarize(cell, items, observed, old['t0']):
                if computed[key] != old[key]:
                    raise ValueError('raw/summary mismatch: ' + key)
            for item, row in zip(items, observed):
                if any(row.get(k) != v for k, v in item.items()) or row['id'] in all_ids:
                    raise ValueError('plan identity/classification mismatch')
                all_ids.add(row['id'])
            phases[phase] = computed; rows.extend(observed)
        processes = [json.loads(line) for line in (folder/'processes.jsonl').read_text().splitlines()]
        starts = [p['pid'] for p in processes if p['event'] == 'start']
        reaped = [p['pid'] for p in processes if p['event'] == 'reaped']
        if sorted(starts) != sorted(reaped) or len(starts) != len(set(starts)):
            raise ValueError('PID lifecycle mismatch')
        waits = None
        if cell['group'] == 'Q':
            config = json.loads((folder/'gateway-config.json').read_text())
            static = json.loads((Path(__file__).parent/'configs'/CONFIG_FILES[cell['variant']]).read_text())
            if normalize_config(config) != normalize_config(static) or normalize_config(config) != configuration(cell, [1, 2]):
                raise ValueError('runtime/static configuration mismatch')
            host = next(p for p in processes if p['event'] == 'start' and p['command'][0].endswith('ExperimentRuntimeHost'))
            connected = [r for r in rows if r.get('connect')]
            mapping, excluded = associate(rows, json.loads((folder/'host-final-records.json').read_text()),
                cell_id=cell['id'], host_pid=host['pid'], target_port=connected[0]['target_port'])
            backend = {}
            for index in range(2):
                for b in json.loads((folder/f'backend-{index}.json').read_text())['requests']:
                    backend.setdefault(b['id'], []).append({**b, 'backend': index})
            if set(backend) != {r['id'] for r in rows if r['outcome'] == 'success'}:
                raise ValueError('unexpected/missing backend request IDs')
            waits = {phase: {'dispatched': [], 'expired': []} for phase in ('warmup', 'formal')}
            transitions = [json.loads(line) for line in (folder/'transitions.jsonl').read_text().splitlines()]
            terminals = Counter(t['id'] for t in transitions if t['finished'])
            if dict(terminals) != {t['id']: 1 for t in mapping.values()}:
                raise ValueError('duplicate or missing terminal event')
            for row in rows:
                if row['id'] in excluded:
                    continue
                kind, seconds = check_trace(row, mapping[row['id']], backend.get(row['id'], []), cell['queue_timeout_ms'])
                if kind:
                    waits[row['phase']][kind].append(dict(id=row['id'], seconds=seconds))
            save(folder/'queue-audit.json', dict(waits=waits, distributions={phase: {
                kind: quantiles([v['seconds'] for v in values]) for kind, values in kinds.items()}
                for phase, kinds in waits.items()}, duplicate_terminals=0, cancellations=0))
        clients = [json.loads(line) for line in (folder/'client-resources.jsonl').read_text().splitlines()]
        cpu = [r['cpu_seconds']/phases['formal']['wall_seconds'] for r in clients[-cell['processes']:]]
        results.append({k: cell[k] for k in ('id', 'group', 'rate', 'repeat', 'variant', 'queue_count', 'queue_timeout_ms')} |
                       dict(phases=phases, client_cpu_cores=cpu, waits=waits))
    if len(all_ids) != 2970:
        raise ValueError('2970-ID conservation')
    t = [r['phases']['formal']['completion_throughput'] for r in results if r['group'] == 'T']
    flags = dict(machine_drift=abs(t[2]/t[0]-1) > .2,
                 generator_sensitive=abs(t[1]/t[0]-1) > .15,
                 client_cpu_at_least_085=any(max(r['client_cpu_cores']) >= .85 for r in results))
    result = pair_decision(results, flags) | dict(flags=flags, controls_throughput=t,
                                              cells=results, unique_ids=len(all_ids))
    save(root/'analysis.json', result)
    return result
