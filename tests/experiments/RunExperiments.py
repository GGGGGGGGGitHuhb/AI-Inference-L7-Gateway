"""One immutable Approved run. Parent is the only managed evidence writer."""
import argparse
import http.client
import json
import os
from pathlib import Path
import platform
import re
import signal
import sys
import time

from Budget import RunBudget,OwnedProcess,save,append,write
from Client import HASHES
from Infrastructure import ROOT,Host,Reader,Sampler,assets,port,process_stats,sha,wait_for
from Plan import build_plan,configuration,request
from Statistics import summarize
from Analyze import analyze
from Association import associate


def get(port_number,path):
    connection=http.client.HTTPConnection('127.0.0.1',port_number,timeout=2)
    try:
        connection.request('GET',path);response=connection.getresponse();body=response.read()
        if response.status!=200:raise RuntimeError('read-only HTTP status')
        return body.decode()
    finally:connection.close()


def real_boundary(backends,output,label):
    rows=[]
    for backend in backends:
        log=backend['log'].read_text();starts=re.findall(r'slot update_slots:.*task\s+(\d+)\s+\| new prompt',log)
        ends=re.findall(r'slot\s+release:.*task\s+(\d+)\s+\| stop processing',log)
        timings=re.findall(r'slot print_timing:.*task\s+(\d+)\s+\|',log)
        # Read-only /metrics does not generate a new slot task; preserve text and recheck.
        metrics=get(backend['port'],'/metrics')
        later=re.findall(r'slot update_slots:.*task\s+(\d+)\s+\| new prompt',backend['log'].read_text())
        if starts!=later:raise RuntimeError('generation not drained at metrics boundary')
        row={'pid':backend['owned'].process.pid,'port':backend['port'],'started_tasks':starts,
             'released_tasks':ends,'timed_tasks':timings,'metrics':metrics,'log_bytes':len(log.encode()),'log_sha256':sha(backend['log'])}
        if len(starts)!=len(set(starts)) or set(starts)!=set(ends) or set(starts)!=set(timings):raise RuntimeError('generation completion counter mismatch')
        rows.append(row)
    save(output/('real-'+label+'.json'),rows)
    return rows


