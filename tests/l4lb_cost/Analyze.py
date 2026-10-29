"""Conservation and descriptive paired comparisons; no capacity inference."""
from collections import Counter
import math
import os
import re
from Common import COUNT, WARMUP, RATE, body, digest, require


def quantiles(values):
    values = sorted(values)
    result = {'n': len(values)}
    for label, fraction, minimum in [('p50', .5, 20), ('p95', .95, 100), ('p99', .99, 1000)]:
        if len(values) >= minimum:
            result[label] = values[math.ceil(len(values) * fraction) - 1]
    return result


def sessions(text):
    accepted = re.findall(r'session=(\d+) backend=127\.0\.0\.1:(\d+) reason=accepted', text)
    closed = re.findall(r'session=(\d+) backend=127\.0\.0\.1:(\d+) reason=(\S+) sent_c2b=(\d+) sent_b2c=(\d+)', text)
    require(len({row[0] for row in accepted}) == len(accepted), 'duplicate accepted session')
    require(len({row[0] for row in closed}) == len(closed), 'duplicate closed session')
    return ({sid: int(port) for sid, port in accepted},
            {sid: {'port': int(port), 'reason': reason, 'tx': int(tx), 'rx': int(rx)}
             for sid, port, reason, tx, rx in closed})


def validate_rows(rows, expected, workload):
    require(len(rows) == len(expected) and Counter(r['id'] for r in rows) == Counter(expected), 'missing/duplicate client ID')
    for row in rows:
        require(row['outcome'] == 'success' and row['status'] == 200, 'failed request; preserve denominator')
        clocks = [row[k] for k in ['scheduled_ns', 'dispatch_ns', 'connect_ns', 'send_ns', 'first_wire_ns',
                                  'head_ns', 'first_body_ns', 'http_ns', 'closed_ns']]
        require(all(v is not None for v in clocks) and all(a <= b for a, b in zip(clocks, clocks[1:])), 'invalid client clock')
        require(row['body_sha256'] == digest(body(row['id'], workload)), 'invalid response hash')
        require(row['tx_bytes'] > 0 and row['rx_bytes'] > 0, 'missing wire bytes')


