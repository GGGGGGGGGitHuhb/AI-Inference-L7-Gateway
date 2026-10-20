"""受控实例、门控长流、固定请求计数；所有进程在 finally 回收。"""
import copy
import http.client
import http.server
import json
import os
from pathlib import Path
import selectors
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time

EXE = sys.argv[1]
checks = 0

def check(condition, detail=''):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(detail)

class Backend(http.server.ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, label):
        super().__init__(('127.0.0.1', 0), Handler)
        self.label = label
        self.status = 200
        self.mode = 'normal'
        self.requests = []
        self.gate = threading.Event()
        self.started = threading.Event()
        self.worker = threading.Thread(target=self.serve_forever, daemon=True)
        self.worker.start()
    def close(self):
        self.gate.set()
        self.shutdown()
        self.server_close()
        self.worker.join(3)
        check(not self.worker.is_alive())

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass
    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.requests.append((body, self.headers['Host']))
            mode, status = self.server.mode, self.server.status
            if mode in ('hold', 'truncate'):
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Transfer-Encoding', 'chunked')
                self.end_headers()
                self.wfile.write(b'9\r\ndata: x\n\n\r\n'); self.wfile.flush()
                self.server.started.set()
                self.server.gate.wait(3)
                if mode == 'hold':
                    self.wfile.write(b'0\r\n\r\n'); self.wfile.flush()
                self.close_connection = True
                return
            payload = json.dumps({'backend': self.server.label, 'model': body['model']}).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload); self.wfile.flush()
        except (OSError, ValueError):
            self.close_connection = True