class Cell:
    def __init__(self,cell,args,root,asset_paths,budget):
        self.cell=cell;self.args=args;self.output=root/cell['id'];self.output.mkdir()
        self.asset_paths=asset_paths;self.budget=budget;self.backends=[];self.gateway=None;self.host=None
        self.rows={};self.started={};self.workers=[];self.baseline=None;self.phase_results={};self.phase_clocks={}
        self.deadline=time.monotonic()+(240 if cell['group']=='R' else 60)

    def start_backends(self):
        cell=self.cell;count=2 if cell['group'] in ('H','Q','R') else 1
        for index in range(count):
            number=port();log=self.output/f'backend-{index}.log';output=self.output/f'backend-{index}.json'
            if cell['group']=='R':
                server,model=self.asset_paths
                command=[server,'-m',model,'--host','127.0.0.1','--port',number,'--alias','gateway-qwen','--ctx-size',2048,
                         '--parallel',1,'--threads',2,'--threads-batch',2,'--n-gpu-layers',0,'--metrics']
                direct=[]
            else:
                group='H' if cell['group'] in ('H','Q') else 'B' if cell['group']=='B' else 'A'
                command=[sys.executable,ROOT/'tests/experiments/Backend.py','--port',number,'--group',group,'--output',output,
                         '--delay',(.02 if index==0 else .1) if group=='H' else 0,'--nodelay',int(cell['nodelay'])]
                direct=[output,str(output)+'.warmup']
            owned=OwnedProcess(command,log,self.output/'processes.jsonl',direct_paths=direct)
            backend={'port':number,'owned':owned,'log':log,'output':output};self.backends.append(backend)
            def ready():
                if owned.process.poll() is not None:raise RuntimeError('backend startup exit')
                stats=process_stats(owned.process.pid)
                if cell['group']=='R':
                    if stats['rss']>2*1024**3:raise RuntimeError('backend RSS guard')
                    try:return json.loads(get(number,'/health')).get('status')=='ok'
                    except (OSError,RuntimeError):return False
                return 'READY' in log.read_text()
            wait_for(ready,120 if cell['group']=='R' else 5,'backend startup')

    def start_gateway(self):
        cell=self.cell;ports=[b['port'] for b in self.backends];self.targets=ports
        if cell['path']=='D':return
        config=configuration(cell,ports)
        if cell['group'] in ('B','H','Q'):
            self.host=Host(self.args.host,config,self.output);self.targets=[self.host.port]
        else:
            config['listen_port']=port();save(self.output/'gateway-config.json',config)
            log=self.output/'gateway.log';self.gateway=OwnedProcess([self.args.gateway,'--config',self.output/'gateway-config.json'],log,self.output/'processes.jsonl')
            def ready():
                if self.gateway.process.poll() is not None:raise RuntimeError('gateway startup exit')
                return 'READY ' in log.read_text()
            wait_for(ready,5,'gateway ready');self.targets=[config['listen_port']];self.baseline=process_stats(self.gateway.process.pid)

    def drain(self,label,warmup=False):
        if self.host:return self.host.drain(label,warmup)
        if self.gateway:
            def clean():
                stats=process_stats(self.gateway.process.pid)
                return stats if stats and stats['fd']==self.baseline['fd'] else None
            stats=wait_for(clean,8,'official FD drain')
            if warmup:self.baseline['rss']=stats['rss']
            elif stats['rss']>self.baseline['rss']+32*1024**2:raise RuntimeError('official RSS drift')
            append(self.output/'drains.jsonl',{'label':label,'stats':stats,'baseline':self.baseline})
        return None

    def collect_worker(self,reader):
        for message in reader.take():
            if message['type']=='started':self.started[message['id']]=message['dispatch']
            elif message['type']=='attempt':
                row=message['row']
                if row['id'] in self.rows:raise RuntimeError('duplicate worker result')
                if len(self.rows)>=256:raise RuntimeError('cell attempt buffer')
                self.rows[row['id']]=row
            elif message['type']=='done':append(self.output/'client-resources.jsonl',message)
            else:raise RuntimeError('unexpected worker frame')

    def phase(self,phase):
        items=[i for i in self.cell['attempts'] if i['phase']==phase]
        workers=[];t0=time.monotonic_ns()+400000000;self.phase_clocks[phase]=t0
        try:
            for index in range(self.cell['processes']):
                subset=items[index::self.cell['processes']]
                owned=OwnedProcess([sys.executable,ROOT/'tests/experiments/Worker.py'],self.output/f'{phase}-client-{index}.log',self.output/'processes.jsonl',capture=True)
                reader=Reader(owned);workers.append((owned,reader));self.workers.append((owned,reader))
                packet={'cell':self.cell,'items':subset,'ports':self.targets,'t0':t0,
                        'concurrency':max(1,self.cell['concurrency']//self.cell['processes'])}
                data=json.dumps(packet).encode()+b'\n'
                if len(data)>2*1024**2:raise RuntimeError('worker command bound')
                owned.process.stdin.write(data);owned.process.stdin.close()
            while True:
                for owned,reader in workers:self.collect_worker(reader)
                if all(reader.done.is_set() for _,reader in workers):break
                if time.monotonic()>self.deadline:raise TimeoutError('cell deadline')
                if self.host and self.host.error:raise self.host.error
                self.budget.check();time.sleep(.001)
            for owned,reader in workers:
                self.collect_worker(reader);owned.process.wait(2)
                if owned.process.returncode:raise RuntimeError('late client process failure')
            rows=[self.rows[i['id']] for i in items]
            result=summarize(self.cell,items,rows,t0);result['t0']=t0
            self.phase_results[phase]=result
            save(self.output/(phase+'-summary.json'),result)
            return rows
        finally:
            for owned,reader in workers:
                owned.stop();reader.stop();self.collect_worker(reader)

    def finish_records(self,error):
        existing=set(self.rows)
        for item in self.cell['attempts']:
            if item['id'] not in self.rows:
                begun=self.started.get(item['id']);self.rows[item['id']]={**item,'outcome':'interrupted' if begun else 'not_started',
                    'dispatch':begun,'closed':time.monotonic_ns(),'error':repr(error)[:1024]}
                if self.cell['rate'] and item['phase'] in self.phase_clocks:
                    scheduled=self.phase_clocks[item['phase']]+int(item['index']/self.cell['rate']*1e9)
                    self.rows[item['id']]['scheduled']=scheduled
                    if not begun and scheduled<=time.monotonic_ns():
                        self.rows[item['id']].update(outcome='not_sent',reason='interrupted_before_dispatch')
            row=self.rows[item['id']]
            data=json.dumps(row,separators=(',',':')).encode()
            if len(data)>8192:raise RuntimeError('attempt summary bound')
            try:write(self.output/(item['id']+'.json'),data,'xb')
            except BaseException:
                write(self.output/(item['id']+'.json'),data,'xb',emergency=True)
        return existing

    def run(self):
        error=None;state=None
        try:
            self.start_backends();self.start_gateway()
            before=real_boundary(self.backends,self.output,'before') if self.cell['group']=='R' else None
            if before and any(row['started_tasks'] for row in before):raise RuntimeError('unexpected generation before preheat')
            self.phase('warmup');warm_state=self.drain('warmup',True)
            if before:
                warm=real_boundary(self.backends,self.output,'warmup')
                if [len(b['started_tasks'])-len(a['started_tasks']) for a,b in zip(before,warm)]!=[1,1]:raise RuntimeError('real warmup allocation')
            else:
                for backend in self.backends:
                    os.kill(backend['owned'].process.pid,signal.SIGUSR1)
                    wait_for(lambda:Path(str(backend['output'])+'.warmup').exists(),2,'backend checkpoint')
            rows=self.phase('formal');state=self.drain('formal')
            if before:
                final=real_boundary(self.backends,self.output,'formal')
                if [len(b['started_tasks'])-len(a['started_tasks']) for a,b in zip(warm,final)]!=[6,6]:raise RuntimeError('real formal allocation')
            if self.host:
                save(self.output/'host-final-records.json',list(self.host.records.values()))
                mapping,excluded=associate(list(self.rows.values()),list(self.host.records.values()),
                    cell_id=self.cell['id'],host_pid=self.host.owned.process.pid,target_port=self.host.port)
                queued=[];expired=[];targets={}
                for row in self.rows.values():
                    if row['id'] in excluded:continue
                    trace=mapping[row['id']];targets[row['id']]={'session_id':trace['id'],'backend':trace.get('backend')}
                    if trace['enqueued']:
                        if trace['dispatched']:
                            queued.append({'id':row['id'],'seconds':(trace['dispatched']-trace['enqueued'])/1e9,'outcome':row['outcome']})
                        elif row['outcome']=='http_timeout':
                            expired.append({'id':row['id'],'seconds':(trace['finished']-trace['enqueued'])/1e9,'code':row['error_code']})
                save(self.output/'queue-and-targets.json',{'dispatched_waits':queued,'expired_waits':expired,'targets':targets,'excluded_connections':excluded})
                if state['peak_reserved']>2147483648 or state['peak_capacity']>33554432:raise RuntimeError('gateway quota')
                if self.cell['group']=='B':
                    if state['pauses']<=warm_state['pauses'] or state['resumes']<=warm_state['resumes']:raise RuntimeError('B formal pause/resume missing')
                    for offset in range(0,self.cell['formal'],4):
                        wave=[r for r in rows if offset<=r['index']<offset+4];slow=next(r for r in wave if r['slow'])
                        if not any(r.get('http_complete',10**30)<slow['http_complete'] for r in wave if not r['slow']):raise RuntimeError('B fast progress missing')
                if self.cell['group']=='Q' and (state['peak_inflight']>2 or max(state['backend_peaks'])>1 or state['peak_queue_count']>self.cell['queue_count'] or state['peak_queue_bytes']>65536):raise RuntimeError('Q limit')
            if any(r['outcome'] in ('protocol_failure','transport_failure','client_deadline','interrupted','not_started') for r in self.rows.values()):raise RuntimeError('protocol/transport/deadline failure')
            return self.phase_results['formal']
        except BaseException as failure:error=failure;raise
        finally:
            failures=[]
            for owned,reader in self.workers:
                try:owned.stop();reader.stop();self.collect_worker(reader)
                except BaseException as failure:failures.append(repr(failure))
            for resource in [self.host,self.gateway]+[b['owned'] for b in self.backends]:
                if resource:
                    try:resource.stop()
                    except BaseException as failure:failures.append(repr(failure))
            self.finish_records(error)
            if error is None and self.cell['group']!='R':
                audits=[];observed=[]
                for backend in self.backends:
                    record=json.loads(backend['output'].read_text());warm=json.loads(Path(str(backend['output'])+'.warmup').read_text())
                    observed.extend(r['id'] for r in record['requests'])
                    audits.append({'port':backend['port'],'accepts':record['accepts'],'requests':len(record['requests']),
                      'warm_accepts':warm['accepts'],'warm_requests':warm['requests'],
                      'formal_accepts':record['accepts']-warm['accepts'],'formal_requests':len(record['requests'])-warm['requests']})
                expected=[r['id'] for r in self.rows.values() if r['outcome']=='success']
                if sorted(observed)!=sorted(expected):raise RuntimeError('backend arrival mismatch/retry')
                save(self.output/'backend-audit.json',audits)
                if self.cell['group'] in ('A','N','T'):
                    for audit in audits:
                        for phase in ['warm','formal']:
                            if self.cell['path']=='PR':
                                if not audit[phase+'_accepts']<audit[phase+'_requests']:raise RuntimeError('PR reuse not observed')
                            elif audit[phase+'_accepts']!=audit[phase+'_requests']:raise RuntimeError('cold connection reused')
            if failures:save(self.output/'cleanup-errors.json',failures);raise RuntimeError('cell cleanup failure')


def interrupt(signum,frame):raise InterruptedError('run interrupted')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--host',required=True);parser.add_argument('--gateway',required=True)
    parser.add_argument('--assets',default=str(ROOT/'build-local/integration/v0.2-s3'));parser.add_argument('--output',required=True)
    args=parser.parse_args();root=Path(args.output).resolve();root.mkdir(exist_ok=False,parents=True)
    plan=build_plan();completed=[];sampler=None;started=time.monotonic()
    with RunBudget(root) as budget:
        try:
            save(root/'plan.json',plan)
            sources=[p for p in (ROOT/'tests/experiments').iterdir() if p.is_file()]+list((ROOT/'src').rglob('*.cpp'))+list((ROOT/'src').rglob('*.h'))
            save(root/'manifest.json',{'arguments':vars(args),'platform':platform.platform(),'affinity':sorted(os.sched_getaffinity(0)),
                'cpu_count':os.cpu_count(),'payload_hashes':HASHES,'source_hashes':{str(p.relative_to(ROOT)):sha(p) for p in sources},
                'host_sha256':sha(args.host),'gateway_sha256':sha(args.gateway),'plan_sha256':sha(root/'plan.json'),
                'requests':{a['id']:sha_bytes(request(c,a)) for c in plan['cells'] for a in c['attempts']},
                'configuration_templates':{c['id']:configuration(c,[1,2] if c['group'] in ('H','Q','R') else [1]) for c in plan['cells']}})
            signal.signal(signal.SIGALRM,interrupt);signal.signal(signal.SIGTERM,interrupt);signal.alarm(3600)
            asset_paths=assets(args.assets,root);sampler=Sampler(budget,root)
            for cell in plan['cells']:
                print('START',cell['id'],flush=True)
                remaining=3600-(time.monotonic()-started)
                if remaining<=0:raise TimeoutError('whole-run deadline')
                signal.setitimer(signal.ITIMER_REAL,min(240 if cell['group']=='R' else 60,remaining))
                result=Cell(cell,args,root,asset_paths,budget).run()
                signal.setitimer(signal.ITIMER_REAL,max(.001,3600-(time.monotonic()-started)))
                completed.append({'cell':cell,**result})
                append(root/'completed-cells.jsonl',completed[-1]);print('DONE',cell['id'],result['counts'],flush=True)
            sampler.stop();sampler=None;budget.finish()
            analysis=analyze(root)
            save(root/'result.json',{'status':analysis['status'],'seconds':time.monotonic()-started,'cells':len(completed),'charged':budget.used})
        except BaseException as error:
            save(root/'result.json',{'status':'FAIL','error':repr(error),'cells':len(completed),'seconds':time.monotonic()-started,'charged':budget.used})
            raise
        finally:
            signal.alarm(0)
            if sampler:sampler.stop()
            # Every planned ID is closed, including cells never started. This is an
            # emergency bounded index, not invented successful request evidence.
            missing=[]
            for cell in plan['cells']:
                for item in cell['attempts']:
                    if not (root/cell['id']/(item['id']+'.json')).exists():missing.append({'id':item['id'],'outcome':'not_started'})
            if missing:write(root/'unstarted.json',json.dumps(missing).encode(),emergency=True)


def sha_bytes(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


if __name__=='__main__':main()
