"""Interrupt the controller with live requests and verify retained terminal records."""
import argparse
import json
import os
from pathlib import Path
import signal
import threading
from types import SimpleNamespace
from Run import cell

parser = argparse.ArgumentParser()
parser.add_argument('--output', required=True)
parser.add_argument('--gateway', required=True)
parser.add_argument('--l4lb', required=True)
parser.add_argument('--id', default='E0-interrupt')
args = SimpleNamespace(**vars(parser.parse_args()), slots=128, workers=1, capacity=32,
                       backends=1, reuse=False, nodelay=1, fault='timeout')
def interrupted(*_):
    raise KeyboardInterrupt('negative control SIGTERM')
signal.signal(signal.SIGTERM, interrupted)
timer = threading.Timer(3, lambda: os.kill(os.getpid(), signal.SIGTERM))
timer.start()
try:
    try:
        cell(dict(id=args.id, kind='diagnostic', path='B', workload='A', rate=60, warm=0, duration=5), args)
    except RuntimeError:
        pass
    else:
        raise AssertionError('interruption returned success')
finally:
    timer.cancel()
    timer.join()
root = Path(args.output) / args.id
result = json.loads((root / 'result.json').read_text())
assert result['error'] and result['metrics'], result
assert result['metrics']['planned'] == 300
assert result['metrics']['backend_ids'] > 0
assert all(p['returncode'] == 0 for p in json.loads((root / 'processes.json').read_text()) if p['name'].startswith('backend'))
assert result['metrics']['outcomes'].get('interrupted', 0) > 0
assert result['metrics']['outcomes'].get('not_started', 0) > 0
for process in json.loads((root / 'processes.json').read_text()):
    assert not Path('/proc/' + str(process['pid'])).exists(), process
print(json.dumps(result))
