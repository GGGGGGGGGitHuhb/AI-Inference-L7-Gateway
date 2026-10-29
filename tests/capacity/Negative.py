"""Live fault controls share the cumulative role ledger; no failed samples discarded."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from Common import write
from Run import cell


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--l4lb', required=True)
    args = parser.parse_args()
    args = SimpleNamespace(**vars(args), slots=128, workers=1, capacity=32, backends=1,
                           reuse=False, nodelay=1, fault='none')
    results = []
    for fault, workload, rate, slots, expected in [('timeout', 'A', 1, 128, 'client_deadline'),
                ('bad_body', 'A', 60, 128, 'body_error'), ('overload', 'S', 60, 1, 'http_rejection')]:
        args.fault, args.slots = fault, slots
        result = cell(dict(id='E0-' + fault, kind='diagnostic', path='B', workload=workload,
                           rate=rate, warm=0, duration=1), args)
        assert result['outcomes'].get(expected, 0) > 0, result
        assert not result['exploration_slo_pass'], result
        if fault == 'overload':
            assert result['outcomes'].get('not_sent', 0) > 0, result
        results.append(result)
        print(json.dumps(result), flush=True)
    write(Path(args.output) / 'negative-results.json', results)


if __name__ == '__main__':
    main()
