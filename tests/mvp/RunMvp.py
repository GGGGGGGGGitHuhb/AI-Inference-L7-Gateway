"""Explicit bounded MVP run; output directory is immutable and every failure stays nonzero."""
import argparse
import platform
import signal
import time
from pathlib import Path

from Common import ROOT, check, save, sha, join_observations
from Budget import RunBudget
from Real import Matrix as RealMatrix
from Simulated import Matrix as SimulatedMatrix, COUNTS


def deadline(signum, frame):
    raise TimeoutError('fixed whole-run wall-clock guard')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['real', 'simulated'], required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--assets', default=str(ROOT / 'build-local/integration/v0.2-s3'))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    with RunBudget(output) as budget:
        try:
            execute(args, output, budget)
        except BaseException as error:
            save(output / 'result.json', {'status': 'FAIL', 'error': repr(error),
                 'budget_error': budget.error, 'charged_bytes': budget.used})
            raise


def execute(args, output, budget):
    expected = {group: count for group, count in [('R0', 8), ('R1', 8), ('R2', 6), ('R3', 6)]} if args.mode == 'real' else COUNTS
    save(output / 'plan.json', {'mode': args.mode, 'attempt_ids': [f'{group}-{i:02}' for group, count in expected.items() for i in range(1, count+1)]})
    sources = list((ROOT / 'tests/mvp').glob('*')) + list((ROOT / 'src').rglob('*.cpp')) + list((ROOT / 'src').rglob('*.h'))
    sources += [ROOT / 'tests/integration/Support.py', ROOT / 'tests/integration/WireResponse.py', ROOT / 'tests/integration/Inputs.json', ROOT / 'CMakeLists.txt']
    save(output / 'manifest.json', {'stage': 'V0.3/S3', 'mode': args.mode, 'arguments': vars(args),
        'platform': platform.platform(), 'started': time.time(), 'inputs_sha256': sha(ROOT / 'tests/integration/Inputs.json'),
        'host_sha256': sha(args.host), 'gateway_sha256': sha(args.gateway),
        'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in sources if p.is_file()}})
    signal.signal(signal.SIGALRM, deadline)
    signal.signal(signal.SIGTERM, deadline)
    signal.alarm(1800 if args.mode == 'real' else 120)
    started = time.monotonic()
    try:
        matrix = RealMatrix(args, output) if args.mode == 'real' else SimulatedMatrix(args.host, output)
        matrix.run()
        join_observations(output, args.mode)
        size = sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
        check(size <= 128 * 1024**2, 'run log 128MiB bound')
        budget.finish()
        save(output / 'result.json', {'status': 'PASS', 'seconds': time.monotonic() - started, 'bytes': size})
    except BaseException as error:
        save(output / 'result.json', {'status': 'FAIL', 'error': repr(error), 'seconds': time.monotonic() - started})
        raise
    finally:
        signal.alarm(0)


if __name__ == '__main__':
    main()
