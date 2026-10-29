"""Streaming ID conservation and scheduled-window SLO audit."""
from collections import Counter
import json
import math
import re
import itertools
from pathlib import Path
from Common import COLUMNS, digest, payload, rows


def quantile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)]


def empty_eof(row):
    return (row['outcome'] == 'protocol_error' and row['error'] == 'missing delimiter'
            and row['rx'] == 0 and all(row[k] is None for k in ['wire', 'body', 'http']))


def audit(root, correct_empty_eof=False):
    root = Path(root)
    spec = json.loads((root / 'spec.json').read_text())
    counts = {phase: int(spec['rate'] * spec[duration]) for phase, duration in [('w', 'warm'), ('f', 'duration')]}
    seen = {phase: bytearray(count) for phase, count in counts.items()}
    outcomes, latencies, lags = Counter(), {k: [] for k in ['connect', 'send', 'wire', 'body', 'http', 'eof', 'closed']}, []
    good, tx, rx, last = 0, 0, 0, spec['measure_start']
    all_tx = all_rx = 0
    corruption = 0
    sent_ids, success_ids = set(), set()
    for values in rows(root, 'client'):
        if len(values) != len(COLUMNS):
            raise ValueError('record schema')
        row = dict(zip(COLUMNS, values))
        if correct_empty_eof and empty_eof(row):
            row['outcome'] = 'transport_failure'
        prefix = spec['id'] + '-' + row['phase'] + '-'
        if not row['id'].startswith(prefix):
            raise ValueError('foreign ID')
        index = int(row['id'][len(prefix):])
        if row['phase'] not in seen or not 0 <= index < counts[row['phase']] or seen[row['phase']][index]:
            raise ValueError('duplicate or unplanned ID')
        seen[row['phase']][index] = 1
        start = spec['start'] if row['phase'] == 'w' else spec['measure_start']
        if row['scheduled'] != start + index * 1_000_000_000 // spec['rate']:
            raise ValueError('scheduled clock altered')
        clocks = [row[key] for key in ['dispatch', 'connect', 'send', 'wire', 'body', 'http', 'eof', 'closed'] if row[key] is not None]
        if clocks != sorted(clocks) or (clocks and clocks[0] < row['scheduled'] and row['outcome'] != 'not_started'):
            raise ValueError('clock order')
        if row['outcome'] not in ['success', 'http_rejection', 'protocol_error', 'body_error', 'transport_failure', 'client_deadline', 'not_sent', 'not_started', 'interrupted']:
            raise ValueError('unknown outcome')
        if row['outcome'] in ('not_started', 'not_sent') and (row['tx'] or row['rx'] or row['connect']):
            raise ValueError('submitted ID marked unsent')
        if row['tx']:
            sent_ids.add(row['id'])
        if row['outcome'] == 'success':
            if row['digest'] != digest(payload(row['id'], spec['workload'])) or row['status'] != 200 or any(row[k] is None for k in ['dispatch', 'connect', 'send', 'wire', 'body', 'http', 'eof', 'closed']):
                raise ValueError('success integrity')
            success_ids.add(row['id'])
        all_tx += row['tx']
        all_rx += row['rx']
        corruption += row['outcome'] in ('body_error', 'protocol_error')
        if row['phase'] != 'f':
            continue
        outcomes[row['outcome']] += 1
        tx += row['tx']
        rx += row['rx']
        last = max(last, row['closed'] or last)
        if row['dispatch'] is not None:
            lags.append((row['dispatch'] - row['scheduled']) / 1e6)
        if row['outcome'] == 'success':
            for key in latencies:
                latencies[key].append((row[key] - row['scheduled']) / 1e6)
            if latencies['http'][-1] <= (100 if spec['workload'] == 'A' else 250) and (spec['workload'] == 'A' or latencies['body'][-1] <= 50):
                good += 1
    if any(not all(values) for values in seen.values()):
        raise ValueError('missing planned ID')
    backend_ids = set()
    backend_rx = backend_tx = 0
    backend_roots = [root] if spec.get('backend_workers', 1) == 1 else [root / f'backend-{i}' for i in range(spec['backend_workers'])]
    for row in itertools.chain.from_iterable(rows(folder, 'backend') for folder in backend_roots):
        if row[0] is None:
            continue
        if row[0] in backend_ids or row[0] not in sent_ids:
            raise ValueError('backend duplicate or foreign ID')
        backend_ids.add(row[0])
        backend_rx += row[4]
        backend_tx += row[5]
    if not success_ids.issubset(backend_ids):
        raise ValueError('successful ID absent from backend')
    l4 = {}
    if spec['path'] == 'L':
        accepted, closed, pending = {}, {}, b''
        for path in sorted(root.glob('log-l4lb-*.jsonl')):
            data = pending + path.read_bytes()
            lines = data.split(b'\n')
            pending = lines.pop()
            for line in lines:
                if b'session=' not in line:
                    continue
                match = re.fullmatch(rb'session=(\d+) backend=(127\.0\.0\.1:[0-9]{1,5}) reason=accepted', line)
                if match:
                    sid, endpoint = int(match[1]), match[2]
                    if not 1 <= int(endpoint.rsplit(b':', 1)[1]) <= 65535 or sid in accepted:
                        raise ValueError('duplicate L4 acceptance or invalid endpoint')
                    accepted[sid] = endpoint
                    continue
                match = re.fullmatch(rb'session=(\d+) backend=(127\.0\.0\.1:[0-9]{1,5}) reason=([^\r\n]+?) sent_c2b=(\d+) sent_b2c=(\d+)(?: errno=(-?\d+) ([^\r\n]+))?', line)
                if not match:
                    raise ValueError('unknown or malformed L4 session line')
                sid, endpoint = int(match[1]), match[2]
                if sid in closed or sid not in accepted or endpoint != accepted[sid]:
                    raise ValueError('duplicate L4 closure or acceptance endpoint mismatch')
                closed[sid] = (int(match[4]), int(match[5]))
        if pending or set(accepted) != set(closed):
            raise ValueError('incomplete L4 log/session conservation')
        c2b, b2c = sum(v[0] for v in closed.values()), sum(v[1] for v in closed.values())
        l4 = {'accepts': len(accepted), 'closed': len(closed), 'sent_c2b': c2b, 'sent_b2c': b2c, 'client_enqueued_all': all_tx, 'client_received_all': all_rx}
        if len(success_ids) == sum(counts.values()) and (c2b != all_tx or b2c != all_rx):
            raise ValueError('successful L4 byte conservation')
    total = counts['f']
    lag95 = quantile(lags, .95)
    valid = outcomes['not_sent'] / total <= .01 and lag95 is not None and lag95 <= 5
    percentile = {}
    for key, values in latencies.items():
        percentile[key] = {label: quantile(values, q) for label, q, minimum in [('p50', .5, 20), ('p95', .95, 100), ('p99', .99, 1000)] if len(values) >= minimum}
    return {'id': spec['id'], 'path': spec['path'], 'workload': spec['workload'], 'rate': spec['rate'],
            'planned': total, 'outcomes': dict(outcomes), 'good': good, 'goodput': good / spec['duration'],
            'good_fraction': good / total, 'generator_valid': valid, 'lag_p95_ms': lag95,
            'exploration_slo_pass': good / total >= .99 and not corruption,
            'latency_ms': percentile, 'completion_throughput': outcomes['success'] / max(1e-9, (last - spec['measure_start']) / 1e9),
            'application_transport_bytes': {'client_tx': tx, 'client_rx': rx, 'backend_rx_all_phases': backend_rx, 'backend_tx_all_phases': backend_tx},
            'corruption_all_phases': corruption, 'l4': l4, 'backend_ids': len(backend_ids), 'success_all_phases': len(success_ids)}


if __name__ == '__main__':
    import sys
    print(json.dumps(audit(sys.argv[1]), indent=2))
