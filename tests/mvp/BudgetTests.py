"""Small storage guards using real children, concurrent writes and failure records."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from Budget import RunBudget, BudgetExceeded, OwnedProcess, save, write, save_attempt


def run_case(root, case, host):
    root.mkdir()
    children = []
    threads = []
    attempt = None
    listener = None
    started = time.monotonic()
    budget = RunBudget(root, direct=65536, managed=8192, emergency=65536, file_limit=8192)
    row = dict(id='started-attempt', group='budget', expected='success', started=started,
               ended=started, body='observed content', bytes=16, error=None, outcome='success')
    try:
        with budget:
            try:
                save(root/'manifest.json', {'case': case})
                save_attempt(root/'started-attempt.json', row)
                if case == 'aggregate':
                    child = OwnedProcess([sys.executable, '-c', 'import time; time.sleep(30)'], root/'child.log', root/'processes.jsonl')
                    children.append(child)
                    write(root/'one.log', b'x'*4000)
                    write(root/'two.log', b'x'*4000)
                elif case == 'concurrent':
                    barrier = threading.Barrier(5)
                    def writer(index):
                        barrier.wait()
                        try:
                            write(root/f'thread-{index}.log', b'x'*2100)
                        except BudgetExceeded:
                            pass
                    threads = [threading.Thread(target=writer,args=(i,)) for i in range(4)]
                    for thread in threads: thread.start()
                    barrier.wait()
                    for thread in threads: thread.join()
                elif case == 'replacement':
                    for i in range(5):
                        write(root/'state.partial', b'x'*2100)
                        os.replace(root/'state.partial', root/'state.json')
                elif case == 'direct':
                    files = [root/'a.raw', root/'b.raw']
                    program = 'from pathlib import Path; import time; '+ '; '.join(f'Path({str(p)!r}).write_bytes(b"x"*9000)' for p in files) + '; time.sleep(30)'
                    children.append(OwnedProcess([sys.executable,'-c',program],root/'child.log',root/'processes.jsonl',direct_paths=files))
                    while True: time.sleep(.01)
                elif case == 'direct_aggregate':
                    # Three direct files plus stdout fit each hard limit; reservations must
                    # refuse a third producer before its multiple files can be created.
                    for index in range(3):
                        files=[root/f'{index}-{j}.raw' for j in range(3)]
                        program='from pathlib import Path; import time; '+ '; '.join(f'Path({str(p)!r}).write_bytes(b"x"*1000)' for p in files)+'; time.sleep(30)'
                        children.append(OwnedProcess([sys.executable,'-c',program],root/f'{index}.log',root/'processes.jsonl',direct_paths=files))
                        time.sleep(.03)
                elif case == 'attempt_fallback':
                    row['body'] = 'z'*10000
                    save_attempt(root/'large-attempt.json', row)
                elif case == 'actual_attempt':
                    import socket
                    from Attempts import Attempt
                    from Common import body
                    listener = socket.socket(); listener.bind(('127.0.0.1',0)); listener.listen()
                    def respond():
                        connection, _ = listener.accept()
                        with connection:
                            connection.recv(8192)
                            payload=json.dumps({'choices':[{'message':{'content':'y'*10000}}]}).encode()
                            connection.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(payload)).encode()+b'\r\nConnection: close\r\n\r\n'+payload)
                    thread=threading.Thread(target=respond); threads.append(thread); thread.start()
                    attempt=Attempt('actual-attempt','budget',listener.getsockname()[1],body('a',stream=False),root,timeout=2)
                    attempt.join()
                elif case == 'normal':
                    from Common import Host, configuration
                    child = Host(host, configuration([9001,9002,9003]),root,'normal')
                    try: child.drain('normal')
                    finally: child.stop()
                    write(root/'one.log',b'a'*100)
                budget.check()
            finally:
                if attempt: attempt.stop()
                if listener: listener.close()
                for thread in threads: thread.join(2)
                for child in children: child.stop()
            save(root/'result.json', {'status':'PASS'})
    except BudgetExceeded as error:
        # Context has ended; still charge reserved error evidence with the same ledger.
        budget.write(root/'result.json', json.dumps({'status':'FAIL','error':str(error)}).encode(), emergency=True)
    size=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    assert size <= sum(budget.limits.values()), size
    result=json.loads((root/'result.json').read_text())
    assert result['status']==('PASS' if case=='normal' else 'FAIL'),result
    assert (root/'started-attempt.json').exists()
    assert all(c.process.poll() is not None for c in children)
    assert time.monotonic()-started < 10
    if case=='actual_attempt':
        record=json.loads((root/'actual-attempt.json').read_text())
        assert record['evidence_truncated'] and record['outcome']=='failure' and record['body_sha256']
    if case=='attempt_fallback':
        assert json.loads((root/'large-attempt.json').read_text())['evidence_truncated']
    return {'case':case,'bytes':size,'limits':budget.limits,'charged':budget.used,'seconds':time.monotonic()-started,'result':result,'pids':[c.process.pid for c in children]}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--host',required=True);parser.add_argument('--case')
    args=parser.parse_args();root=Path(args.output)
    if args.case:
        result=run_case(root,args.case,args.host)
        root.with_suffix('.audit.json').write_text(json.dumps(result,indent=2))
        return 0 if result['result']['status']=='PASS' else 2
    root.mkdir(exist_ok=False)
    rows=[]
    for case in ['aggregate','concurrent','replacement','direct','direct_aggregate','attempt_fallback','actual_attempt','normal']:
        child=subprocess.run([sys.executable,__file__,'--case',case,'--output',str(root/case),'--host',args.host],capture_output=True,text=True,timeout=15)
        (root/(case+'.log')).write_text(child.stdout+child.stderr)
        assert child.returncode==(0 if case=='normal' else 2),(case,child.returncode,child.stderr)
        row=json.loads((root/case).with_suffix('.audit.json').read_text());row['exit']=child.returncode;rows.append(row)
    (root/'audit.json').write_text(json.dumps(rows,indent=2))
    print('BudgetTests: 7 nonzero bounded failures + normal host passed')
    return 0


if __name__=='__main__': sys.exit(main())
