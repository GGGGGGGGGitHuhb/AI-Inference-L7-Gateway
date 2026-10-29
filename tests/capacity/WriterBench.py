"""Bounded serialization/write microbenchmark, never a product capacity sample."""
import argparse
import itertools
import json
from pathlib import Path
import time
from Common import Chunks, MIB, rows, write
from Runtime import Ledger

parser = argparse.ArgumentParser()
parser.add_argument('--run', required=True)
parser.add_argument('--sample', required=True)
args = parser.parse_args()
ledger = Ledger(args.run)
if any(c['state'] == 'running' for c in ledger.data['cells']):
    raise RuntimeError('run only while load is stopped')
root = Path(args.run) / 'writer-microbench'
root.mkdir(exist_ok=False)
source = list(itertools.islice(rows(args.sample, 'client'), 64))
if not source:
    raise ValueError('sample required')
used = sum(p.stat().st_size for p in ledger.budget_root.rglob('*') if p.is_file())
if used + 8*MIB + 16*MIB > 2*1024*MIB or ledger.data['active_seconds'] + 5 > 5400:
    raise RuntimeError('auxiliary budget')
ledger.data['active_seconds'] += 5
ledger.save()
start = time.monotonic()
result = []
for repeat in range(3):
    for mode in ['encode', 'encode_write']:
        output = Chunks(root, f'{mode}-{repeat}', 2*MIB, row_limit=512)
        cpu, wall = time.process_time_ns(), time.monotonic_ns()
        for index in range(5000):
            row = source[index % len(source)]
            if mode == 'encode':
                json.dumps(row, separators=(',', ':')).encode()
            else:
                output.row(row)
        output.close()
        elapsed_cpu, elapsed_wall = time.process_time_ns() - cpu, time.monotonic_ns() - wall
        result.append({'mode': mode, 'repeat': repeat, 'records': 5000,
                       'cpu_ns': elapsed_cpu, 'wall_ns': elapsed_wall, 'bytes': output.total,
                       'cpu_ns_per_record': elapsed_cpu / 5000})
elapsed = time.monotonic() - start
ledger.data['active_seconds'] -= max(0, 5 - elapsed)
ledger.data.setdefault('auxiliary', []).append({'kind': 'writer-microbench', 'elapsed_seconds': elapsed})
ledger.save()
write(root / 'result.json', {'sample': args.sample, 'scope': 'serialization/page-cache write only; not network/response validation', 'measurements': result})
print(json.dumps(result, indent=2))
