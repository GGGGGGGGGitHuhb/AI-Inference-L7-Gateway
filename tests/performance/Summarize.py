#!/usr/bin/env python3
"""Nearest-rank successful distributions; cells/repeats remain independent."""
import argparse
import collections
import json
import math
import pathlib
import statistics


def distribution(values, percentiles):
    values = sorted(values)
    return {'n': len(values), **{f'p{q}': values[math.ceil(len(values) * q / 100) - 1]
            if values else None for q in percentiles}, 'max': max(values) if values else None}


def summarize(root):
    root = pathlib.Path(root)
    output = []
    for cell in json.loads((root / 'cells.json').read_text()):
        folder = root / cell['id'] / 'formal'
        rows = [json.loads(line) for line in (folder / 'attempts.jsonl').read_text().splitlines()]
        success = [row for row in rows if row['success']]
        failure = [row for row in rows if not row['success']]
        duration = (cell['end_ns'] - cell['start_ns']) / 1e9
        q = [50, 95, 99] if cell['group'] == 'A' else [50, 95] if cell['group'] == 'B' else [50, 90] if cell['group'].startswith('R') else [50]
        metrics = {}
        for name, end, start in [('e2e_ms', 't_http', 't0'), ('ttfb_ms', 't_first_wire', 't0'),
                ('connect_ms', 't_connect', 't0'), ('post_send_ms', 't_http', 't_send'),
                ('first_body_ms', 't_body', 't0'), ('ttft_ms', 't_content', 't0')]:
            if name == 'ttft_ms' and not cell['stream']:
                continue
            metrics[name] = distribution([(r[end] - r[start]) / 1e6 for r in success if r[end] is not None], q)
        samples = [json.loads(line) for line in (folder / 'resources.jsonl').read_text().splitlines()]
        resources = {}
        for name in samples[0]['processes']:
            observed = [(r['time_ns'], r['processes'].get(name)) for r in samples if r['processes'].get(name)]
            if observed:
                first, last = observed[0], observed[-1]
                wall = (last[0]-first[0])/1e9
                resources[name] = {'sample_count': len(observed), 'rss_peak_bytes': max(v['rss_bytes'] for _, v in observed),
                    'fd_peak': max(v['fd'] for _, v in observed), 'fd_start': first[1]['fd'], 'fd_end': last[1]['fd'],
                    'cpu_seconds': last[1]['cpu_seconds']-first[1]['cpu_seconds'],
                    'core_equivalents': (last[1]['cpu_seconds']-first[1]['cpu_seconds'])/wall if wall else None,
                    'context_switch_delta': {key: last[1]['context_switches'][key]-first[1]['context_switches'][key]
                                            for key in first[1]['context_switches']}}
        tokens = [r['completion_tokens'] for r in success]
        tokens_valid = bool(tokens) and all(isinstance(t, int) and t >= 0 for t in tokens)
        active = peak_active = 0
        for _, change in sorted([(r['t0'], 1) for r in rows] + [(r['t_closed'], -1) for r in rows]):
            active += change
            peak_active = max(peak_active, active)
        result = {**cell, 'observed_peak_inflight': peak_active, 'wall_seconds': duration, 'valid_success': len(success), 'failed': len(failure),
            'failure_categories': dict(collections.Counter(r['category'] for r in failure)),
            'failure_rate': len(failure)/len(rows) if rows else None,
            'success_completion_s': len(success)/duration, 'attempt_s': len(rows)/duration,
            'valid_decoded_bytes': sum(r['decoded_bytes'] for r in success),
            'valid_mib_s': sum(r['decoded_bytes'] for r in success)/2**20/duration,
            'completion_tokens': sum(tokens) if tokens_valid else None,
            'tokens_s': sum(tokens)/duration if tokens_valid else None,
            'token_source': 'per-request usage.completion_tokens' if tokens_valid else 'missing reliable count; events/bytes not tokens',
            'failure_duration_ms': distribution([(r['t_closed']-r['t0'])/1e6 for r in failure], [50, 95]),
            'worker_turnaround_ms': distribution([r['turnaround_ns']/1e6 for r in rows if r['turnaround_ns'] is not None], [50, 95]),
            'metrics': metrics, 'resources': resources}
        if cell['group'] == 'C':
            result['fast_slow'] = {label: distribution([(r['t_http']-r['t0'])/1e6 for r in success if r['slow'] == slow], [50])
                                   for label, slow in [('fast', False), ('slow', True)]}
        counts = root / cell['id'] / 'backend-counts.json'
        if counts.exists():
            final = json.loads(counts.read_text())
            warm = json.loads(pathlib.Path(str(counts) + '.warmup').read_text())
            result['backend_counts'] = {'warmup': warm, 'total_accepts': final['accepts'],
                'total_requests': len(final['requests']), 'formal_accepts': final['accepts'] - warm['accepts'],
                'formal_requests': len(final['requests']) - warm['requests']}
            intervals = [value/1e6 for req in final['requests'][warm['requests']:] for value in req['interval_ns']]
            if intervals:
                result['backend_send_interval_ms'] = distribution(intervals, [50, 95, 99])
        host = root / cell['id'] / 'host-maxima.json'
        if host.exists():
            result['host_maxima_including_warmup'] = json.loads(host.read_text())
        output.append(result)
    groups = collections.defaultdict(list)
    for cell in output:
        if not cell['id'].startswith('control'):
            groups[(cell['group'], cell['path'], cell['concurrency'], cell['stream'])].append(cell)
    repeats = []
    for key, cells in groups.items():
        values = {'success_completion_s': [c['success_completion_s'] for c in cells]}
        for metric in cells[0]['metrics']:
            for q in cells[0]['metrics'][metric]:
                if q.startswith('p'):
                    values[f'{metric}_{q}'] = [c['metrics'][metric][q] for c in cells if c['metrics'][metric][q] is not None]
        repeats.append({'group': key[0], 'path': key[1], 'concurrency': key[2], 'stream': key[3],
            'cells': [c['id'] for c in cells], 'stats': {name: {'median': statistics.median(v) if v else None,
                'min': min(v) if v else None, 'max': max(v) if v else None} for name, v in values.items()}})
    controls = [c for c in output if c['id'].startswith('control')]
    flags = []
    if len(controls) == 3:
        a, b, c = controls
        if abs(b['success_completion_s']/a['success_completion_s'] - 1) > .15:
            flags.append('two-process completion rate differs >15%: possible generator/backend/scheduling limit')
        if abs(c['success_completion_s']/a['success_completion_s'] - 1) > .2 or abs(c['metrics']['e2e_ms']['p50']/a['metrics']['e2e_ms']['p50'] - 1) > .2:
            flags.append('pre/post control drift >20%: machine/tool drift possible')
    for concurrency in (1, 4, 16):
        selected = [c for c in output if c['group'] == 'A' and c['concurrency'] == concurrency]
        if selected and any(c['resources'].get('client', {}).get('core_equivalents', 0) > .85 for c in selected):
            flags.append(f'client near one core in A C={concurrency}; inspect scaling, generator/backend interference possible')
    return {'cells': output, 'repeat_statistics': repeats, 'control_flags': flags,
            'limits': ['closed loop; coordinated omission uncorrected', 'three repeats are observed ranges, not confidence intervals',
                       'CPU single-slot model; no production capacity or GPU claim', 'sampled resource peaks are not exact peaks']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'summary.json').write_text(json.dumps(summarize(args.input), indent=2))


if __name__ == '__main__':
    main()
