"""No-load negative controls for parser, accounting and hard artifact reservations."""
import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest
from Common import Chunks, COLUMNS, MIB, digest, payload, write
from Client import Response, ProtocolError
from Analyze import audit
from Runtime import Ledger


class Checks(unittest.TestCase):
    def test_frame_negative_controls(self):
        async def parse(data):
            reader = asyncio.StreamReader()
            reader.feed_data(data)
            reader.feed_eof()
            row = dict.fromkeys(COLUMNS) | {'rx': 0}
            return await Response(reader, row).read()
        for head in [b'Transfer-Encoding: chunked\r\nContent-Length: 1\r\n\r\n0\r\n\r\n',
                     b'Content-Length: +1\r\n\r\nx', b'Content-Length: 1_0\r\n\r\nxxxxxxxxxx',
                     b'Transfer-Encoding: chunked\r\n\r\n+1\r\nx\r\n0\r\n\r\n',
                     b'Transfer-Encoding: chunked\r\n\r\n0x1\r\nx\r\n0\r\n\r\n',
                     b'Content-Length: 1\r\n\r\nxy', b'Content-Length: 2\r\n\r\nx']:
            with self.assertRaises(ProtocolError):
                asyncio.run(parse(b'HTTP/1.1 200 OK\r\n' + head))
        self.assertEqual(asyncio.run(parse(b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\nx')), b'x')

    def test_record_budget_rotation(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Chunks(folder, 'test', MIB + 10)
            output.put(b'x' * MIB)
            output.put(b'0123456789')
            with self.assertRaises(RuntimeError):
                output.put(b'x')
            output.close()
            self.assertEqual(sorted(p.stat().st_size for p in Path(folder).iterdir()), [10, MIB])

    def fixture(self, folder, mutation=None):
        spec = {'id': 'unit', 'path': 'B', 'workload': 'A', 'rate': 2, 'warm': 0,
                'duration': 1, 'start': 1_000_000_000, 'measure_start': 1_000_000_000}
        write(Path(folder) / 'spec.json', spec)
        output = Chunks(folder, 'client-0', MIB)
        back = Chunks(folder, 'backend', MIB)
        for i in range(2):
            identity = f'unit-f-{i}'
            scheduled = spec['measure_start'] + i * 500_000_000
            row = dict.fromkeys(COLUMNS) | dict(id=identity, phase='f', scheduled=scheduled,
                dispatch=scheduled + 1, connect=scheduled + 2, send=scheduled + 3,
                wire=scheduled + 4, body=scheduled + 5, http=scheduled + 6,
                eof=scheduled + 7, closed=scheduled + 8, outcome='success', status=200,
                tx=100, rx=1100, digest=digest(payload(identity, 'A')))
            if mutation:
                mutation(row, i)
            output.row([row[k] for k in COLUMNS])
            back.row([identity, i, scheduled, scheduled + 8, 100, 1100, 'complete'])
        output.close()
        back.close()

    def test_missing_duplicate_bad_body_clock(self):
        for mutate in [lambda row, i: row.update(id='unit-f-0'),
                       lambda row, i: row.update(digest='bad'),
                       lambda row, i: row.update(scheduled=row['scheduled'] + 1),
                       lambda row, i: row.update(outcome='not_sent')]:
            with tempfile.TemporaryDirectory() as folder:
                self.fixture(folder, mutate)
                with self.assertRaises(ValueError):
                    audit(folder)
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(folder)
            path = next(Path(folder).glob('client-*.jsonl'))
            path.write_text(path.read_text().splitlines()[0] + '\n')
            with self.assertRaises(ValueError):
                audit(folder)

    def test_goodput_includes_drain(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(folder)
            self.assertEqual(audit(folder)['goodput'], 2)
            # Shift the final scheduled request to 999ms and completion into drain.
            spec = json.loads((Path(folder) / 'spec.json').read_text())
            spec['rate'], spec['duration'] = 1000, .002
            (Path(folder) / 'spec.json').write_text(json.dumps(spec))
            path = next(Path(folder).glob('client-*.jsonl'))
            records = [json.loads(line) for line in path.read_text().splitlines()]
            for i, row in enumerate(records):
                origin = spec['measure_start'] + i * 1_000_000
                row[2] = origin
                for j in range(3, 11):
                    row[j] = origin + 2_000_000 + j
            path.write_text(''.join(json.dumps(row) + '\n' for row in records))
            self.assertEqual(audit(folder)['goodput'], 1000)

    def test_record_hard_cap_no_truncation(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Chunks(folder, 'bounded', MIB, row_limit=512)
            row = dict.fromkeys(COLUMNS) | dict(id='X' * 48 + '-f-88319', phase='f',
                scheduled=2**64-1, dispatch=2**64-1, connect=2**64-1, send=2**64-1,
                wire=2**64-1, body=2**64-1, http=2**64-1, eof=2**64-1, closed=2**64-1,
                outcome='success', status=200, tx=4096, rx=32768, digest='f'*64)
            output.row([row[k] for k in COLUMNS])
            before = output.total
            row['error'] = 'x' * 4096
            with self.assertRaises(RuntimeError):
                output.row([row[k] for k in COLUMNS])
            self.assertEqual(output.total, before)
            output.close()

    def test_formal_manifest_integrity(self):
        import hashlib
        from Formal import validate, worst_bytes
        root = Path(__file__).resolve().parents[2]
        manifest = json.loads((root / 'tests/capacity/manifest-example.json').read_text())
        manifest['status'] = 'Frozen'
        reference = {'path': str(root / 'tests/capacity/manifest-example.json'), 'sha256': hashlib.sha256((root / 'tests/capacity/manifest-example.json').read_bytes()).hexdigest()}
        manifest['selection'] = {'calibration': [reference]}
        manifest['environment'] = manifest['sources'] = reference
        manifest['tools'] = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in (root / 'tests/capacity').glob('*.py')}
        validate(manifest)
        self.assertEqual(worst_bytes(manifest), 1930715136)
        for change in ['missing', 'duplicate', 'timing', 'tool', 'rotation']:
            bad = copy.deepcopy(manifest)
            if change == 'missing':
                bad['cells'].pop()
            elif change == 'duplicate':
                bad['cells'][1] = bad['cells'][0]
            elif change == 'timing':
                bad['cells'][0]['duration'] = 21
            elif change == 'tool':
                bad['tools'][next(iter(bad['tools']))] = 'wrong'
            else:
                bad['cells'][0], bad['cells'][1] = bad['cells'][1], bad['cells'][0]
            with self.assertRaises(ValueError):
                validate(bad)

    def test_formal_corruption_stops_with_plan_retained(self):
        from contextlib import redirect_stdout
        import io
        from types import SimpleNamespace
        from unittest.mock import patch
        from Formal import run
        root = Path(__file__).resolve().parents[2]
        manifest = json.loads((root / 'tests/capacity/manifest-example.json').read_text())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'manifest.json'
            path.write_text(json.dumps(manifest))
            args = SimpleNamespace(manifest=str(path), output=str(Path(folder) / 'run'),
                                   gateway=str(path), l4lb=str(path))
            result = dict(id='injected', good_fraction=0, generator_valid=True,
                          outcomes={'body_error': 1}, corruption_all_phases=1)
            with patch('Formal.validate', return_value=manifest), patch('Formal.verify_sources'), \
                    patch('Run.cell', return_value=result) as execute, redirect_stdout(io.StringIO()):
                with self.assertRaises(RuntimeError):
                    run(args)
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(len(json.loads((Path(args.output) / 'formal-plan.json').read_text())['cells']), 72)

    def test_l4_cross_file_session_conservation(self):
        with tempfile.TemporaryDirectory() as folder:
            self.fixture(folder)
            path = Path(folder) / 'spec.json'
            spec = json.loads(path.read_text())
            spec['path'] = 'L'
            path.write_text(json.dumps(spec))
            log = Chunks(folder, 'log-l4lb', 2*MIB)
            data = b'#' * (MIB-10) + b'\n'
            for index in range(2):
                data += f'session={index} backend=127.0.0.1:12345 reason=accepted\n'.encode()
                data += f'session={index} backend=127.0.0.1:12345 reason=drained sent_c2b=100 sent_b2c=1100\n'.encode()
            for begin in range(0, len(data), 32768):
                log.put(data[begin:begin+32768])
            log.close()
            self.assertEqual(audit(folder)['l4']['closed'], 2)
            final = sorted(Path(folder).glob('log-l4lb-*.jsonl'))[-1]
            final.write_bytes(final.read_bytes()[:-1])
            with self.assertRaises(ValueError):
                audit(folder)

    def test_multitoken_l4_reason_and_rejected_session_lines(self):
        for corrupt in ['none', 'duplicate', 'missing', 'unknown', 'endpoint']:
            with tempfile.TemporaryDirectory() as folder:
                self.fixture(folder)
                path = Path(folder) / 'spec.json'
                spec = json.loads(path.read_text())
                spec['path'] = 'L'
                path.write_text(json.dumps(spec))
                accepted = [f'session={i} backend=127.0.0.1:12345 reason=accepted\n' for i in range(2)]
                closed = [f'session={i} backend=127.0.0.1:12345 reason=shutdown SHUT_WR sent_c2b=100 sent_b2c=1100 errno=107 Transport endpoint is not connected\n' for i in range(2)]
                lines = accepted + closed
                if corrupt == 'duplicate':
                    lines.append(closed[0])
                elif corrupt == 'missing':
                    lines.pop()
                elif corrupt == 'unknown':
                    lines.append('prefix session=3 malformed\n')
                elif corrupt == 'endpoint':
                    lines[-1] = lines[-1].replace(':12345', ':54321')
                (Path(folder) / 'log-l4lb-0000.jsonl').write_text(''.join(lines))
                if corrupt == 'none':
                    self.assertEqual(audit(folder)['l4']['closed'], 2)
                else:
                    with self.assertRaises(ValueError):
                        audit(folder)

    def test_rework_prefix_and_raw_fingerprint_guards(self):
        from Resume import PREFIX, check_prefix, fingerprints, check_fingerprints
        original = {'cells': [dict(id=identity, kind='formal', state='complete' if i < 6 else 'failed')
                              for i, identity in enumerate(PREFIX)]}
        check_prefix(original)
        for operation in ['short', 'long', 'unexpected_failure', 'running', 'auxiliary']:
            value = copy.deepcopy(original)
            if operation == 'short':
                value['cells'].pop()
            elif operation == 'long':
                value['cells'].append(dict(id='extra', kind='formal', state='complete'))
            elif operation == 'unexpected_failure':
                value['cells'][0]['state'] = 'failed'
            elif operation == 'running':
                value['cells'][-1]['state'] = 'running'
            else:
                value['auxiliary'] = [{'state': 'running'}]
            with self.assertRaises(ValueError):
                check_prefix(value)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'raw').write_text('original')
            expected = fingerprints(root)
            check_fingerprints(root, expected)
            (root / 'raw').write_text('altered')
            with self.assertRaises(ValueError):
                check_fingerprints(root, expected)

    def test_monitor_confirmed_exit_and_live_permission_evidence(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from Runtime import Monitor
        for mode in ['exited', 'alive', 'controller']:
            with tempfile.TemporaryDirectory() as folder:
                monitor = Monitor.__new__(Monitor)
                monitor.phase, monitor.windows = 'requests', (0, 1)
                monitor.failure_recorded = False
                monitor.events = Chunks(folder, 'monitor-events', 65536, row_limit=8192)
                process = SimpleNamespace(pid=4242, poll=lambda: 0 if mode == 'exited' else None)
                owned = SimpleNamespace(process=process)
                with patch('Runtime.proc', side_effect=PermissionError(13, 'denied')):
                    if mode == 'exited':
                        self.assertIsNone(monitor.snapshot('owned', 4242, owned))
                    else:
                        with self.assertRaises(PermissionError):
                            monitor.snapshot(mode, 4242, None if mode == 'controller' else owned)
                monitor.events.close()
                event = json.loads(next(Path(folder).glob('monitor-events-*')).read_text())
                self.assertEqual(event['pid'], 4242)
                self.assertGreater(event['time_ns'], 0)
                self.assertEqual(event['phase'], 'request-drain')
                self.assertIn('PermissionError', event['traceback'])
                self.assertEqual(event['action'], 'skip-confirmed-exit' if mode == 'exited' else 'fatal')

    def test_only_disappeared_thread_enoent_is_ignored(self):
        from unittest.mock import patch
        from Common import proc
        for mode in ['gone', 'alive_missing_stat', 'permission']:
            with tempfile.TemporaryDirectory() as folder:
                base = Path(folder)
                process = base / '123'
                (process / 'fd').mkdir(parents=True)
                (process / 'stat').write_text('123 (test) ' + ' '.join(['0']*20))
                (process / 'statm').write_text('1 1')
                missing = process / 'task' / '999' / 'stat'
                if mode != 'gone':
                    missing.parent.mkdir(parents=True)
                original_read = Path.read_text
                def read(path, *args, **kwargs):
                    if path == missing and mode == 'permission':
                        raise PermissionError(13, 'denied')
                    return original_read(path, *args, **kwargs)
                with patch('Common.Path', side_effect=lambda p: base if p == '/proc' else Path(p)), \
                        patch.object(Path, 'glob', return_value=[missing]), \
                        patch.object(Path, 'read_text', read), patch('Common.os.sched_getaffinity', return_value={0}):
                    if mode == 'gone':
                        value = proc(123)
                        self.assertEqual(value['unavailable_exited_threads'], ['999'])
                        self.assertEqual(value['ticks'], 0)
                    else:
                        with self.assertRaises(PermissionError if mode == 'permission' else FileNotFoundError):
                            proc(123)

    def test_second_resume_exact_prefix_only(self):
        from Resume import PREFIX2, check_prefix
        value = {'cells': [dict(id=identity, kind='formal', state='failed' if i in (6,17) else 'complete')
                           for i,identity in enumerate(PREFIX2)]}
        check_prefix(value, second=True)
        with self.assertRaises(ValueError):
            check_prefix(value)
        for index in [0,6,17]:
            altered = copy.deepcopy(value)
            altered['cells'][index]['state'] = 'failed' if index == 0 else 'complete'
            with self.assertRaises(ValueError):
                check_prefix(altered, second=True)

    def test_resume_process_set_matches_frozen_topology(self):
        from Resume import check_processes
        manifest = {'configuration': {'backends': 1}, 'workloads': {'A': {'workers': 2}, 'S': {'workers': 1}}}
        for workload in 'AS':
            for path in 'BGML':
                names = ['backend-0'] + [f'generator-{i}' for i in range(manifest['workloads'][workload]['workers'])]
                names += [f'gateway-{i}' for i in range(0 if path == 'B' else (1 if path == 'G' else 2))]
                if path == 'L':
                    names.append('l4lb')
                processes = [dict(name=name, pid=100+i, returncode=0) for i,name in enumerate(names)]
                spec = {'workload': workload, 'path': path}
                check_processes(processes, spec, manifest)
                for changed in [processes[:-1], processes+[processes[0]], [processes[0]]*len(processes)]:
                    with self.assertRaises(ValueError):
                        check_processes(changed, spec, manifest)

    def test_bounded_exit_confirmation_only_outside_real_window(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        import subprocess
        from Runtime import Monitor
        cases = ['immediate', 'delayed', 'timeout', 'measurement', 'false_phase', 'controller', 'already_exited_inside']
        for error_type in (PermissionError, FileNotFoundError, ProcessLookupError):
            for mode in cases:
                with tempfile.TemporaryDirectory() as folder:
                    monitor = Monitor.__new__(Monitor)
                    monitor.phase = 'fd-drain' if mode == 'false_phase' else 'requests'
                    monitor.windows = (0, 1000 if mode in ('measurement', 'false_phase', 'already_exited_inside') else 100)
                    monitor.failure_recorded = False
                    monitor.events = Chunks(folder, 'monitor-events', 65536, row_limit=8192)
                    process = Mock()
                    process.poll.return_value = 0 if mode in ('immediate', 'already_exited_inside') else None
                    process.wait.return_value = 0
                    if mode == 'delayed':
                        def finish(**kwargs):
                            monitor.phase = 'cleanup'
                            return 0
                        process.wait.side_effect = finish
                    if mode == 'timeout':
                        process.wait.side_effect = subprocess.TimeoutExpired('owned', .1)
                    owned = SimpleNamespace(process=process)
                    with patch('Runtime.proc', side_effect=error_type(13, 'read failed')), patch('Runtime.now', side_effect=[200, 220, 300]):
                        if mode in ('immediate', 'delayed'):
                            self.assertIsNone(monitor.snapshot('owned', 42, owned))
                        else:
                            with self.assertRaises(error_type):
                                monitor.snapshot(mode, 42, None if mode == 'controller' else owned)
                    monitor.events.close()
                    event = json.loads(next(Path(folder).glob('monitor-events-*')).read_text())
                    self.assertEqual(event['time_ns'], 200)
                    if mode == 'delayed':
                        self.assertEqual(event['phase'], 'request-drain')
                    if mode in ('delayed', 'timeout'):
                        process.wait.assert_called_once_with(timeout=.1)
                        self.assertEqual(event['exit_wait_start_ns'], 220)
                        self.assertEqual(event['exit_wait_end_ns'], 300)
                        self.assertEqual(event['exit_wait_elapsed_ns'], 80)
                    else:
                        process.wait.assert_not_called()
                    self.assertEqual(event['exit_wait_timed_out'], mode == 'timeout')
                    self.assertEqual(event['action'], 'skip-confirmed-exit' if mode in ('immediate','delayed') else 'fatal')
                    process.terminate.assert_not_called()
                    process.kill.assert_not_called()
                    process.send_signal.assert_not_called()

    def test_third_resume_prefix_only(self):
        from Resume import PREFIX3, check_prefix
        value = {'cells': [dict(id=identity, kind='formal', state='failed' if i in (6,17,32) else 'complete')
                           for i,identity in enumerate(PREFIX3)]}
        check_prefix(value, second=True, third=True)
        with self.assertRaises(ValueError):
            check_prefix(value, second=True)
        value['cells'][32]['state'] = 'complete'
        with self.assertRaises(ValueError):
            check_prefix(value, second=True, third=True)

    def test_reviewer_prefix_is_distinct_from_builder(self):
        import copy
        from Resume import PREFIX3, check_prefix
        original = {'cells': [dict(id=identity, kind='formal', state='failed' if i == 32 else 'complete')
                              for i, identity in enumerate(PREFIX3)]}
        check_prefix(original, reviewer=True)
        with self.assertRaises(ValueError):
            check_prefix(original, second=True, third=True)
        for change in ('builder_states', 'missing', 'extra', 'running_auxiliary', 'no_failure'):
            value = copy.deepcopy(original)
            if change == 'builder_states':
                value['cells'][6]['state'] = value['cells'][17]['state'] = 'failed'
            elif change == 'missing':
                value['cells'].pop()
            elif change == 'extra':
                value['cells'].append(dict(value['cells'][-1]))
            elif change == 'running_auxiliary':
                value['auxiliary'] = [{'state': 'running'}]
            else:
                value['cells'][32]['state'] = 'complete'
            with self.assertRaises(ValueError):
                check_prefix(value, reviewer=True)

    def test_reviewer_parent_profile_and_matrix_are_bound(self):
        import copy
        from Resume import ROOT, PREFIX3, V4_SHA, REWORK4, REVIEWER_PROFILE, check_parent_manifest
        manifest = json.loads((ROOT / 'docs/performance/V0.6/S1-manifest-v4.json').read_text())
        candidate = copy.deepcopy(manifest)
        candidate['continuation'] = {'profile': REVIEWER_PROFILE, 'rework': REWORK4,
                                     'parent_manifest_sha256': V4_SHA, 'prefix_ids': PREFIX3,
                                     'parent_manifest_path': 'docs/performance/V0.6/S1-manifest-v4.json'}
        self.assertEqual(check_parent_manifest(candidate), manifest)
        for change in ('profile', 'parent', 'matrix', 'prefix'):
            changed = copy.deepcopy(candidate)
            if change == 'profile':
                changed['continuation']['profile'] = 'builder'
            elif change == 'parent':
                changed['continuation']['parent_manifest_sha256'] = '0' * 64
            elif change == 'matrix':
                changed['configuration']['capacity'] = 64
            else:
                changed['continuation']['prefix_ids'] = PREFIX3[:-1]
            with self.assertRaises(ValueError):
                check_parent_manifest(changed)

    def test_cumulative_reservation_and_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = Ledger(folder)
            spec = dict(id='unit', kind='E1', path='B', rate=60, warm=2, duration=5)
            entry = ledger.reserve(spec)
            self.assertEqual(Ledger(folder).data['active_seconds'], 45)
            with self.assertRaises(RuntimeError):
                ledger.reserve(spec)
            ledger.close(entry, 3, 'failed')
            self.assertEqual(Ledger(folder).data['active_seconds'], 3)
            with self.assertRaises(RuntimeError):
                ledger.reserve(spec)
            ledger.data['active_seconds'] = 5400
            with self.assertRaises(RuntimeError):
                ledger.reserve(spec | {'id': 'later'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
