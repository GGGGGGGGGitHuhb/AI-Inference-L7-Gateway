"""Short offline/loopback controls. Never launches models or the fixed matrix."""
import argparse
from contextlib import nullcontext
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

from Budget import RunBudget,OwnedProcess,write,save,BudgetExceeded
from Client import attempt,PAYLOADS
from Infrastructure import Host,Reader,assets,port
from Plan import build_plan,configuration,request
from Statistics import check_row,quantiles,summarize
from RunExperiments import Cell
from AssociationTests import check as association_checks


def rejected(action):
    try:action()
    except (AssertionError,ValueError,RuntimeError,FileNotFoundError,OSError):return
    raise AssertionError('negative accepted')


def unit_checks(root):
    plan=build_plan();assert len(plan['cells'])==57
    assert sum(len(c['attempts']) for c in plan['cells'])==7590
    assert [c['path'] for c in plan['cells'][2:5]]==['D','PC','PR']
    spec=importlib.util.spec_from_file_location('frozen_p1_client',Path(__file__).resolve().parents[1]/'performance/Client.py')
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    assert PAYLOADS['A']==old.PAYLOADS['A'] and PAYLOADS['B']==old.PAYLOADS['C']
    assert len(PAYLOADS['H'])==1024
    assert quantiles(list(range(100)))['p95']==94 and 'p99' not in quantiles(list(range(999)))
    assert 'p50' not in quantiles(list(range(19))) and quantiles([])['median'] is None
    rejected(lambda:check_row({'outcome':'success','status':200,'http_valid':False}))
    rejected(lambda:check_row({'outcome':'http_rejection','status':504}))
    rejected(lambda:check_row({'outcome':'http_timeout','status':503}))
    rejected(lambda:check_row({'outcome':'success','status':200,'http_valid':True,'dispatch':2,'connect':1}))
    rejected(lambda:check_row({'outcome':'not_sent','send':1}))
    cell=copy.deepcopy(plan['cells'][0]);cell['rate']=0
    item={'id':'one'};row={'id':'one','outcome':'success','status':200,'http_valid':True,'dispatch':1000000000,
                         'send':1000000000,'http_complete':1100000000,'closed':1100000001}
    assert summarize(cell,[item],[row],1000000000)['slo_met']==1
    row['http_complete']+=1;row['closed']+=1
    assert summarize(cell,[item],[row],1000000000)['slo_met']==0
    rejected(lambda:summarize(cell,[item],[],1000000000))
    rejected(lambda:summarize(cell,[item],[row,row],1000000000))
    rejected(lambda:assets(root/'missing',root))
    wrong=root/'wrong/backend/llama-b7481';wrong.mkdir(parents=True);(wrong/'llama-server').write_bytes(b'bad')
    rejected(lambda:assets(root/'wrong',root))
    from Worker import arrival_decision
    assert arrival_decision(0,0,128)=='no_slot'
    assert arrival_decision(50000001,0,0)=='dispatch_late'
    assert arrival_decision(50000000,0,127) is None
    state={key:0 for key in __import__('Infrastructure').ZERO};state['inflight']=1
    from Infrastructure import validate_empty,validate_state
    rejected(lambda:validate_empty(state))
    limits=configuration(next(c for c in plan['cells'] if c['group']=='Q'),[1,2])
    state.update(peak_reserved=limits['max_reserved_bytes']+1,peak_capacity=0)
    rejected(lambda:validate_state(state,limits))
    # Port conflict is a real bind failure, not an invented error string.
    with socket.socket() as bound:
        bound.bind(('127.0.0.1',0));bound.listen()
        from Backend import Server
        rejected(lambda:Server(bound.getsockname()[1],'A',0,False))
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen()
        def malformed():
            connection,_=listener.accept()
            with connection:
                connection.recv(8192);connection.sendall(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nx\r\nZ\r\n')
        thread=threading.Thread(target=malformed);thread.start()
        item={'id':'partial','index':0,'slow':False};cell['group']='B'
        result=attempt(listener.getsockname()[1],request(cell,item),item,'B');thread.join(2)
        assert result['outcome']=='protocol_failure' and not result['http_valid']
        save(root/'partial-200.json',result)
    late=attempt(1,b'',{'id':'late'},'A',time.monotonic_ns()-100000000)
    assert late['outcome']=='not_sent' and late.get('send') is None
    save(root/'late.json',late)


def storage_case(root):
    root.mkdir();child=None
    budget=RunBudget(root,direct=32768,managed=4096,emergency=16384,file_limit=8192)
    try:
        with budget:
            try:
                child=OwnedProcess([sys.executable,'-c','import time;time.sleep(10)'],root/'child.log',root/'processes.jsonl')
                write(root/'one',b'x'*3000);write(root/'two',b'y'*3000)
            finally:
                if child:child.stop()
    except BudgetExceeded as error:
        budget.write(root/'error.json',json.dumps({'error':str(error)}).encode(),emergency=True)
        assert child.process.poll() is not None
        assert sum(p.stat().st_size for p in root.iterdir())<=sum(budget.limits.values())
        return 2
    raise AssertionError('storage overrun accepted')


def short_host(root,host,group='Q'):
    plan=build_plan();cell=copy.deepcopy(next(c for c in plan['cells'] if c['group']==group and (c['queue_count']==8 if group=='Q' else c['path']=='P')))
    cell['attempts']=[{**a,'index':index} for phase in ['warmup','formal'] for index,a in enumerate([x for x in cell['attempts'] if x['phase']==phase][:4])]
    cell['formal']=4;cell['warmup']=4;cell['rate']=60 if group=='Q' else 0
    args=SimpleNamespace(host=host,gateway='',assets='')
    with RunBudget(root):
        # This is a short fixture, explicitly not one of the 57 formal cells.
        from Budget import ACTIVE
        result=Cell(cell,args,root,None,ACTIVE).run()
        assert sum(result['counts'].values())==4


def double_interruption(root,host):
    cell=copy.deepcopy(next(c for c in build_plan()['cells'] if c['group']=='H'))
    cell.update(processes=2,concurrency=4,rate=0)
    cell['attempts']=[a for a in cell['attempts'] if a['index']<4];cell['formal']=4;cell['warmup']=4
    root.mkdir();args=SimpleNamespace(host=host,gateway='')
    with RunBudget(root) as budget:
        fixture=Cell(cell,args,root,None,budget)
        def interrupt_clients():
            end=time.monotonic()+5
            while time.monotonic()<end:
                if len(fixture.workers)==2 and len(fixture.started)>=2:
                    for owned,_ in fixture.workers:
                        try:os.killpg(owned.process.pid,signal.SIGTERM)
                        except ProcessLookupError:pass
                    return
                time.sleep(.001)
            raise RuntimeError('interruption gate absent')
        thread=threading.Thread(target=interrupt_clients);thread.start()
        rejected(fixture.run);thread.join(6)
        assert not thread.is_alive()
        records=[json.loads((fixture.output/(a['id']+'.json')).read_text()) for a in cell['attempts']]
        assert len(records)==8 and any(r['outcome']=='interrupted' for r in records)
        assert all(owned.process.poll() is not None for owned,_ in fixture.workers)
        save(root/'closure.json',{'ids':[r['id'] for r in records],'outcomes':[r['outcome'] for r in records]})


def budget_negative(root,case):
    root.mkdir();budget=RunBudget(root,direct=16384,managed=4096,emergency=32768,file_limit=4096);children=[];threads=[]
    try:
        with budget:
            try:
                if case=='multi_paths':
                    for i in range(2):
                        paths=[root/f'{i}-{j}.raw' for j in range(2)]
                        code='from pathlib import Path;import time;'+ ';'.join(f'Path({str(p)!r}).write_bytes(b"x"*100)' for p in paths)+';time.sleep(20)'
                        children.append(OwnedProcess([sys.executable,'-c',code],root/f'{i}.log',root/'processes.jsonl',direct_paths=paths))
                        time.sleep(.02)
                elif case=='direct_hard':
                    path=root/'raw';code=f'from pathlib import Path;Path({str(path)!r}).write_bytes(b"x"*10000)'
                    children.append(OwnedProcess([sys.executable,'-c',code],root/'child.log',root/'processes.jsonl',direct_paths=[path]))
                    while True:time.sleep(.01)
                elif case=='concurrent':
                    barrier=threading.Barrier(4)
                    def writer(i):
                        barrier.wait()
                        try:write(root/f'writer-{i}',b'x'*1500)
                        except BudgetExceeded:pass
                    threads=[threading.Thread(target=writer,args=(i,)) for i in range(3)]
                    for thread in threads:thread.start()
                    barrier.wait()
                    for thread in threads:thread.join()
                elif case=='replacement':
                    for i in range(3):write(root/'state.partial',b'x'*2000);os.replace(root/'state.partial',root/'state')
                budget.check()
            finally:
                for thread in threads:thread.join(2)
                for child in children:child.stop()
    except BudgetExceeded as error:
        budget.write(root/'error.json',json.dumps({'error':str(error),'children':[c.process.pid for c in children]}).encode(),emergency=True)
        assert all(c.process.poll() is not None for c in children)
        assert sum(p.stat().st_size for p in root.iterdir())<=sum(budget.limits.values())
        return 2
    raise AssertionError('negative did not fail')


def late_future(root):
    import Worker
    def fail_later(*args):time.sleep(.01);raise RuntimeError('late future failure')
    Worker.one=fail_later
    cell=build_plan()['cells'][0]
    rejected(lambda:Worker.run_batch(cell,cell['attempts'][:2],[1],time.monotonic_ns(),2))
    save(root/'future-error.json',{'observed':'future.result propagated exception'})


def main():
    if '--storage' in sys.argv:return storage_case(Path(sys.argv[2]))
    if '--negative' in sys.argv:return budget_negative(Path(sys.argv[3]),sys.argv[2])
    host=sys.argv[1]
    destination=Path(sys.argv[sys.argv.index('--output')+1]) if '--output' in sys.argv else None
    if destination:destination.mkdir(exist_ok=False)
    with (nullcontext(destination) if destination else tempfile.TemporaryDirectory(prefix='experiment-detectors-')) as name:
        root=Path(name);unit_checks(root);late_future(root);association_checks(root)
        result=subprocess.run([sys.executable,__file__,'--storage',str(root/'budget')],capture_output=True,text=True,timeout=10)
        assert result.returncode==2,result.stderr
        for case in ['multi_paths','direct_hard','concurrent','replacement']:
            result=subprocess.run([sys.executable,__file__,'--negative',case,str(root/case)],capture_output=True,text=True,timeout=10)
            (root/(case+'.log')).write_text(result.stdout+result.stderr)
            assert result.returncode==2,(case,result.stderr)
        short=root/'short';short.mkdir();short_host(short,host)
        backpressure=root/'backpressure';backpressure.mkdir();short_host(backpressure,host,'B')
        double_interruption(root/'double-interrupted',host)
    print('ExperimentDetectors: plan/payload, clocks/classes/SLO/quantiles, HTTP/arrival, five real budget negatives, host, dual-client interruption and late future passed')
    return 0


if __name__=='__main__':sys.exit(main())
