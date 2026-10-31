"""Read-only, phase-separated lifecycle forensics; never joins L4 sessions to HTTP IDs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'capacity'))
from Common import COLUMNS, rows
from Analyze import empty_eof, quantile

ACCEPT = re.compile(rb'session=(\d+) backend=(127\.0\.0\.1:[0-9]+) reason=accepted')
CLOSE = re.compile(rb'session=(\d+) backend=(127\.0\.0\.1:[0-9]+) reason=(.+?) sent_c2b=(\d+) sent_b2c=(\d+)(?: errno=(-?\d+) (.+))?')


def lines(paths):
    pending = b''
    for path in paths:
        with path.open('rb') as stream:
            while block := stream.read(65536):
                parts = (pending + block).split(b'\n')
                pending = parts.pop()
                for line in parts:
                    if len(line) > 8192:
                        raise ValueError('log line bound')
                    yield line
                if len(pending) > 8192:
                    raise ValueError('log line bound')
    if pending:
        raise ValueError('incomplete final log line')


def inspect(root):
    spec = json.loads((root / 'spec.json').read_text())
    phases = {p: {'planned': int(spec[d] * spec['rate']), 'outcomes': Counter(),
                  'errors': Counter(), 'backend_by_outcome': Counter(), 'per_second': {},
                  'closed_minus_connect_ms': []} for p, d in [('w', 'warm'), ('f', 'duration')]}
    received = set()
    backend_roots = [root] if spec['backend_workers'] == 1 else [root / f'backend-{i}' for i in range(spec['backend_workers'])]
    for folder in backend_roots:
        for row in rows(folder, 'backend'):
            if row[0] is not None:
                if row[0] in received:
                    raise ValueError('duplicate backend ID')
                received.add(row[0])
    seen, sent = set(), set()
    for values in rows(root, 'client'):
        if len(values) != len(COLUMNS):
            raise ValueError('client schema')
        r = dict(zip(COLUMNS, values))
        p = phases[r['phase']]
        prefix = spec['id'] + '-' + r['phase'] + '-'
        if not r['id'].startswith(prefix):
            raise ValueError('foreign ID')
        index = int(r['id'][len(prefix):])
        if r['id'] in seen or not 0 <= index < p['planned']:
            raise ValueError('duplicate/unplanned ID')
        seen.add(r['id'])
        if r['tx']:
            sent.add(r['id'])
        # S1's historical zero-byte EOF correction is explicit, never written back.
        outcome = 'transport_failure' if empty_eof(r) else r['outcome']
        p['outcomes'][outcome] += 1
        second = str(index // spec['rate'])
        p['per_second'].setdefault(second, Counter())[outcome] += 1
        if outcome != 'success':
            p['errors'][json.dumps([outcome, r['error'], r['rx']], separators=(',', ':'))] += 1
            if r['connect'] is not None and r['closed'] is not None:
                p['closed_minus_connect_ms'].append((r['closed'] - r['connect']) / 1e6)
        if r['id'] in received:
            p['backend_by_outcome'][outcome] += 1
        elif outcome == 'success':
            raise ValueError('successful ID missing from backend')
    if not received.issubset(sent):
        raise ValueError('backend unknown/unsent ID')
    for p in phases.values():
        if sum(p['outcomes'].values()) != p['planned']:
            raise ValueError('missing planned IDs')
        values = p.pop('closed_minus_connect_ms')
        p['failure_connected_lifetime_ms'] = {label: quantile(values, q) for label, q in [('p50', .5), ('p95', .95), ('p99', .99)]}
    l4 = {'scope': 'all phases; session IDs do not identify HTTP requests'}
    if spec['path'] == 'L':
        accepted, closed = {}, set()
        reasons, zero, errnos = Counter(), Counter(), Counter()
        c2b = b2c = 0
        for line in lines(sorted(root.glob('log-l4lb-*.jsonl'))):
            if b'session=' not in line:
                continue
            a = ACCEPT.fullmatch(line)
            if a:
                sid = int(a[1])
                if sid in accepted:
                    raise ValueError('duplicate L4 accept')
                accepted[sid] = a[2]
                continue
            c = CLOSE.fullmatch(line)
            if not c:
                raise ValueError('unknown L4 session line')
            sid = int(c[1])
            if sid in closed or accepted.get(sid) != c[2]:
                raise ValueError('unpaired L4 close')
            closed.add(sid)
            reason = c[3].decode()
            reasons[reason] += 1
            if int(c[5]) == 0:
                zero[reason] += 1
            if c[6]:
                errnos[reason + ':' + c[6].decode()] += 1
            c2b += int(c[4]); b2c += int(c[5])
        if set(accepted) != closed:
            raise ValueError('L4 sessions not conserved')
        l4.update(accepted=len(accepted), closed=len(closed), close_reasons=reasons,
                  zero_response_reasons=zero, errno=errnos, sent_c2b=c2b, sent_b2c=b2c)
    hashes = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
            hashes[str(path.relative_to(root))] = digest.hexdigest()
    return {'input': str(root), 'spec': spec, 'phases': phases, 'l4': l4, 'input_sha256': hashes}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('output exists')
    results = [inspect(root) for root in args.input]
    data = json.dumps({'schema': 1, 'cells': results}, indent=2).encode() + b'\n'
    if len(data) > 1024 * 1024:
        raise ValueError('summary exceeds 1MiB')
    with args.output.open('xb') as stream:
        stream.write(data)
    print(json.dumps({'cells': len(results), 'output_bytes': len(data)}))


if __name__ == '__main__':
    main()
