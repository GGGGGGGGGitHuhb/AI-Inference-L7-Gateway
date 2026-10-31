"""Synthetic forensic checks; no sockets or product processes."""
import json
from pathlib import Path
import tempfile
import unittest
from History import COLUMNS, inspect, lines


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'spec.json').write_text(json.dumps({'id': 'unit', 'backend_workers': 1,
            'path': 'L', 'warm': 0, 'duration': 1, 'rate': 1}))
        r = dict.fromkeys(COLUMNS)
        r.update(id='unit-f-0', phase='f', outcome='transport_failure', error='EOF before any response',
                 tx=200, rx=0, connect=1000000, closed=6000000)
        self.row = [r[k] for k in COLUMNS]
        (self.root / 'client-0-0000.jsonl').write_text(json.dumps(self.row) + '\n')
        (self.root / 'backend-0000.jsonl').write_text('')
        self.log = (b'session=1 backend=127.0.0.1:1234 reason=accepted\n'
                    b'session=1 backend=127.0.0.1:1234 reason=shutdown SHUT_WR sent_c2b=200 sent_b2c=0 errno=107 Transport endpoint is not connected\n')
        (self.root / 'log-l4lb-0000.jsonl').write_bytes(self.log[:80])
        (self.root / 'log-l4lb-0001.jsonl').write_bytes(self.log[80:])

    def test_split_multitoken_reason_and_phase(self):
        result = inspect(self.root)
        self.assertEqual(result['l4']['errno'], {'shutdown SHUT_WR:107': 1})
        self.assertEqual(result['phases']['f']['backend_by_outcome'], {})
        self.assertEqual(result['phases']['f']['failure_connected_lifetime_ms']['p50'], 5)
        self.assertEqual(result['phases']['w']['outcomes'], {})
        self.assertEqual((self.root / 'log-l4lb-0000.jsonl').read_bytes(), self.log[:80])

    def test_duplicate_client_rejected(self):
        with (self.root / 'client-0-0000.jsonl').open('a') as f:
            f.write(json.dumps(self.row) + '\n')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            inspect(self.root)

    def test_missing_close_rejected(self):
        (self.root / 'log-l4lb-0000.jsonl').write_bytes(self.log.splitlines(keepends=True)[0])
        (self.root / 'log-l4lb-0001.jsonl').write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'not conserved'):
            inspect(self.root)

    def test_truncated_log_rejected(self):
        (self.root / 'log-l4lb-0001.jsonl').write_bytes(self.log[80:-1])
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            inspect(self.root)

    def test_foreign_backend_rejected(self):
        (self.root / 'backend-0000.jsonl').write_text('["foreign"]\n')
        with self.assertRaisesRegex(ValueError, 'unknown/unsent'):
            inspect(self.root)

    def test_historical_empty_eof_explicit(self):
        self.row[COLUMNS.index('outcome')] = 'protocol_error'
        self.row[COLUMNS.index('error')] = 'missing delimiter'
        (self.root / 'client-0-0000.jsonl').write_text(json.dumps(self.row) + '\n')
        self.assertEqual(inspect(self.root)['phases']['f']['outcomes'], {'transport_failure': 1})


if __name__ == '__main__':
    unittest.main()
