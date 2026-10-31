"""Real child exit-boundary checks; no sockets or performance traffic."""
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from TraceRuntime import Owned, close_all


CHILD = '''
import signal,time
stopping=False
def stop(signum,frame):
    global stopping
    stopping=True
signal.signal(signal.SIGTERM,stop)
print('READY',flush=True)
while not stopping:time.sleep(.001)
signal.signal(signal.SIGTERM,signal.SIG_DFL)
print('DEFAULT_HANDLER',flush=True)
time.sleep(.15)
'''


class Tests(unittest.TestCase):
    def check_child(self, notify_first):
        with tempfile.TemporaryDirectory() as folder:
            child=Owned([sys.executable,'-u','-c',CHILD], 'exit-boundary',Path(folder),65536)
            child.activity_deadline=time.monotonic()+5
            try:
                child.ready('READY',timeout=2)
                with patch.object(child.process,'send_signal',wraps=child.process.send_signal) as sent:
                    if notify_first:
                        child.request_stop()
                        child.ready('DEFAULT_HANDLER',timeout=2)
                    records,errors=close_all([child])
                    self.assertEqual(errors,[])
                    self.assertEqual(records[0]['returncode'],0)
                    self.assertFalse(records[0]['deadline_killed'])
                    sent.assert_called_once_with(signal.SIGTERM)
                self.assertFalse(child.thread.is_alive())
                self.assertIsNotNone(child.process.poll())
            finally:
                if child.process.poll() is None:child.process.kill()
                child.process.wait(timeout=2)
                child.thread.join(timeout=2)

    def test_batch_then_close_sends_once(self):
        self.check_child(False)

    def test_close_after_handler_restored_sends_no_second_term(self):
        self.check_child(True)


if __name__=='__main__':unittest.main(verbosity=2,failfast=True)
