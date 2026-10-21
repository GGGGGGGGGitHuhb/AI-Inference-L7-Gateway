"""Parent-owned bounded IPC, resources, assets and gateway process fixtures."""
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import socket
import sys
import tarfile
import threading
import time

from Budget import OwnedProcess,append,save,BudgetExceeded
ROOT=Path(__file__).resolve().parents[2]
ZERO=('sessions','reserved','capacity','pending','paused','timers','upstreams','leased','idle','pool_total','inflight','queue_count','queue_bytes')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def wait_for(predicate,timeout,label):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        value=predicate()
        if value:return value
        time.sleep(.005)
    raise RuntimeError('gate deadline: '+label)


def process_stats(pid):
    root=Path('/proc')/str(pid)
    try:
        stat=(root/'stat').read_text().split();status=(root/'status').read_text().splitlines()
        switches={line.split(':')[0]:int(line.split(':')[1]) for line in status if 'ctxt_switches:' in line}
        return {'pid':pid,'cpu_seconds':(int(stat[13])+int(stat[14]))/os.sysconf('SC_CLK_TCK'),
          'rss':int((root/'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE'),
          'fd':len(list((root/'fd').iterdir())),'threads':int(stat[19]),**switches}
    except (FileNotFoundError,ProcessLookupError):return None


def validate_state(state,config):
    if state['peak_reserved']>config['max_reserved_bytes'] or state['peak_capacity']>config['stream_buffer']['max_total_bytes']:
        raise RuntimeError('resource quota exceeded')
    if state['pending']>state['capacity']:raise RuntimeError('pending exceeds capacity')
    if 'admission' in config:
        admission=config['admission']
        if (state['peak_inflight']>admission['max_inflight'] or
            max(state['backend_peaks'],default=0)>admission['max_inflight_per_backend'] or
            state['peak_queue_count']>admission['max_queue_requests_per_model'] or
            state['peak_queue_bytes']>admission['max_queue_bytes_per_model']):raise RuntimeError('admission quota exceeded')


def validate_empty(state):
    if any(state[key]!=0 for key in ZERO):raise RuntimeError('resource residual')


class Reader:
    def __init__(self,owned):
        self.owned=owned;self.queue=queue.Queue(256);self.error=None;self.done=threading.Event()
        self.thread=threading.Thread(target=self.read,daemon=True);self.thread.start()

    def read(self):
        try:
            while True:
                line=self.owned.process.stdout.readline(8193)
                if not line:break
                if len(line)>8192 or not line.endswith(b'\n'):raise RuntimeError('IPC frame bound')
                self.queue.put(json.loads(line),timeout=2)
        except BaseException as error:self.error=error
        finally:self.done.set()

    def take(self):
        if self.error:raise self.error
        rows=[]
        while True:
            try:rows.append(self.queue.get_nowait())
            except queue.Empty:break
        return rows

    def stop(self):
        self.thread.join(2)
        if self.thread.is_alive():raise RuntimeError('IPC reader did not exit')
        if self.error:raise self.error


class Host:
    def __init__(self,executable,config,output):
        self.output=Path(output);self.config=config;self.state=None;self.records={};self.port=None;self.error=None
        self.samples=[];self.events=[];self.stop_event=threading.Event()
        save(self.output/'gateway-config.json',config)
        self.owned=OwnedProcess([executable,self.output/'gateway-config.json'],self.output/'host.log',self.output/'processes.jsonl',capture=True)
        self.reader=Reader(self.owned);self.thread=threading.Thread(target=self.observe,daemon=True);self.thread.start()
        try:
            wait_for(self.ready,5,'host ready');self.baseline=process_stats(self.owned.process.pid)
        except BaseException:self.stop();raise

    def ready(self):
        if self.error:raise self.error
        if self.owned.process.poll() is not None:raise RuntimeError('host exited before ready')
        return self.port and self.state

    def observe(self):
        try:
            while not self.stop_event.is_set() or not self.reader.done.is_set():
                rows=self.reader.take()
                for row in rows:
                    if row['type']=='ready':self.port=row['port']
                    elif row['type']=='state':
                        if len(json.dumps(row).encode())>4096:raise RuntimeError('state size bound')
                        validate_state(row,self.config)
                        self.state=row;append(self.output/'states.jsonl',row)
                    elif row['type']=='transition':
                        if len(json.dumps(row).encode())>1024:raise RuntimeError('event size bound')
                        self.records[row['id']]=row;self.events.append(row)
                        if len(self.events)>=256:self.flush_events()
                    else:raise RuntimeError('unknown host message')
                if self.reader.done.is_set() and not rows:break
                time.sleep(.002)
            self.flush_events()
        except BaseException as error:self.error=error

    def flush_events(self):
        if self.events:
            from Budget import write
            data=''.join(json.dumps(r,separators=(',',':'))+'\n' for r in self.events).encode()
            write(self.output/'transitions.jsonl',data,'ab');self.events.clear()

    def drain(self,label,warmup=False):
        beginning=time.monotonic_ns()
        def clean():
            if self.error:raise self.error
            s=self.state
            return s if s and s['time']>=beginning and all(s[k]==0 for k in ZERO) else None
        state=wait_for(clean,8,'drain '+label);stats=process_stats(self.owned.process.pid)
        if stats['fd']!=self.baseline['fd']:raise RuntimeError('FD drift')
        if warmup:self.baseline['rss']=stats['rss']
        elif stats['rss']>self.baseline['rss']+32*1024**2:raise RuntimeError('RSS drift')
        append(self.output/'drains.jsonl',{'label':label,'state':state,'stats':stats,'baseline':self.baseline})
        return state

    def stop(self):
        errors=[]
        try:self.owned.stop()
        except BaseException as error:errors.append(error)
        self.stop_event.set();self.thread.join(3)
        try:self.reader.stop()
        except BaseException as error:errors.append(error)
        if self.thread.is_alive():errors.append(RuntimeError('host observer alive'))
        if self.error:errors.append(self.error)
        if self.owned.process.returncode!=0:errors.append(RuntimeError('host exit failure'))
        if errors:raise errors[0]


class Sampler:
    def __init__(self,budget,output):
        self.budget=budget;self.output=Path(output);self.done=threading.Event();self.error=None
        self.thread=threading.Thread(target=self.sample,daemon=True);self.thread.start()

    def sample(self):
        try:
            while not self.done.is_set():
                children=list(self.budget.children)
                live=[p for p in children if p.poll() is None]
                rows=[process_stats(p.pid) for p in live]
                for child,row in zip(live,rows):
                    if row and any('llama-server' in str(arg) for arg in child.args) and row['rss']>2*1024**3:raise RuntimeError('backend RSS bound')
                rows.append(process_stats(os.getpid()))
                for row in rows:
                    if row and row['threads']>256:raise RuntimeError('thread bound')
                append(self.output/'resources.jsonl',{'time':time.monotonic_ns(),'load':os.getloadavg(),'processes':rows})
                self.done.wait(1)
        except BaseException as error:
            self.error=error
            try:self.budget.fail('resource sampler: '+repr(error))
            except BudgetExceeded:pass

    def stop(self):
        self.done.set();self.thread.join(2)
        if self.error:raise self.error


def assets(root,output):
    root=Path(root);server=root/'backend/llama-b7481/llama-server';model=root/'models/qwen2.5-0.5b-instruct-q4_k_m.gguf';archive=root/'downloads/llama-b7481-bin-ubuntu-x64.tar.gz'
    expected={server:'45938e6847d403ff6486cd692de9441aeb330e971a5dd8ad6f695b60bae2d081',model:'74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db',archive:'9cbbff430e4f2d976135d68d998576530cc1bd87babe1d71db4886d8a79e7b2e'}
    for path,digest in expected.items():
        if sha(path)!=digest:raise RuntimeError('asset identity: '+str(path))
    members={}
    with tarfile.open(archive,'r:gz') as source:
        for member in source:
            if member.isfile() and ('.so' in member.name or 'LICENSE' in member.name or member.name.endswith('/llama-server')):
                digest=hashlib.sha256(source.extractfile(member).read()).hexdigest();path=server.parent/Path(member.name).name
                if sha(path)!=digest:raise RuntimeError('library/license identity')
                members[str(path)]=digest
    license_path=root/'models/LICENSE'
    if 'Apache License' not in license_path.read_text():raise RuntimeError('model license')
    save(Path(output)/'assets.json',{'assets':{str(p):v for p,v in expected.items()},'members':members,'model_license':sha(license_path)})
    return server.resolve(),model.resolve()