class Gateway:
    def __init__(self, folder, config):
        path = Path(folder)/'config.json'; path.write_text(json.dumps(config))
        self.process = subprocess.Popen([EXE, '--config', str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                check(bool(selector.select(5)), 'ready timeout')
            line = self.process.stdout.readline()
            check(line.startswith('READY '), line)
            self.port = int(line.rsplit(':', 1)[1])
        except BaseException:
            self.process.kill(); self.process.communicate(); raise
    def close(self):
        if self.process.poll() is None: self.process.send_signal(signal.SIGTERM)
        try: out, err = self.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.communicate(); raise
        check(self.process.returncode == 0, err)
        check('AddressSanitizer' not in err and 'runtime error:' not in err, err)

def request(port, model='a'):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=4)
    try:
        conn.request('POST', '/v1/chat/completions', json.dumps({'model': model, 'messages': [{'role':'user','content':'fixed'}]}), {'Content-Type':'application/json'})
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally: conn.close()

def stream(port, model='a'):
    conn = socket.create_connection(('127.0.0.1', port), timeout=4)
    body = json.dumps({'model':model,'stream':True,'messages':[{'role':'user','content':'fixed'}]}).encode()
    conn.sendall(b'POST /v1/chat/completions HTTP/1.1\r\nHost: client\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
    return conn

def config_for(backends, policy='round_robin'):
    return {'listen_port':0, 'models':[
        {'name':name,'policy':policy,'backends':[{'id':b.label,'address':'127.0.0.1','port':b.server_port} for b in group]}
        for name,group in [('a',backends[:2]),('b',backends[2:])]],
        'health':{'failure_threshold':1,'cooldown_ms':30},
        'timeouts_ms':{'shutdown':100,'response':1000}}

def config_checks(folder, config):
    bad = []
    for key,value in [('models',[]),('models',{}),('models', [dict(config['models'][0], policy='random')]),('health',{'failure_threshold':0}),('health',{'failure_threshold':17}),('health',{'failure_threshold':True}),('health',{'failure_threshold':1.5}),('health',{'cooldown_ms':300001}),('health',[]),('health',{'cooldown_ms':9}),('health',{'unknown':2}),('upstream_address','127.0.0.1'),('upstream_port',9000)]:
        item = copy.deepcopy(config); item[key]=value; bad.append(item)
    for key,value in [('name',''),('name','x'*257),('name','a\x00'),('name',4),('backends',[{}]),('backends',[]),('policy',3),('unknown',1)]:
        item=copy.deepcopy(config); item['models'][0][key]=value; bad.append(item)
    for key,value in [('id',''),('id','x'*65),('id','é'),('address','0.0.0.0'),('address','localhost'),('port',0),('port',65536),('port',-1),('port',1.5),('unknown',1)]:
        item=copy.deepcopy(config); item['models'][0]['backends'][0][key]=value; bad.append(item)
    for missing in ('name','backends'):
        item=copy.deepcopy(config); del item['models'][0][missing]; bad.append(item)
    for missing in ('id','address','port'):
        item=copy.deepcopy(config); del item['models'][0]['backends'][0][missing]; bad.append(item)
    item=copy.deepcopy(config); item['models']*=17; bad.append(item)
    item=copy.deepcopy(config); item['models'][0]['backends']*=33; bad.append(item)
    item=copy.deepcopy(config); item['models'][1]['name']='a'; bad.append(item)
    item=copy.deepcopy(config); item['models'][0]['backends'][1]['id']=item['models'][0]['backends'][0]['id']; bad.append(item)
    item=copy.deepcopy(config); item['models'][0]['backends'][1]['port']=item['models'][0]['backends'][0]['port']; bad.append(item)
    item=copy.deepcopy(config); item['listen_port']=item['models'][0]['backends'][0]['port']; bad.append(item)
    item=copy.deepcopy(config); item['models'].append({'name':'c','backends':[{'id':'c','address':'127.0.0.1','port':9999}]}); item['upstream_pool']={'max_connections':256}; bad.append(item)
    bad.extend([{}, {'upstream_port':9000}, {'upstream_address':'127.0.0.1'}, {'upstream_port':9000,'upstream_address':'127.0.0.1','health':{}}])
    texts = [json.dumps(item) for item in bad] + ['{"models":[],"models":[]}', '{"models":[[[[[[[[]]]]]]]]}', ' '*65537, '{"models":[{"name":"a","name":"b","backends":[]}]}']
    for index, text in enumerate(texts):
        path=Path(folder)/f'bad-{index}.json'; path.write_text(text)
        result=subprocess.run([EXE,'--config',str(path)], capture_output=True, text=True, timeout=4)
        check(result.returncode != 0 and 'READY' not in result.stdout, (index,result.stdout,result.stderr))

def main():
    backends=[Backend(str(i)) for i in range(4)]
    try:
      with tempfile.TemporaryDirectory() as folder:
        config=config_for(backends)
        config_checks(folder,config)
        # 合法最大32模型/64实例/1024池上限，边界不只做拒绝测试。
        boundary={'listen_port':0,'models':[
            {'name':f'm{i}','backends':[{'id':f'b{j}','address':'127.0.0.1','port':i*2+j+1} for j in range(2)]}
            for i in range(32)]}
        boundary_gateway=Gateway(folder,boundary)
        boundary_gateway.close()
        gateway=Gateway(folder,config)
        try:
            for name,labels in [('a',['0','1']*3),('b',['2','3']*3)]:
                for label in labels:
                    status,body=request(gateway.port,name)
                    check(status==200 and body['backend']==label and body['model']==name,body)
            before=sum(len(b.requests) for b in backends)
            status,body=request(gateway.port,'unknown')
            check(status==404 and body['error']['code']=='model_not_found',body)
            check(sum(len(b.requests) for b in backends)==before)
            for backend in backends:
                check(all(host==f'127.0.0.1:{backend.server_port}' for _,host in backend.requests))
            # 两模型四实例各执行三轮摘除；普通400/429不标记失败。
            for cycle in range(3):
                for backend in backends: backend.status=503
                for name in ('a','b'):
                    before=sum(len(b.requests) for b in backends)
                    check(request(gateway.port,name)[0]==503)
                    check(request(gateway.port,name)[0]==503)
                    status,body=request(gateway.port,name)
                    check(status==503 and body['error']['code']=='no_available_backend',body)
                    check(sum(len(b.requests) for b in backends)==before+2,'retry')
                # TCP仍成功，404试探仍失败。
                time.sleep(.04)
                for backend in backends: backend.status=404
                for name in ('a','b'):
                    check(request(gateway.port,name)[0]==404)
                    check(request(gateway.port,name)[0]==404)
                    check(request(gateway.port,name)[1]['error']['code']=='no_available_backend')
                time.sleep(.04)
                for backend in backends: backend.status=200
                for name in ('a','b'):
                    check(request(gateway.port,name)[0]==200)
                    check(request(gateway.port,name)[0]==200)
            for neutral in (400,429):
                for backend in backends: backend.status=neutral
                for _ in range(6): check(request(gateway.port)[0]==neutral)
            for backend in backends: backend.status=200
        finally: gateway.close()
        # LI 长流占用实例0时，所有短请求去1；门控释放后恢复平局轮转。
        config=config_for(backends,'least_inflight')
        gateway=Gateway(folder,config)
        held=None
        try:
            backends[0].mode='hold'; backends[0].gate.clear(); backends[0].started.clear()
            held=stream(gateway.port)
            check(backends[0].started.wait(2))
            for _ in range(4): check(request(gateway.port)[1]['backend']=='1')
            held.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0)); held.close(); held=None
            backends[0].gate.set(); backends[0].mode='normal'
            # 未终结客户端取消中立，不摘除；下一独立请求可用。
            time.sleep(.02)
            check(request(gateway.port)[0]==200)
        finally:
            if held: held.close()
            backends[0].gate.set(); gateway.close()
        # 停机同时覆盖活动Trial流和另一实例idle。
        config=config_for(backends); gateway=Gateway(folder,config)
        held=None
        try:
            backends[0].mode='normal'; backends[0].status=503
            check(request(gateway.port)[0]==503)
            check(request(gateway.port)[0]==200)  # 实例1留下idle
            time.sleep(.04)
            backends[0].status=200; backends[0].mode='hold'
            backends[0].gate.clear(); backends[0].started.clear()
            held=stream(gateway.port)
            check(backends[0].started.wait(2))
            check(held.recv(4096).startswith(b'HTTP/1.1 200'))
        finally:
            gateway.close()
            if held: held.close()
            backends[0].gate.set(); backends[0].mode='normal'
        # legacy允许任意合法model；同物理地址可由不同model独立配置。
        legacy={'listen_port':0,'upstream_address':'127.0.0.1','upstream_port':backends[0].server_port}
        gateway=Gateway(folder,legacy)
        try: check(request(gateway.port,'arbitrary-model')[1]['model']=='arbitrary-model')
        finally: gateway.close()
        shared=config_for(backends)
        shared['models'][1]['backends']=copy.deepcopy(shared['models'][0]['backends'])
        gateway=Gateway(folder,shared)
        try:
            check(request(gateway.port,'a')[1]['model']=='a')
            check(request(gateway.port,'b')[1]['model']=='b')
        finally: gateway.close()
        # 已提交流被截断，不伪造第二HTTP状态/成功零块。
        config=config_for(backends); gateway=Gateway(folder,config)
        try:
            backends[0].mode='truncate'; backends[0].gate.clear(); backends[0].started.clear()
            with stream(gateway.port) as held:
                check(backends[0].started.wait(2))
                first=held.recv(4096); check(first.startswith(b'HTTP/1.1 200'),first)
                backends[0].gate.set()
                response=first
                while True:
                    piece=held.recv(4096)
                    if not piece: break
                    response+=piece
                check(response.count(b'HTTP/1.1 ')==1 and not response.endswith(b'0\r\n\r\n'),response)
        finally: gateway.close()
    finally:
        for backend in backends: backend.close()
    print(f'RoutingE2E checks={checks}, all owned processes reaped')

if __name__=='__main__': main()
