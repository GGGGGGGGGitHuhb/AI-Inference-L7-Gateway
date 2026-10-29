"""Small adversarial checks of conservation, timing, byte accounting and budgets."""
import copy
import io
import tempfile
import unittest
from pathlib import Path
from Common import body, digest, COUNT, WARMUP, require
from Analyze import validate_rows, quantiles, sessions, audit
from Backend import Counted
from RunCosts import reserve, plan, MIB


def row(identity):
    return {'id': identity, 'outcome': 'success', 'status': 200, 'scheduled_ns': 1, 'dispatch_ns': 2,
            'connect_ns': 3, 'send_ns': 4, 'first_wire_ns': 5, 'head_ns': 6, 'first_body_ns': 7,
            'http_ns': 8, 'closed_ns': 9, 'body_sha256': digest(body(identity, 'A')),
            'tx_bytes': 10, 'rx_bytes': 20, 'target_port': 123}


def valid_cell():
    spec = {'id': 'A-0-L', 'path': 'L', 'workload': 'A', 'repeat': 0}
    warm = [row(f'A-0-L-w-{n:03}') for n in range(WARMUP)]
    rows = [row(f'A-0-L-f-{n:03}') for n in range(COUNT)]
    backend = {'accepts': COUNT + WARMUP, 'errors': [], 'records': [
        {'id': r['id'], 'error': None, 'rx_bytes': 10, 'tx_bytes': 20, 'started_ns': 4, 'ended_ns': 7}
        for r in warm + rows]}
    samples = [{'start_ns': 0, 'end_ns': 0, 'processes': {name: {'pid': n, 'ticks': 0, 'rss_bytes': 4096, 'fds': 7}
                 for n, name in enumerate(('client', 'backend', 'gateway-0', 'gateway-1', 'l4lb'))}},
               {'start_ns': 10, 'end_ns': 10, 'processes': {name: {'pid': n, 'ticks': 0, 'rss_bytes': 4096, 'fds': 7}
                 for n, name in enumerate(('client', 'backend', 'gateway-0', 'gateway-1', 'l4lb'))}}]
    logs = ''.join(f'session={n} backend=127.0.0.1:{123+n%2} reason=accepted\n'
                   f'session={n} backend=127.0.0.1:{123+n%2} reason=drained sent_c2b=10 sent_b2c=20\n'
                   for n in range(COUNT + WARMUP))
    return [spec, warm, rows, backend, samples, {'scheduled_start_ns': 1, 'warm_sessions': [str(n) for n in range(WARMUP)]}, logs]


class Detectors(unittest.TestCase):
    def test_complete_plan(self):
        cells = plan()
        self.assertEqual(len(cells), 18)
        ids = [identity for cell in cells for identity in cell['ids']]
        self.assertEqual(len(ids), 4536)
        self.assertEqual(len(set(ids)), 4536)

    def test_denominators_clocks_success(self):
        validate_rows([row('x')], ['x'], 'A')
        for changed in [[], [row('x'), row('x')]]:
            with self.assertRaises(AssertionError):
                validate_rows(changed, ['x'], 'A')
        for field, value in [('outcome', 'not_sent'), ('status', 503), ('http_ns', 0), ('body_sha256', 'wrong')]:
            changed = row('x')
            changed[field] = value
            with self.assertRaises(AssertionError):
                validate_rows([changed], ['x'], 'A')

    def test_actual_stream_bytes(self):
        source = Counted(io.BytesIO(b'POST / HTTP/1.1\r\nX:  a\r\n\r\nbody'))
        total = 0
        for _ in range(3):
            total += len(source.readline())
        total += len(source.read(4))
        self.assertEqual(total, source.count)
        destination = Counted(io.BytesIO())
        destination.write(b'4\r\nbody\r\n0\r\n\r\n')
        self.assertEqual(destination.count, 14)

    def test_network_audit_negative(self):
        values = valid_cell()
        result = audit(*values)
        self.assertEqual(result['network']['extra_l4_hop_bytes'], COUNT * 30)
        for mutation in ('bytes', 'warm', 'duplicate', 'backend', 'session_port'):
            values = valid_cell()
            if mutation == 'bytes':
                values[-1] = values[-1].replace('sent_b2c=20', 'sent_b2c=19')
            elif mutation == 'warm':
                values[-2]['warm_sessions'] = []
            elif mutation == 'duplicate':
                values[-1] += values[-1].splitlines()[0] + '\n'
            elif mutation == 'backend':
                values[3]['records'].pop()
            else:
                values[-1] = values[-1].replace('127.0.0.1:123 reason=drained', '127.0.0.1:999 reason=drained')
            with self.assertRaises(AssertionError):
                audit(*values)

    def test_quantile_threshold(self):
        self.assertNotIn('p95', quantiles(list(range(99))))
        self.assertEqual(quantiles(list(range(100)))['p95'], 94)
        self.assertNotIn('p99', quantiles(list(range(240))))

    def test_cumulative_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'previous-evidence'
            with path.open('wb') as file:
                file.truncate(44 * MIB)
            self.assertEqual(reserve(directory), 44 * MIB)
            with path.open('ab') as file:
                file.write(b'x')
            before = path.stat().st_size
            with self.assertRaises(AssertionError):
                reserve(directory)
            self.assertEqual(path.stat().st_size, before)


if __name__ == '__main__':
    unittest.main()
