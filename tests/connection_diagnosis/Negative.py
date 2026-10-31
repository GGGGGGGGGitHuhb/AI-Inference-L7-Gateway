"""Exactly three bounded functional cells; never a performance sample."""
import json
from pathlib import Path
import signal
import socket
import sys
import time
from types import SimpleNamespace
from RunCell import ports, gateway_config, HERE
from TraceRuntime import preserve_early_failure, Ledger, Owned, Monitor, close_all
from Decode import read_trace, LifecycleIndex
from Common import write, now, request, rows, MIB

KINDS=('connection-limit','reservation','peer-reset')


@preserve_early_failure
def cell(spec,args):
    if spec['negative'] not in KINDS:raise ValueError('unapproved negative')
    ledger=Ledger(args.output);entry=ledger.reserve(spec)
    root=Path(args.output)/spec['id'];root.mkdir();write(root/'spec.json',spec)
    started=time.monotonic();Owned.variant='T';Owned.activity_deadline=started+60
    owned=[];sockets=[];clients=[];error=None;result=None
    monitor=Monitor(owned,root,.1);monitor.activity_deadline_ns=int((started+60)*1e9)
    old_alarm=signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('negative60s')))
    signal.setitimer(signal.ITIMER_REAL,60)
    def spawn(command,name):
        child=Owned(command,name,root,65536);owned.append(child);child.ready('TCP 服务已启动' if name=='l4lb' else 'READY');return child
    def connect(port,identity,partial=False):
        stamp=now();sock=socket.create_connection(('127.0.0.1',port),timeout=2);sockets.append(sock)
        row=dict(id=identity,start=stamp,connect=now(),local=sock.getsockname(),peer=sock.getpeername())
        clients.append(row);sock.sendall(b'POST /v1/chat/completions HTTP/1.1\r\n' if partial else request(identity,'A'))
        return sock,row
    try:
        port,backend=ports(2)
        if spec['negative']=='peer-reset':
            spawn([sys.executable,str(HERE/'ResetBackend.py'),'--port',str(backend),'--output',str(root)],'reset-peer')
            config=root/'l4lb.conf';config.write_text(f'protocol=tcp\nlisten=127.0.0.1:{port}\nbackend=127.0.0.1:{backend}\nscheduler=round_robin\nhealth_check=tcp_connect\nmetrics=off\n')
            lb=spawn([args.l4lb,'--run',str(config)],'l4lb')
            until=time.monotonic()+10
            while b'to=Healthy' not in lb.tail:
                if time.monotonic()>=until:raise TimeoutError('negative health readiness')
                monitor.check();time.sleep(.02)
        else:
            config=gateway_config(port,[backend],1 if spec['negative']=='connection-limit' else 2,False)
            config['max_reserved_bytes']=16*MIB
            write(root/'gateway.json',config)
            spawn([args.gateway,'--config',str(root/'gateway.json')],'gateway-0')
            connect(port,spec['id']+'-held',True)
            # First SYN and partial header precede second connect; actual classification must still prove ordering.
            time.sleep(.05)
        sock,row=connect(port,spec['id']+'-probe')
        try:
            data=sock.recv(4096);row['received_bytes']=len(data)
            if data:raise ValueError('negative unexpectedly returned response')
        except ConnectionResetError:row['reset']=True
        row['closed']=now();sock.close();monitor.check()
    except BaseException as failure:error=repr(failure)
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signals=[]
        previous={sig:signal.signal(sig,lambda signum,frame:signals.append(signum)) for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGALRM)}
        for sock in sockets:
            try:sock.close()
            except OSError:pass
        for row in clients:row.setdefault('closed',now())
        monitor.windows=(int(started*1e9),now())
        monitor.phase='cleanup'
        try:
            processes,errors=close_all(owned)
            if errors:error=(error or '')+repr(errors)
            write(root/'processes.json',processes);write(root/'negative-clients.json',clients)
            if not error:
                name='l4lb' if spec['negative']=='peer-reset' else 'gateway-0'
                header,records=read_trace(root/name)
                if header[13]!=next(x['pid'] for x in processes if x['name']==name):raise ValueError('negative trace PID')
                idx=LifecycleIndex(records,reverse=True,kind=2 if name=='l4lb' else 1)
                probe=clients[-1];matched,status=idx.match(probe['local'],probe['peer'],probe['start'],probe['closed'])
                if status!='unique':raise ValueError('negative unique tuple match '+status)
                if name=='gateway-0':
                    expected=2 if spec['negative']=='connection-limit' else 3
                    if matched['outcome']!=expected:raise ValueError('negative rejection branch')
                    held,held_status=idx.match(clients[0]['local'],clients[0]['peer'],clients[0]['start'],clients[0]['closed'])
                    if held_status!='unique' or held['outcome']!=1:raise ValueError('negative held connection not published')
                else:
                    peers=list(rows(root,'reset-peer'))
                    if len(peers)!=1 or peers[0][0]!=probe['id']:raise ValueError('reset peer ID conservation')
                    if peers[0][2:] != [matched['endpoints'][3],matched['endpoints'][2],'reset']:raise ValueError('reset outbound tuple mismatch')
                    if matched['first_side']!=2 or matched['error']!=104:raise ValueError('reset original observed side/errno')
                result={'passed':True,'planned_connections':len(clients),'record':matched,'trace_records':len(records)}
        except BaseException as failure:error=(error or '')+'; audit '+repr(failure)
        finally:
            try:monitor.close()
            except BaseException as failure:error=(error or '')+'; monitor '+repr(failure)
            if signals or time.monotonic()-started>60:error=(error or '')+'; lifecycle deadline/signal'
            try:write(root/'result.json',{'error':error,'metrics':result})
            finally:
                ledger.close(entry,time.monotonic()-started,'failed' if error else 'complete')
                for sig,handler in previous.items():signal.signal(sig,handler)
                signal.signal(signal.SIGALRM,old_alarm)
    if error:raise RuntimeError(error)
    return result
