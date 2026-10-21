"""Incremental validation; at most 8 KiB persisted per attempt, never a 4 MiB body."""
import hashlib
import json
from pathlib import Path
import socket
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
from WireResponse import WireResponse


def sse_body(size):
    records=[]
    for index in range(size//1024):
        data='[DONE]' if index==size//1024-1 else json.dumps({'choices':[{'delta':{'content':'x'},
            'finish_reason':'stop' if index==size//1024-2 else None}]},separators=(',',':'))
        record=('data: '+data).encode();records.append(record+b' '*(1022-len(record))+b'\n\n')
    return b''.join(records)


H_BODY=b'data: {"choices":[{"delta":{"content":"x"},"finish_reason":null}]}\n\ndata: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
H_BODY+=b'data: [DONE]'+b' '*(1024-len(H_BODY)-len(b'data: [DONE]')-2)+b'\n\n'
PAYLOADS={'A':b'{"value":"'+b'x'*1012+b'"}','B':sse_body(4194304),'H':H_BODY}
HASHES={k:hashlib.sha256(v).hexdigest() for k,v in PAYLOADS.items()}
CLOCKS=('dispatch','connect','send','head','first_body','content','http_complete','closed')


class TimedResponse(WireResponse):
    def __init__(self,sock,row,deadline,slow):
        super().__init__(sock);self.row=row;self.deadline=deadline;self.slow=slow;self.last_recv=None

    def receive(self):
        remaining=(self.deadline-time.monotonic_ns())/1e9
        if remaining<=0:raise TimeoutError('absolute client deadline')
        self.sock.settimeout(remaining)
        part=self.sock.recv(16384);self.last_recv=time.monotonic_ns()
        if part:
            self.buffer+=part
            if self.slow:time.sleep(.005)
        return bool(part)

    def finish(self):
        if self.row['http_complete'] is None:self.row['http_complete']=self.last_recv
        return super().finish()

    def read1(self,maximum):
        part=super().read1(maximum)
        if part and self.row['first_body'] is None:self.row['first_body']=self.last_recv
        if self.length==0 and self.row['http_complete'] is None:self.row['http_complete']=self.last_recv
        return part


def attempt(port,request,item,group,scheduled=None,on_start=None):
    row={**item,**dict.fromkeys(CLOCKS),'scheduled':scheduled,'status':None,'outcome':'transport_failure',
         'error':None,'error_code':None,'body_bytes':0,'done':0,'finishes':0,
         'request_sha256':hashlib.sha256(request).hexdigest(),'target_port':port}
    if scheduled is not None and time.monotonic_ns()-scheduled>50000000:
        row.update(outcome='not_sent',reason='dispatch_late',checked=time.monotonic_ns(),closed=time.monotonic_ns())
        return row
    if on_start:on_start(item['id'],time.monotonic_ns())
    stream=group in ('B','H','Q','R');slow=item.get('slow',False)
    row['dispatch']=time.monotonic_ns();deadline=row['dispatch']+int((155 if group=='R' else 16)*1e9)
    sock=None;response=None;hasher=hashlib.sha256();prefix=bytearray();events=b'';complete=False
    try:
        sock=socket.create_connection(('127.0.0.1',port), (deadline-time.monotonic_ns())/1e9)
        row['connect']=time.monotonic_ns();row['client_port']=sock.getsockname()[1]
        if slow:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,65536)
            row['actual_rcvbuf']=sock.getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF)
        sock.settimeout(max(.001,(deadline-time.monotonic_ns())/1e9));sock.sendall(request);row['send']=time.monotonic_ns()
        response=TimedResponse(sock,row,deadline,slow)
        if slow:time.sleep(.5)
        response.begin();row['head']=response.last_recv;row['status']=response.status
        while True:
            part=response.read1(16384)
            if not part:complete=True;break
            hasher.update(part);row['body_bytes']+=len(part)
            if row['body_bytes']>8*1024**2:raise ValueError('response byte limit')
            if len(prefix)<16384:prefix.extend(part[:16384-len(prefix)])
            if stream and response.status==200:
                events+=part
                while b'\n\n' in events:
                    event,events=events.split(b'\n\n',1)
                    for line in event.splitlines():
                        if not line.startswith(b'data:'):continue
                        if row['done']:raise ValueError('SSE after DONE')
                        data=line[5:].strip()
                        if data==b'[DONE]':
                            if row['finishes']!=1 or row['content'] is None:raise ValueError('DONE before content/finish')
                            row['done']+=1;continue
                        value=json.loads(data)
                        if 'timings' in value:row['backend_timings']=value['timings']
                        if 'usage' in value:row['usage']=value['usage']
                        for choice in value.get('choices',[]):
                            content=choice.get('delta',{}).get('content')
                            if content:
                                if not isinstance(content,str):raise ValueError('non-text content')
                                if row['content'] is None:row['content']=response.last_recv
                            if choice.get('finish_reason'):row['finishes']+=1
                if len(events)>65536:raise ValueError('SSE event limit')
        if not row['http_complete']:raise ValueError('missing legal HTTP terminal')
        if response.status!=200:
            code=json.loads(prefix)['error']['code'];row['error_code']=code
            allowed={503:{'queue_full','queue_bytes_exceeded','no_available_backend','upstream_capacity','gateway_stopping'},
                     504:{'queue_timeout','total_timeout','response_timeout','stream_idle_timeout'}}
            if code not in allowed.get(response.status,set()):raise ValueError('unclassified HTTP error')
            row['outcome']='http_timeout' if response.status==504 else 'http_rejection'
        else:
            if stream and (row['content'] is None or row['finishes']!=1 or row['done']!=1 or events.strip()):raise ValueError('incomplete SSE')
            key='A' if group in ('A','T','N') else 'H' if group=='Q' else group
            if key in HASHES and (hasher.hexdigest()!=HASHES[key] or row['body_bytes']!=len(PAYLOADS[key])):raise ValueError('body identity')
            if not stream:json.loads(prefix)
            row['outcome']='success'
    except BaseException as error:
        row['error']=repr(error)[:1024]
        row['outcome']='client_deadline' if isinstance(error,TimeoutError) else 'transport_failure' if isinstance(error,OSError) else 'protocol_failure'
    finally:
        if sock:sock.close()
        row['closed']=time.monotonic_ns();row['body_sha256']=hasher.hexdigest();row['http_valid']=complete and bool(row['http_complete'])
        if row['outcome']!='success':row['error_prefix']=bytes(prefix[:256]).decode('utf-8','replace')
    if len(json.dumps(row).encode())>8192:raise RuntimeError('attempt summary exceeds 8KiB')
    return row
