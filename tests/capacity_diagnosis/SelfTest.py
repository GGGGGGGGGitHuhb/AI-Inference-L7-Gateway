"""No network/load: fixed matrix, protection, failure paths, and taskset ownership."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import Diagnosis as D
from types import SimpleNamespace


class Tests(unittest.TestCase):
    def test_matrix_and_role_order(self):
        builder, reviewer = D.matrix('builder'), D.matrix('reviewer')
        self.assertEqual(len({x['id'] for x in builder}), 12)
        for r in range(3):
            self.assertEqual(reviewer[4*r:4*r+4], builder[4*r:4*r+4][::-1])
        self.assertEqual(sum(x['backend_workers']==2 for x in builder), 3)
        with self.assertRaises(ValueError):
            D.matrix('unknown')

    def test_distinct_physical_core_mapping(self):
        topology = [dict(cpu=i, core=i//2, package=0) for i in range(14)]
        self.assertEqual(list(D.cpu_map(topology).values()), list(range(0,14,2)))
        with self.assertRaises(ValueError):
            D.cpu_map(topology[:12])

    def test_whole_matrix_budget(self):
        cells = D.matrix('builder')
        self.assertEqual(D.reservation(cells[2]), 3840*23*(512+384+256)+3*D.MIB+D.CELL_METADATA)
        self.assertLess(sum(map(D.reservation,cells))+D.CLOSURE, D.LIMIT)
        with tempfile.TemporaryDirectory() as folder:
            ledger = D.DiagnosisLedger(folder)
            with patch.object(D, 'used', return_value=D.LIMIT):
                with self.assertRaises(RuntimeError):
                    ledger.reserve(cells[0])
            ledger.data['active_seconds'] = 496
            with self.assertRaises(RuntimeError):
                ledger.reserve(cells[0])

    def test_failure_reservation_and_duplicate(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = D.DiagnosisLedger(folder)
            spec = D.matrix('builder')[0]
            entry = ledger.reserve(spec)
            self.assertEqual(ledger.data['active_seconds'],45)
            with self.assertRaises(RuntimeError):
                ledger.reserve(D.matrix('builder')[1])
            ledger.close(entry, 1, 'failed')
            with self.assertRaises(RuntimeError):
                ledger.reserve(spec)
            self.assertEqual(ledger.data['cells'][0]['state'],'failed')

    def test_source_mismatch_stops(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'source.json'
            previous={r:dict(files={'x':'old'},source_diff='',head='old') for r in ('gateway','l4lb')}
            previous['binaries']={'g':'hash','l':'hash'}
            p.write_text(json.dumps(previous))
            with patch.object(D,'identity',return_value=dict(files={'x':'new'},source_diff='',head='new')), patch.object(D,'sha',return_value='hash'):
                with self.assertRaises(ValueError):
                    D.source_check(p,'g','l')
            with patch.object(D,'identity',return_value=dict(files={'x':'old'},source_diff='',head='new')), patch.object(D,'sha',return_value='hash'):
                self.assertEqual(D.source_check(p,'g','l')['gateway']['head'],'new')

    def test_affinity_mismatch_or_absence_fails(self):
        row={'processes':{'controller':{'affinity':[1]}}}
        with patch.object(D,'rows',return_value=iter([row])):
            self.assertEqual(D.check_affinities('.',{'controller':1},[0,1],{'controller'}),1)
        with patch.object(D,'rows',return_value=iter([row])):
            with self.assertRaises(ValueError):
                D.check_affinities('.',{'controller':2},[0,1],{'controller'})
        with patch.object(D,'rows',return_value=iter([row])):
            with self.assertRaises(ValueError):
                D.check_affinities('.',{'controller':1},[0,1],{'controller','backend-0'})
        with patch.object(D,'rows',return_value=iter([])):
            with self.assertRaises(ValueError):
                D.check_affinities('.',{},[0,1],{'controller'})

    def test_taskset_actual_child_and_capture_cleanup(self):
        cpu=min(os.sched_getaffinity(0))
        original_affinity = os.sched_getaffinity(0)
        self.addCleanup(os.sched_setaffinity, 0, original_affinity)
        os.sched_setaffinity(0, [cpu])
        with tempfile.TemporaryDirectory() as folder:
            owned=D.owned_factory({'backend-0':cpu, 'controller':cpu},D.shutil.which('taskset'))(
                [sys.executable,'-c','import time; print("READY",flush=True); time.sleep(.05)'],
                'backend-0',Path(folder),65536)
            owned.process.wait(timeout=2)
            record=owned.close()
            self.assertEqual(record['returncode'],0)
            self.assertEqual(record['affinity_at_start'],[cpu])
            self.assertFalse(owned.thread.is_alive())
            self.assertFalse(Path('/proc',str(record['pid'])).exists())
            with self.assertRaises(ValueError):
                D.owned_factory({'backend-0':cpu, 'controller':cpu},'taskset')([], 'unknown', Path(folder),65536)

    def test_activity_budget_includes_wrapper_time(self):
        with patch.object(D.time, 'monotonic', return_value=600):
            self.assertEqual(D.activity_guard(100, 40),500)
            with self.assertRaises(RuntimeError): D.activity_guard(100,45)
            with self.assertRaises(RuntimeError): D.activity_guard(0)

    def test_two_cells_have_unique_checkpoint_and_final_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            cells=D.matrix('builder')[:2]
            manifest=dict(cells=cells,worst_matrix_bytes=100,taskset='taskset',gateway='g',l4lb='l',cpu_map={})
            path=Path(folder)/'manifest.json';path.write_text(json.dumps(manifest))
            output=Path(folder)/'run'
            args=SimpleNamespace(manifest=str(path),sha256=D.sha(path),output=str(output))
            def fake_cell(spec, options):
                cellroot=output/spec['id'];cellroot.mkdir()
                (cellroot/'result.json').write_text('{}')
                (cellroot/'spec.json').write_text('{"measure_start":0}')
                names=['MainThread','resource-monitor']+['capture-'+name for name in
                       ['backend-0','gateway-0','gateway-1','generator-0','generator-1']+(['l4lb'] if spec['path']=='L' else [])]
                (cellroot/'affinity-startup-test.json').write_text(json.dumps({'threads':[{'name':n} for n in names]}))
                return {'corruption_all_phases':0,'drained':True,'good_fraction':1,'outcomes':{}}
            with patch.object(D,'verify'),patch.object(D.Run,'cell',side_effect=fake_cell),patch.object(D,'check_affinities',return_value=1):
                D.run(args)
            self.assertEqual(len(list(output.glob('checkpoint-*.json'))),2)
            self.assertEqual(len(json.loads((output/'summary.json').read_text())),2)
            self.assertFalse((output/'stopped.json').exists())

    def test_duplicate_output_and_manifest_hash_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=Path(folder)/'manifest.json';manifest.write_text('{}')
            args=SimpleNamespace(manifest=str(manifest),sha256='wrong',output=str(Path(folder)/'run'))
            with self.assertRaises(ValueError): D.run(args)
            args.sha256=D.sha(manifest)
            Path(args.output).mkdir()
            with patch.object(D,'verify'):
                with self.assertRaises(ValueError): D.run(args)

    def test_first_correctness_failure_stops_without_second_cell(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=dict(cells=D.matrix('builder'),worst_matrix_bytes=100,taskset='taskset',gateway='g',l4lb='l',cpu_map={})
            path=Path(folder)/'manifest.json';path.write_text(json.dumps(manifest))
            args=SimpleNamespace(manifest=str(path),sha256=D.sha(path),output=str(Path(folder)/'run'))
            with patch.object(D,'verify'),patch.object(D.Run,'cell',return_value={'corruption_all_phases':1,'drained':True}) as cell:
                with self.assertRaises(RuntimeError): D.run(args)
                self.assertEqual(cell.call_count,1)
            stopped=json.loads((Path(args.output)/'stopped.json').read_text())
            self.assertEqual(len(stopped['not_started_ids']),11)
            self.assertEqual(stopped['failed_verification_ids'], ['P-M1-r0'])
            self.assertEqual(len(json.loads(path.read_text())['cells']),12)


if __name__ == '__main__':
    unittest.main(verbosity=2)
