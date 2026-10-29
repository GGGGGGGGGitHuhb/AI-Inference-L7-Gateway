"""Versioned non-destructive correction of empty-response EOF classifications."""
import argparse
import json
from pathlib import Path
from Analyze import audit, empty_eof
from Common import Chunks, COLUMNS, MIB, rows, write

parser = argparse.ArgumentParser()
parser.add_argument('--run', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
output = Path(args.output)
output.mkdir(parents=True, exist_ok=False)
changes = Chunks(output, 'empty-eof-corrections', 4 * MIB)
summary = []
for root in sorted(Path(args.run).glob('E1-*')):
    if not (root / 'result.json').exists():
        continue
    changed = 0
    for row in rows(root, 'client'):
        record = dict(zip(COLUMNS, row))
        if empty_eof(record):
            changes.row({'cell': root.name, 'id': record['id'], 'old': 'protocol_error',
                         'new': 'transport_failure', 'rx': 0, 'wire': None, 'body': None,
                         'http': None, 'error': record['error']})
            changed += 1
    result = audit(root, correct_empty_eof=True)
    original = json.loads((root / 'result.json').read_text())
    result['resources'] = original['metrics']['resources']
    result['drained'] = original['metrics']['drained']
    result['classification_version'] = 'empty-eof-v2'
    result['changed_all_phase_ids'] = changed
    result['raw_cell'] = str(root)
    write(output / (root.name + '.json'), result)
    summary.append({k: result[k] for k in ['id', 'rate', 'good_fraction', 'generator_valid', 'exploration_slo_pass', 'changed_all_phase_ids']})
changes.close()
write(output / 'summary.json', summary)
print(json.dumps(summary, indent=2))
