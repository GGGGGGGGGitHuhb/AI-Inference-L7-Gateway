"""Actual same-four-tuple reuse plus strict ambiguity rejection controls."""
import copy
import json
import socket
import threading
import time
from Association import associate


def check(root):
    rows=[];records=[];errors=[]
    with socket.socket() as listener, socket.socket() as reservation:
        listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(3)
        reservation.bind(('127.0.0.1',0));source=reservation.getsockname()[1];reservation.close()
        target=listener.getsockname()[1]
        for index,phase in enumerate(('warmup','formal','formal')):
            identifier=f'reuse-{phase}-{index}'
            def serve():
                try:
                    conn,peer=listener.accept();accepted=time.monotonic_ns()
                    with conn:
                        conn.settimeout(3);assert conn.recv(1024)==identifier.encode()
                        conn.sendall(identifier.encode());conn.shutdown(socket.SHUT_WR)
                        assert conn.recv(1)==b''
                    records.append({'id':index+1,'client_port':peer[1],'accepted':accepted,'finished':time.monotonic_ns()})
                except BaseException as error:errors.append(repr(error))
            thread=threading.Thread(target=serve);thread.start()
            with socket.socket() as client:
                client.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);client.settimeout(3)
                client.bind(('127.0.0.1',source));client.connect(('127.0.0.1',target));connected=time.monotonic_ns()
                client.sendall(identifier.encode());data=b''
                while True:
                    chunk=client.recv(1024)
                    if not chunk:break
                    data+=chunk
                assert data==identifier.encode();client.shutdown(socket.SHUT_WR)
            closed=time.monotonic_ns();thread.join(3);assert not thread.is_alive() and not errors,errors
            rows.append({'id':identifier,'outcome':'success','connect':connected,'closed':closed,'client_port':source,'target_port':target,'marker':data.decode()})
    scope={'cell_id':'reuse','host_pid':1,'target_port':target}
    mapping,excluded=associate(rows,records,**scope)
    assert [mapping[row['id']]['id'] for row in rows]==[1,2,3] and not excluded
    negatives=[]
    def reject(label,clients,hosts,**extra):
        try:associate(clients,hosts,**(scope|extra))
        except RuntimeError as error:negatives.append({'case':label,'error':str(error)})
        else:raise AssertionError('accepted ambiguity: '+label)
    reject('count',rows,records[:-1]);reject('duplicate-client',rows+[rows[0]],records)
    reject('duplicate-host',rows,records+[records[0]])
    extra=copy.deepcopy(records[0]);extra['id']=9;extra['client_port']=source+1
    reject('unmatched-host',rows,records+[extra])
    for side,start,end in [('client','connect','closed'),('host','accepted','finished')]:
        for kind in ('overlap','equal','missing','reverse'):
            left=copy.deepcopy(rows);right=copy.deepcopy(records);group=left if side=='client' else right
            if kind=='overlap':group[0][end]=group[1][start]+1
            elif kind=='equal':group[1][start]=group[0][start]
            elif kind=='missing':del group[1][start]
            else:group[1][end]=group[1][start]-1
            reject(side+'-'+kind,left,right)
    reject('foreign-cell',rows,records,cell_id='other')
    reject('foreign-listener',rows,records,target_port=target+1)
    reject('non-loopback',rows,records,client_address='192.0.2.1')
    plain=[rows[0]];plain_hosts=[records[0]]
    unsent=[{'id':'reuse-none-1','outcome':'not_sent'},{'id':'reuse-none-2','outcome':'not_started'},
            {'id':'reuse-none-3','outcome':'transport_failure','connect':None}]
    normal,excluded=associate(plain+unsent,plain_hosts,**scope)
    assert len(normal)==1 and len(excluded)==3
    bad=copy.deepcopy(unsent[0]);bad['client_port']=source
    reject('unissued-port',plain+[bad],plain_hosts)
    reject('unproven-success',[{'id':'reuse-bad','outcome':'success'}],[])
    (root/'association-reuse.json').write_text(json.dumps({'rows':rows,'host':records,'mapping':{k:v['id'] for k,v in mapping.items()},'excluded':excluded,'rejections':negatives},indent=2)+'\n')
