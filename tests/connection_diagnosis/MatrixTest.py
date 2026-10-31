"""Synthetic controller/gate tests: no process, socket or product invocation."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import Matrix as M


def metrics():
    names=('controller','generator-0','generator-1','backend-0','gateway-0','gateway-1','l4lb')
    return dict(planned=38400,good_fraction=1,generator_valid=True,corruption_all_phases=0,
                latency_ms={'http':{'p95':2,'p99':3}},resources={'processes':{n:dict(first={'ticks':0},last={'ticks':100},ticks_per_second=100,window_seconds=19.8) for n in names}})


class Tests(unittest.TestCase):
    def test_exact_matrix_counts_and_rotation(self):
        for role in ('builder','reviewer'):
            p=M.plan(role);self.assertEqual(len(p),18);self.assertEqual(len({x['id'] for x in p}),18)
            self.assertEqual(sum(x['stage']=='low' for x in p),9);self.assertEqual(sum(x['stage']=='negative' for x in p),3)
        self.assertEqual([s['variant'] for s in M.plan('reviewer')[3:6]],['T','O','U'])

    def test_gate_requires_every_repeat_and_cpu_role(self):
        low=[dict(spec=s,metrics=metrics()) for s in M.plan('builder') if s['stage']=='low']
        self.assertTrue(M.gates(low,'low')['passed'])
        low[-1]['metrics']['latency_ms']['http']['p99']=4
        self.assertFalse(M.gates(low,'low')['passed'])
        low[-1]['metrics']['resources']['processes'].pop('backend-0')
        with self.assertRaises(ValueError):M.gates(low,'low')

    def test_invalid_generator_blocks_even_if_good(self):
        high=[dict(spec=s,metrics=metrics()) for s in M.plan('builder') if s['stage']=='high']
        high[0]['metrics']['generator_valid']=False
        self.assertFalse(M.gates(high,'high')['passed'])

    def run_mocked(self,folder,fail_at=None,low_bad=False):
        plan=M.plan('builder');calls=[]
        manifest=dict(output=str(Path(folder)/'run'),cells=plan,binaries={k:dict(gateway='fake',l4lb='fake') for k in ('U','trace')})
        def cell(spec,args):
            calls.append(spec['id'])
            if len(calls)==fail_at:raise RuntimeError('injected first failure')
            result=metrics()
            if low_bad and spec['stage']=='low':result['good_fraction']=.98
            return result
        with patch.object(M,'verify'):
            if fail_at:
                with self.assertRaises(RuntimeError):M.run(manifest,'fake-sha',cell,cell)
            else:M.run(manifest,'fake-sha',cell,cell)
        return calls,json.loads((Path(folder)/'run/summary.json').read_text())

    def test_two_plus_cells_checkpoint_and_single_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            calls,result=self.run_mocked(folder)
            self.assertEqual(len(calls),18);self.assertEqual(result['status'],'complete')
            self.assertEqual(len(list((Path(folder)/'run').glob('checkpoint-*.json'))),18)

    def test_failure_first_stop_preserves_attempted(self):
        with tempfile.TemporaryDirectory() as folder:
            calls,result=self.run_mocked(folder,fail_at=2)
            self.assertEqual(len(calls),2);self.assertEqual(len(result['verified_ids']),1)
            self.assertEqual(len(result['not_started_ids']),16);self.assertEqual(result['status'],'failed')

    def test_low_gate_blocks_all_six_high_cells(self):
        with tempfile.TemporaryDirectory() as folder:
            calls,result=self.run_mocked(folder,low_bad=True)
            self.assertEqual(len(calls),12);self.assertEqual(result['status'],'blocked-low-overhead')

    def test_preflight_failure_has_closure(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=dict(output=folder,cells=[])
            with patch.object(M,'verify',side_effect=ValueError('preflight mismatch')):
                with self.assertRaises(RuntimeError):M.run(manifest,'fake')
            result=json.loads((Path(folder)/'summary.json').read_text())
            self.assertEqual(result['status'],'failed');self.assertEqual(result['attempted_ids'],[])

    def test_early_reserved_cell_is_failed(self):
        from TraceRuntime import Ledger,preserve_early_failure
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            @preserve_early_failure
            def fail(spec,args):
                Ledger(args.output).reserve(spec);raise OSError('spec write')
            with self.assertRaises(OSError):fail(dict(id='early',stage='negative'),SimpleNamespace(output=folder))
            self.assertEqual(Ledger(folder).data['cells'][0]['state'],'failed')
            self.assertTrue((Path(folder)/'early/early-failure.json').exists())

    def test_whole_budget_before_cell(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=dict(output=folder,cells=M.plan('builder'),binaries={})
            with patch.object(M,'verify'),patch.object(M.time,'monotonic',side_effect=[0,1141,1141,1141,1141]):
                with self.assertRaises(RuntimeError):M.run(manifest,'fake',lambda *_:self.fail('must not start'))
            result=json.loads((Path(folder)/'summary.json').read_text());self.assertEqual(result['attempted_ids'],[])

if __name__=='__main__':unittest.main(verbosity=2)
