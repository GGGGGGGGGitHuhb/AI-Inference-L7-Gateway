"""Approved 57 cells, 7590 unique attempts, no adaptive rates or repeats."""
import hashlib
import json
from pathlib import Path

SLO = {'A': {'e2e': .1}, 'B': {'fast': .5, 'slow': 5},
       'H': {'ttft': .25, 'e2e': .5}, 'R': {'ttft': 2, 'e2e': 5}}


def build_plan():
    cells = []
    def add(group, repeat, path, concurrency=0, rate=0, count=0, nodelay=False, processes=1):
        number = len(cells)
        formal, warmup = {'A':(200,10),'B':(12,4),'H':(120,10),'Q':(120,10),
                          'R':(12,2),'T':(200,10),'N':(100,10)}[group]
        cell = dict(id=f'{number:02}-{group}-{repeat}-{path}', group=group, repeat=repeat,
                    path=path, concurrency=concurrency, rate=rate, queue_count=count,
                    nodelay=nodelay, processes=processes, formal=formal, warmup=warmup)
        cell['attempts'] = [dict(id=f'{cell["id"]}-{phase}-{i:03}', phase=phase,index=i,
            slow=group=='B' and i%4==0, long=group in ('H','Q') and i%4==3)
            for phase,n in [('warmup',warmup),('formal',formal)] for i in range(n)]
        cells.append(cell)
    add('T',0,'D',8)
    add('T',1,'D',8,processes=2)
    for repeat in range(3):
        for c in [1,4]:
            for path in [['D','PC','PR'],['PR','PC','D'],['PC','D','PR']][repeat]: add('A',repeat,path,c)
        for on in ([False,True] if repeat%2==0 else [True,False]): add('N',repeat,'PR',1,nodelay=on)
        for path in (['D','P'] if repeat%2==0 else ['P','D']):add('B',repeat,path,4)
        for rate in [20,60]:
            for path in (['RR','LI'] if repeat%2==0 else ['LI','RR']):add('H',repeat,path,rate=rate)
        for count in ([0,8] if repeat%2==0 else [8,0]):add('Q',repeat,'P',rate=60,count=count)
        for path in (['D','P'] if repeat%2==0 else ['P','D']):add('R',repeat,path,2)
    add('T',2,'D',8)
    ids=[a['id'] for c in cells for a in c['attempts']]
    assert len(cells)==57 and len(ids)==len(set(ids))==7590
    assert sum(c['formal'] for c in cells)==7104 and sum(c['warmup'] for c in cells)==486
    return {'cells':cells,'slo':SLO,'formal':7104,'warmup':486,'total':7590}


def request(cell, item):
    prompt='x'*256
    if cell['group']=='R':
        prompt=json.loads((Path(__file__).resolve().parents[1]/'integration/Inputs.json').read_text())['short']
    body=json.dumps({'model':'gateway-qwen','messages':[{'role':'user','content':prompt}],
        'temperature':0,'max_tokens':32,'stream':cell['group'] in ('B','H','Q','R'),'n':1},separators=(',',':')).encode()
    return (b'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nConnection: close\r\nX-Experiment-Id: '+item['id'].encode()+b'\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)


def configuration(cell, ports):
    real=cell['group']=='R'
    value={'listen_port':0,'max_connections':128,'max_reserved_bytes':2147483648,
        'models':[{'name':'gateway-qwen','policy':'least_inflight' if cell['path']=='LI' else 'round_robin',
                   'backends':[{'id':f'backend-{i}','address':'127.0.0.1','port':p} for i,p in enumerate(ports)]}],
        'health':{'failure_threshold':2,'cooldown_ms':1000},
        'upstream_pool':{'max_connections':32,'max_idle':4 if cell['path']=='PR' else 0,'idle_timeout_ms':5000},
        'stream_buffer':{'high_water_bytes':196608,'low_water_bytes':65536,'max_total_bytes':33554432},
        'timeouts_ms':{'request':5000,'connect':1000,'upstream_write':2000,'response':120000 if real else 10000,
                       'stream_idle':30000 if real else 5000,'downstream_write':10000,'total':150000 if real else 15000,'shutdown':3000}}
    if cell['group']=='Q':value['admission']={'max_inflight':2,'max_inflight_per_backend':1,
         'max_queue_requests_per_model':cell['queue_count'],'max_queue_bytes_per_model':65536,'queue_timeout_ms':500}
    return value