def audit(cell, warm, rows, backend, samples, boundary, l4_text):
    validate_rows(warm, [f'{cell["id"]}-w-{n:03}' for n in range(WARMUP)], cell['workload'])
    validate_rows(rows, [f'{cell["id"]}-f-{n:03}' for n in range(COUNT)], cell['workload'])
    all_ids = [r['id'] for r in warm + rows]
    require(Counter(r['id'] for r in backend['records']) == Counter(all_ids), 'backend missing/duplicate IDs')
    require(backend['accepts'] == len(all_ids), 'hidden backend connection reuse/extra accepts')
    require(not backend['errors'] and all(r['error'] is None for r in backend['records']), 'backend errors')
    by_id = {r['id']: r for r in backend['records']}
    client_tx = sum(r['tx_bytes'] for r in rows)
    client_rx = sum(r['rx_bytes'] for r in rows)
    backend_rx = sum(by_id[r['id']]['rx_bytes'] for r in rows)
    backend_tx = sum(by_id[r['id']]['tx_bytes'] for r in rows)
    l4_tx = l4_rx = 0
    distribution = None
    if cell['path'] == 'L':
        accepted, closed = sessions(l4_text)
        require(len(accepted) == len(all_ids) and accepted.keys() == closed.keys(), 'L4 session conservation')
        require(all(accepted[sid] == value['port'] and value['reason'] == 'drained'
                    for sid, value in closed.items()), 'L4 session identity/termination differs')
        warm_sessions = set(boundary['warm_sessions'])
        require(len(warm_sessions) == WARMUP and warm_sessions <= accepted.keys(), 'warm L4 sessions')
        formal = [value for sid, value in closed.items() if sid not in warm_sessions]
        require(len(formal) == COUNT, 'formal L4 session count')
        l4_tx, l4_rx = sum(r['tx'] for r in formal), sum(r['rx'] for r in formal)
        require((l4_tx, l4_rx) == (client_tx, client_rx), 'L4 forwarded byte mismatch')
        distribution = dict(Counter(r['port'] for r in formal))
        require(sorted(distribution.values()) == [COUNT // 2, COUNT // 2], 'L4 request-count distribution')
    else:
        require(not l4_text, 'unexpected L4 in direct cell')
        distribution = dict(Counter(r['target_port'] for r in rows))
        require(sorted(distribution.values()) == ([COUNT] if cell['path'] == 'D' else [COUNT // 2] * 2), 'direct distribution')
    first, last = samples[0], samples[-1]
    require(len(samples) >= 2 and all(s['start_ns'] <= s['end_ns'] for s in samples), 'invalid sample span')
    require(all(a['end_ns'] <= b['start_ns'] for a, b in zip(samples, samples[1:])), 'nonmonotonic samples')
    require(first['end_ns'] <= boundary['scheduled_start_ns'] <= min(r['dispatch_ns'] for r in rows), 'CPU baseline after start')
    require(last['start_ns'] >= max(r['closed_ns'] for r in rows), 'CPU endpoint before completion')
    wall = (last['end_ns'] - first['start_ns']) / 1e9
    hz = os.sysconf('SC_CLK_TCK')
    cpu = {}
    for name, before in first['processes'].items():
        after = last['processes'][name]
        ticks = after['ticks'] - before['ticks']
        require(ticks >= 0 and before['pid'] == after['pid'], 'invalid CPU identity/ticks')
        cpu[name] = {'ticks': ticks, 'seconds': ticks / hz, 'core_fraction': ticks / hz / wall,
                     'ms_per_success': 1000 * ticks / hz / COUNT, 'low_resolution': ticks < 5,
                     'peak_rss_bytes': max(s['processes'][name]['rss_bytes'] for s in samples),
                     'peak_fds': max(s['processes'][name]['fds'] for s in samples)}
    lag = [(r['dispatch_ns'] - r['scheduled_ns']) / 1e6 for r in rows]
    p95_lag = quantiles(lag)['p95']
    limited = p95_lag > 5 or any(cpu[name]['core_fraction'] > .85 for name in ('client', 'backend'))
    proxy_seconds = sum(v['seconds'] for k, v in cpu.items() if k.startswith('gateway') or k == 'l4lb')
    result = {'id': cell['id'], 'workload': cell['workload'], 'path': cell['path'], 'repeat': cell['repeat'],
              'planned': COUNT, 'success': COUNT, 'not_sent': 0, 'quality_limited': limited,
              'cpu_window_seconds': wall, 'cpu_tick_seconds': 1 / hz, 'cpu': cpu,
              'proxy_cpu_ms_per_success': proxy_seconds * 1000 / COUNT,
              'network': {'client_tx': client_tx, 'client_rx': client_rx, 'backend_rx': backend_rx,
                          'backend_tx': backend_tx, 'l4_tx': l4_tx, 'l4_rx': l4_rx,
                          'summed_link_payload_bytes': client_tx + client_rx + backend_tx + backend_rx + l4_tx + l4_rx,
                          'extra_l4_hop_bytes': l4_tx + l4_rx},
              'distribution': distribution, 'dispatch_lag_ms': quantiles(lag),
              'completion_req_s': COUNT / ((max(r['closed_ns'] for r in rows) - boundary['scheduled_start_ns']) / 1e9),
              'offered_req_s': RATE, 'planned_window_seconds': COUNT / RATE,
              'completed_in_window': sum(r['http_ns'] <= boundary['scheduled_start_ns'] + int(COUNT / RATE * 1e9) for r in rows),
              'max_sample_interval_ms': max((b['start_ns'] - a['start_ns']) / 1e6 for a, b in zip(samples, samples[1:]))}
    for label, key in [('ttfb_ms', 'first_wire_ns'), ('first_body_ms', 'first_body_ns'), ('e2e_ms', 'http_ns'), ('close_ms', 'closed_ns')]:
        result[label] = quantiles([(r[key] - r['scheduled_ns']) / 1e6 for r in rows])
    result['backend_service_ms'] = quantiles([(by_id[r['id']]['ended_ns'] - by_id[r['id']]['started_ns']) / 1e6 for r in rows])
    return result


def paired(cells):
    require(len(cells) == 18, 'incomplete matrix')
    keyed = {(c['workload'], c['repeat'], c['path']): c for c in cells}
    require(len(keyed) == 18, 'duplicate cell')
    result = []
    for workload in ('A', 'B'):
        for repeat in range(3):
            for left, right in [('D', 'M'), ('M', 'L')]:
                a, b = keyed[workload, repeat, left], keyed[workload, repeat, right]
                result.append({'workload': workload, 'repeat': repeat, 'comparison': right + '-' + left,
                    'e2e_p50_delta_ms': b['e2e_ms']['p50'] - a['e2e_ms']['p50'],
                    'e2e_p95_delta_ms': b['e2e_ms']['p95'] - a['e2e_ms']['p95'],
                    'ttfb_p95_delta_ms': b['ttfb_ms']['p95'] - a['ttfb_ms']['p95'],
                    'proxy_cpu_ms_per_success_delta': b['proxy_cpu_ms_per_success'] - a['proxy_cpu_ms_per_success'],
                    'link_payload_bytes_delta': b['network']['summed_link_payload_bytes'] - a['network']['summed_link_payload_bytes'],
                    'quality_limited': a['quality_limited'] or b['quality_limited']})
    return result
