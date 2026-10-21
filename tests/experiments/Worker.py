"""Bounded client process; no output files, only <=8KiB framed parent IPC."""
import concurrent.futures
import json
import resource
import os
import sys
import threading
import time
from Client import attempt
from Plan import request

IPC_LOCK=threading.Lock()


def emit(value):
    line=json.dumps(value,separators=(',',':'))+'\n'
    if len(line.encode())>8192:raise RuntimeError('worker IPC bound')
    with IPC_LOCK:sys.stdout.write(line);sys.stdout.flush()


def started(identity,clock):emit({'type':'started','id':identity,'dispatch':clock})


def one(cell,item,ports,payload,scheduled):
    row=attempt(ports[item['index']%len(ports)],payload,item,cell['group'],scheduled,started)
    emit({'type':'attempt','row':row})
    return row


def arrival_decision(now,scheduled,active):
    if now-scheduled>50000000:return 'dispatch_late'
    if active>=128:return 'no_slot'
    return None


def run_batch(cell,items,ports,t0,concurrency):
    payloads={item['id']:request(cell,item) for item in items}
    delay=(t0-time.monotonic_ns())/1e9
    if delay>0:time.sleep(delay)
    usage_start=resource.getrusage(resource.RUSAGE_SELF)
    futures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=128 if cell['rate'] else concurrency) as pool:
        if cell['rate']:
            for item in items:
                scheduled=t0+int(item['index']/cell['rate']*1e9)
                delay=(scheduled-time.monotonic_ns())/1e9
                if delay>0:time.sleep(delay)
                now=time.monotonic_ns()
                active=sum(not f.done() for f in futures)
                reason=arrival_decision(now,scheduled,active)
                if reason:
                    emit({'type':'attempt','row':{**item,'scheduled':scheduled,'checked':now,'closed':now,
                          'outcome':'not_sent','reason':reason}})
                    continue
                futures.append(pool.submit(one,cell,item,ports,payloads[item['id']],scheduled))
        elif cell['group']=='B':
            delay=(t0-time.monotonic_ns())/1e9
            if delay>0:time.sleep(delay)
            for offset in range(0,len(items),4):
                for item in items[offset:offset+4]:futures.append(pool.submit(one,cell,item,ports,payloads[item['id']],None))
                for f in futures:f.result()
        else:
            delay=(t0-time.monotonic_ns())/1e9
            if delay>0:time.sleep(delay)
            pending=set();iterator=iter(items)
            for item in iterator:
                if len(pending)>=concurrency:
                    done,pending=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
                    for f in done:f.result()
                future=pool.submit(one,cell,item,ports,payloads[item['id']],None);pending.add(future);futures.append(future)
        for f in futures:f.result()
    usage=resource.getrusage(resource.RUSAGE_SELF)
    emit({'type':'done','time':time.monotonic_ns(),'pid':os.getpid(),
          'cpu_seconds':usage.ru_utime+usage.ru_stime-usage_start.ru_utime-usage_start.ru_stime,'rss_kib':usage.ru_maxrss,
          'voluntary_switches':usage.ru_nvcsw,'involuntary_switches':usage.ru_nivcsw})


def main():
    line=sys.stdin.buffer.readline(2*1024**2+1)
    if len(line)>2*1024**2:raise RuntimeError('input IPC limit')
    data=json.loads(line)
    run_batch(data['cell'],data['items'],data['ports'],data['t0'],data['concurrency'])


if __name__=='__main__':main()
