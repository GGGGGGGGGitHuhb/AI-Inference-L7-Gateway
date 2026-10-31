"""No socket/load: binary conservation and conservative lifecycle association."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import Decode as D


def record(generation=1, start=10, end=30, port=30000, kind=1):
    return dict(generation=generation, times=[start,0,0,0,0,0,0,end,end,0,0,0],
                endpoints=[['127.0.0.1',8000],['127.0.0.1',port],['0.0.0.0',0],['0.0.0.0',0]],
                flags=3,kind=kind,process=[10,1])


class Tests(unittest.TestCase):
    def test_exact_tuple_and_overlap_only(self):
        idx=D.LifecycleIndex([record()],reverse=True)
        matched,status=idx.match(['127.0.0.1',30000],['127.0.0.1',8000],9,31)
        self.assertEqual(status,'unique');self.assertEqual(matched['generation'],1)
        for peer,start,end in [(['127.0.0.1',8001],9,31),(['127.0.0.1',8000],31,35)]:
            self.assertIsNone(idx.match(['127.0.0.1',30000],peer,start,end)[0])

    def test_reused_port_requires_disjoint_lifetime(self):
        idx=D.LifecycleIndex([record(),record(2,40,50)],reverse=True)
        self.assertEqual(idx.match(['127.0.0.1',30000],['127.0.0.1',8000],40,51)[0]['generation'],2)
        self.assertEqual(idx.match(['127.0.0.1',30000],['127.0.0.1',8000],15,45)[1],'ambiguous')

    def test_process_collision_is_not_guessed(self):
        a,b=record(),record();b['process']=[11,2]
        idx=D.LifecycleIndex([a,b],reverse=True)
        self.assertEqual(idx.match(['127.0.0.1',30000],['127.0.0.1',8000],9,31)[1],'ambiguous')

    def test_health_requires_explicit_record_and_flags(self):
        idx=D.LifecycleIndex([record(kind=2)],kind=3)
        self.assertIsNone(idx.match(['127.0.0.1',8000],['127.0.0.1',30000],9,31)[0])
        probe=record(kind=3);probe['flags']=1
        self.assertIsNone(D.LifecycleIndex([probe],kind=3).match(['127.0.0.1',8000],['127.0.0.1',30000],9,31)[0])

    def test_drop_and_incomplete_export_are_fatal(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            header=[D.MAGIC,1,256,131071,0,1,1,0,0,0,0,0,0,10,1,2,3]+[0]*15
            (p/'header.bin').write_bytes(D.HEADER.pack(*header))
            with self.assertRaises(ValueError):D.read_trace(p)
            header[5]=0;header[6]=0;header[4]=1
            (p/'header.bin').write_bytes(D.HEADER.pack(*header))
            with self.assertRaises(ValueError):D.read_trace(p)

    def test_owned_cleanup_notification_failure_still_reaps(self):
        from unittest.mock import Mock
        import TraceRuntime as R
        item=R.Owned.__new__(R.Owned)
        item.name='fake';item.process=Mock();item.thread=Mock();item.tail=b''
        item.error=None;item.bytes=item.blocks=item.write_ns=item.read_ns=0;item.trace_expected=False
        item.activity_deadline=0
        item.process.poll.return_value=None
        item.process.send_signal.side_effect=ProcessLookupError()
        item.process.kill.side_effect=lambda: setattr(item.process,'returncode',-9)
        item.process.wait.return_value=-9
        item.thread.is_alive.return_value=False
        with patch.object(R.time,'monotonic',side_effect=[1,14,14]):
            result=item.close()
        item.process.kill.assert_called_once();item.process.wait.assert_called_once_with(timeout=2)
        self.assertTrue(result['cleanup_error']);self.assertTrue(result['deadline_killed'])

    def test_close_all_exception_does_not_skip_other_child(self):
        from unittest.mock import Mock
        import TraceRuntime as R
        first,second=Mock(),Mock()
        for i,item in enumerate((first,second)):
            item.name=str(i);item.process.pid=100+i
            item.process.poll.return_value=None
            item.process.wait.return_value=-9
        second.request_stop.side_effect=TimeoutError('notify deadline')
        second.close.side_effect=TimeoutError('close deadline')
        first.close.return_value={'name':'first','returncode':0}
        records,errors=R.close_all([first,second])
        self.assertEqual(len(records),2);self.assertTrue(errors)
        second.process.kill.assert_called_once();second.process.wait.assert_called_once()
        first.close.assert_called_once()

    def test_cleanup_alarm_is_recorded_without_skipping_reap(self):
        import signal
        from types import SimpleNamespace
        from unittest.mock import Mock
        import RunCell as R
        owned=[]
        class FakeOwned:
            variant='U';activity_deadline=0
            def __init__(self,command,name,root,limit):
                self.name=name;self.process=Mock();self.process.pid=100+len(owned)
                self.process.returncode=0 if name.startswith('generator') else None
                self.process.poll.side_effect=lambda:self.process.returncode
                self.process.kill.side_effect=lambda:setattr(self.process,'returncode',-9)
                self.baseline_fd=0;self.tail=b'to=Healthy to=Healthy';self.closed=False
                owned.append(self)
            def ready(self,*args):pass
            def request_stop(self):pass
            def close(self):
                self.closed=True;self.process.returncode=0
                if self.name=='generator-1':signal.raise_signal(signal.SIGALRM)
                return {'name':self.name,'pid':self.process.pid,'returncode':0}
        class FakeMonitor:
            def __init__(self,*args):pass
            def check(self):pass
            def close(self):pass
        with tempfile.TemporaryDirectory() as folder:
            args=SimpleNamespace(output=folder,workers=2,backends=1,slots=128,capacity=32,reuse=False,nodelay=1,stream_mib=4,sample_interval=.1,fault='none',gateway='g',l4lb='l')
            spec=dict(id='unit',kind='formal',stage='low',variant='U',path='L',workload='A',rate=1,warm=0,duration=1)
            metrics={'corruption_all_phases':0}
            with patch.object(R,'Owned',FakeOwned),patch.object(R,'Monitor',FakeMonitor),patch.object(R,'ports',side_effect=lambda count:list(range(8000,8000+count))),patch.object(R,'proc',return_value={'fds':0}),patch.object(R,'audit',return_value=metrics),patch.object(R,'summarize',return_value={}):
                with self.assertRaises(RuntimeError):R.cell(spec,args)
            self.assertEqual(len(owned),6);self.assertTrue(all(x.closed for x in owned))
            ledger=json.loads((Path(folder)/'trace-ledger.json').read_text())
            self.assertEqual(ledger['cells'][0]['state'],'failed')

    def test_binary_stage_order_and_process_clock(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            header=[D.MAGIC,1,256,131071,1,0,1,0,0,0,0,0,0,10,1,30,31]+[0]*15
            (p/'header.bin').write_bytes(D.HEADER.pack(*header))
            def store(times):
                values=[1,1]+times+[0,0,0]*4+[0,0,0]+[1,0,0,1,1,0,0,0,256]+[b'']
                (p/'trace-0.bin').write_bytes(D.RECORD.pack(*values))
            valid=[10,12,13,14,15,16,17,20,21,18,0,0]
            store(valid);self.assertEqual(len(D.read_trace(p)[1]),1)
            for index,value in ((1,9),(3,12),(9,22),(8,19)):
                bad=valid.copy();bad[index]=value;store(bad)
                with self.assertRaises(ValueError):D.read_trace(p)

    def test_duplicate_endpoint_metadata_rejected(self):
        with patch.object(D,'read_trace',return_value=(None,[])),patch.object(D,'rows',return_value=iter([['id'],['id']])):
            with self.assertRaisesRegex(ValueError,'duplicate client endpoint'):D.correlate('fake')

    def test_wait_timeout_is_not_success(self):
        from unittest.mock import Mock
        import subprocess
        import TraceRuntime as R
        item=R.Owned.__new__(R.Owned);item.name='fake';item.process=Mock();item.thread=Mock()
        item.tail=b'';item.error=None;item.bytes=item.blocks=item.write_ns=item.read_ns=0
        item.trace_expected=False;item.activity_deadline=0;item.process.returncode=None
        item.process.poll.return_value=None;item.process.send_signal.side_effect=RuntimeError('notification')
        item.process.wait.side_effect=subprocess.TimeoutExpired('child',2);item.thread.is_alive.return_value=False
        result=item.close();self.assertIn('TimeoutExpired',result['cleanup_error']);item.process.kill.assert_called_once()

    def test_u_o_client_adapters_do_not_change_payload(self):
        import importlib.util
        module_spec=importlib.util.spec_from_file_location('trace_client',Path(__file__).with_name('Client.py'))
        Client=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(Client)
        from Common import request
        self.assertEqual(Client.request('id','A'),request('id','A'))
        self.assertEqual(Client.COLUMNS, D.COLUMNS)


if __name__=='__main__':unittest.main(verbosity=2)
