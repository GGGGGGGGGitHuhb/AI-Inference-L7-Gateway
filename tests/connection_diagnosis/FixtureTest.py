"""Pure predicates for Approved rework002; no process or socket creation."""
import importlib.util
from pathlib import Path
import unittest
import os

p=Path(os.environ.get('TRACE_L4_SOURCE', 'build-local/builder/v0.6-s2-trace/l4-source'))/'tests/v04_shutdown_product.py'
spec=importlib.util.spec_from_file_location('shutdown_fixture',p)
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


class Test(unittest.TestCase):
    def test_exhausted_source_plateau_is_not_backpressure(self):
        row=dict(bytes_c2b_total=173768,bytes_b2c_total=108608)
        self.assertIsNone(fixture.backpressure_ready([row,row],[173760,173760],[True,True]))
    def test_fresh_blocked_and_both_outstanding_required(self):
        row=dict(bytes_c2b_total=100,bytes_b2c_total=200)
        self.assertIsNotNone(fixture.backpressure_ready([row,row],[300,400],[True,True]))
        self.assertIsNone(fixture.backpressure_ready([row,row],[300,400],[False,True]))
        self.assertIsNone(fixture.backpressure_ready([row],[300,400],[True,True]))
    def test_fixed_time_and_submission_limits(self):
        self.assertTrue(fixture.preparation_budget_ok([0,0],0))
        self.assertFalse(fixture.preparation_budget_ok([0,16*1024*1024],1))
        self.assertFalse(fixture.preparation_budget_ok([0,0],16))


if __name__=='__main__':unittest.main(verbosity=2)
