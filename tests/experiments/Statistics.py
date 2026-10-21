"""Conservation, clock validation, nearest-rank thresholds and frozen SLO."""
import math
import statistics
from collections import Counter

OUTCOMES={'success','http_rejection','http_timeout','transport_failure','protocol_failure',
          'client_deadline','not_sent','not_started','interrupted'}


def quantiles(values):
    values=sorted(values);n=len(values)
    row={'n':n,'min':min(values) if n else None,'median':statistics.median(values) if n else None,'max':max(values) if n else None}
    for label,p,minimum in [('p50',.5,20),('p95',.95,100),('p99',.99,1000)]:
        if n>=minimum:row[label]=values[math.ceil(p*n)-1]
    return row


def check_row(row):
    if row['outcome'] not in OUTCOMES:raise ValueError('unknown outcome')
    clocks=[row.get(k) for k in ['dispatch','connect','send','head','first_body','content','http_complete','closed']]
    clocks=[v for v in clocks if v is not None]
    if any(a>b for a,b in zip(clocks,clocks[1:])):raise ValueError('nonmonotonic client clocks')
    if row.get('scheduled') is not None and row.get('dispatch') is not None and row['dispatch']<row['scheduled']:raise ValueError('dispatch before schedule')
    if row['outcome']=='success' and (row.get('status')!=200 or not row.get('http_valid')):raise ValueError('false success')
    if row['outcome']=='http_timeout' and (row.get('status')!=504 or row.get('error_code') not in {'queue_timeout','total_timeout','response_timeout','stream_idle_timeout'}):raise ValueError('false HTTP timeout')
    if row['outcome']=='http_rejection' and (row.get('status')!=503 or row.get('error_code') not in {'queue_full','queue_bytes_exceeded','no_available_backend','upstream_capacity','gateway_stopping'}):raise ValueError('false rejection')
    if row['outcome'] in ('not_sent','not_started') and row.get('send') is not None:raise ValueError('unsent with send clock')


def summarize(cell,items,rows,t0):
    if len(rows)!=len(items) or {r['id'] for r in rows}!={i['id'] for i in items}:raise ValueError('missing/duplicate IDs')
    for row in rows:check_row(row)
    counts=dict(Counter(r['outcome'] for r in rows));success=[r for r in rows if r['outcome']=='success']
    def origin(r):return r['scheduled'] if cell['rate'] else r['dispatch']
    def passes(r):
        end=(r['http_complete']-origin(r))/1e9
        group=cell['group']
        limit=5 if group=='R' or (group=='B' and r['slow']) else .5 if group in ('B','H','Q') else .1
        content=(r['content']-origin(r))/1e9 if r.get('content') else None
        return end<=limit and (group not in ('H','Q','R') or content is not None and content<=(2 if group=='R' else .25))
    met=sum(passes(r) for r in success)
    closed=max(r['closed'] for r in rows);wall=(closed-t0)/1e9
    duration=len(items)/cell['rate'] if cell['rate'] else wall
    result={'counts':counts,'success':len(success),'slo_met':met,'wall_seconds':wall,
        'goodput':met/duration,'completion_throughput':len(success)/wall,
        'offered':cell['rate'] or None,'window_seconds':duration,
        'window_late_completions':sum(r['http_complete']>t0+duration*1e9 for r in success) if cell['rate'] else 0,
        'e2e':quantiles([(r['http_complete']-origin(r))/1e9 for r in success]),
        'ttft':quantiles([(r['content']-origin(r))/1e9 for r in success if r.get('content')]),
        'send_e2e':quantiles([(r['http_complete']-r['send'])/1e9 for r in success]),
        'send_ttft':quantiles([(r['content']-r['send'])/1e9 for r in success if r.get('content')])}
    dispatch=[(r['dispatch']-r['scheduled'])/1e9 for r in rows if r.get('dispatch') is not None and r.get('scheduled') is not None]
    send=[(r['send']-r['scheduled'])/1e9 for r in rows if r.get('send') is not None and r.get('scheduled') is not None]
    result['dispatch_lag']=quantiles(dispatch);result['send_lag']=quantiles(send)
    p95=sorted(dispatch)[math.ceil(.95*len(dispatch))-1] if dispatch else None
    result['arrival_limited']=bool(cell['rate'] and (counts.get('not_sent',0)/len(items)>.01 or p95 is None or p95>.005))
    for label,filter_key in [('slow','slow'),('long','long')]:
        result[label+'_split']={str(value):{'n':sum(bool(r.get(filter_key))==value for r in success),
            'e2e':quantiles([(r['http_complete']-origin(r))/1e9 for r in success if bool(r.get(filter_key))==value])} for value in [False,True]}
    return result
