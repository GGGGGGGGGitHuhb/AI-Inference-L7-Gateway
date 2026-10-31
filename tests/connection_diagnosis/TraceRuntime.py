"""Separate trace-round ceilings and owned exporters; frozen runtime remains unchanged."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'capacity'))
from Common import MIB, now, write
from Runtime import Owned as BaseOwned, Monitor

LIMIT=4096*MIB
CLOSURE=128*MIB


def used(root):
    return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file())


class Ledger:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(exist_ok=True,parents=True)
        self.path=self.root/'trace-ledger.json'
        self.data=json.loads(self.path.read_text()) if self.path.exists() else {'cells':[],'active_seconds':0}

    def save(self):
        temporary=self.path.with_suffix('.next')
        temporary.write_text(json.dumps(self.data,indent=2)+'\n');temporary.replace(self.path)

    def reserve(self,spec):
        if any(c['state'] in ('running','failed') for c in self.data['cells']):
            raise RuntimeError('previous cell is incomplete or failed; no resume')
        if any(c['id']==spec['id'] for c in self.data['cells']) or (self.root/spec['id']).exists():
            raise RuntimeError('unique trace cell required')
        limit=16*MIB if spec['stage']=='negative' else 256*MIB
        if len(self.data['cells'])>=18 or self.data['active_seconds']+60>1200:
            raise RuntimeError('trace cell/activity budget')
        if used(self.root.parent)+limit+CLOSURE>LIMIT:
            raise RuntimeError('trace evidence reservation')
        entry=dict(id=spec['id'],spec=spec,state='running',reserved=limit,start_ns=now())
        self.data['cells'].append(entry);self.data['active_seconds']+=60;self.save();return entry

    def close(self,entry,elapsed,state):
        entry.update(state=state,elapsed_seconds=elapsed)
        self.data['active_seconds']-=max(0,60-elapsed);self.save()


class Owned(BaseOwned):
    variant='U'
    activity_deadline=0

    def __init__(self,command,name,root,limit):
        self._stop_requested=False
        self.trace_expected=self.variant=='T' and (name.startswith('gateway-') or name=='l4lb')
        if self.trace_expected:
            directory=Path(root)/name;directory.mkdir()
            command=['env',f'CONNECTION_TRACE_DIR={directory}',*command]
        else:
            command=['env','-u','CONNECTION_TRACE_DIR',*command]
        super().__init__(command,name,root,limit)

    def request_stop(self):
        # 同一控制线程中，批量通知和单项回收共享一次停止请求。
        # 先标记再发信号；通知失败保留错误，由原截止/kill/reap兜底，不重发TERM。
        if getattr(self,'_stop_requested',False):return
        self._stop_requested=True
        if self.process.poll() is None:
            try:self.process.send_signal(signal.SIGTERM)
            except ProcessLookupError:pass

    def close(self):
        started=time.monotonic();export_start=None;failure=None;killed=False
        deadline=min(self.activity_deadline or started+12,started+12)
        try:
            self.request_stop()
            while self.process.poll() is None:
                match=re.search(rb'TRACE_EXPORT_BEGIN ([0-9]+)',self.tail)
                if match:
                    export_start=int(match[1]);deadline=min(deadline,export_start/1e9+10)
                if time.monotonic()>=deadline:
                    failure='owned cleanup deadline';break
                time.sleep(.002)
        except BaseException as error:
            failure=repr(error)
        finally:
            # 单项通知/等待/异常不能跳过该child的kill与wait。
            try:
                if self.process.poll() is None:
                    try:self.process.kill();killed=True
                    except ProcessLookupError:pass
                self.process.wait(timeout=2)
            except BaseException as error:
                failure=(failure or '')+'; reap '+repr(error)
            try:self.thread.join(timeout=2)
            except BaseException as error:failure=(failure or '')+'; capture join '+repr(error)
        if self.thread.is_alive() or self.error:
            failure=(failure or '')+'; capture '+str(self.error)
        return {'name':self.name,'pid':self.process.pid,'returncode':self.process.returncode,
                'capture_bytes':self.bytes,'capture_blocks':self.blocks,'capture_write_ns':self.write_ns,
                'capture_read_wait_ns':self.read_ns,'capture_loss_bytes':0,'export_begin_ns':export_start,
                'export_expected':self.trace_expected,'deadline_killed':killed,'cleanup_seconds':time.monotonic()-started,
                'cleanup_error':failure}


def close_all(owned):
    records=[];errors=[]
    for item in reversed(owned):
        try:
            item.request_stop()
        except ProcessLookupError:pass
        except BaseException as error:errors.append('notify '+item.name+':'+repr(error))
    for item in reversed(owned):
        try:
            record=item.close();records.append(record)
            if record['returncode']!=0 or record.get('cleanup_error'):
                errors.append('close '+item.name+':'+str(record.get('cleanup_error') or record['returncode']))
        except BaseException as error:
            errors.append('close exception '+item.name+':'+repr(error))
            # 最后防线，仍逐个回收后再处理下一个child。
            try:
                if item.process.poll() is None:item.process.kill()
                item.process.wait(timeout=2)
                item.thread.join(timeout=2)
            except BaseException as reap_error:errors.append('fallback reap '+item.name+':'+repr(reap_error))
            records.append({'name':item.name,'pid':item.process.pid,'returncode':item.process.poll(),
                            'cleanup_error':repr(error)})
    return records,errors


def preserve_early_failure(function):
    def wrapped(spec,args):
        started=time.monotonic()
        try:return function(spec,args)
        except BaseException as error:
            ledger=Ledger(args.output)
            pending=[e for e in ledger.data['cells'] if e['id']==spec['id'] and e['state']=='running']
            if pending:
                entry=pending[0]
                entry['early_failure']=repr(error)
                ledger.close(entry,time.monotonic()-started,'failed')
                root=Path(args.output)/spec['id'];root.mkdir(exist_ok=True)
                write(root/'early-failure.json',{'error':repr(error)},limit=32768)
            raise
    return wrapped
