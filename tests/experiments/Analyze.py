"""Raw per-cell re-audit and three-repeat descriptive pairing; no sample pooling."""
import json
import statistics
from pathlib import Path
from Statistics import summarize
from Budget import save


def analyze(root):
    root=Path(root);plan=json.loads((root/'plan.json').read_text());results=[];ids=set()
    for cell in plan['cells']:
        folder=root/cell['id'];phases={}
        for phase in ['warmup','formal']:
            items=[a for a in cell['attempts'] if a['phase']==phase]
            rows=[json.loads((folder/(a['id']+'.json')).read_text()) for a in items]
            for row in rows:
                if row['id'] in ids:raise ValueError('duplicate plan ID')
                ids.add(row['id'])
            old=json.loads((folder/(phase+'-summary.json')).read_text())
            computed=summarize(cell,items,rows,old['t0'])
            for key,value in computed.items():
                if value!=old[key]:raise ValueError('summary differs from raw: '+key)
            phases[phase]=computed
        resources=[json.loads(line) for line in (folder/'client-resources.jsonl').read_text().splitlines()]
        formal_clients=resources[-cell['processes']:]
        cpu=[r['cpu_seconds']/phases['formal']['wall_seconds'] for r in formal_clients]
        results.append({'id':cell['id'],'group':cell['group'],'repeat':cell['repeat'],'path':cell['path'],
            'rate':cell['rate'],'queue_count':cell['queue_count'],'concurrency':cell['concurrency'],'nodelay':cell['nodelay'],
            'phases':phases,'client_cpu_cores':cpu})
    if len(ids)!=7590:raise ValueError('plan conservation')
    controls=[r for r in results if r['group']=='T'];t=[r['phases']['formal']['completion_throughput'] for r in controls]
    flags={'machine_drift':abs(t[2]/t[0]-1)>.2,'generator_sensitive':abs(t[1]/t[0]-1)>.15,
           'client_cpu_at_least_085':any(max(r['client_cpu_cores'])>=.85 for r in results)}
    flags['suspected_generator_limit']=flags['client_cpu_at_least_085'] and (flags['machine_drift'] or flags['generator_sensitive'])
    pairings={}
    for group,rates in [('H',[20,60]),('Q',[60])]:
        for rate in rates:
            pairs=[]
            for repeat in range(3):
                selected=[r for r in results if r['group']==group and r['rate']==rate and r['repeat']==repeat]
                selected.sort(key=lambda r:(0 if r['path']=='RR' else 1) if group=='H' else r['queue_count'])
                first,second=selected
                pairs.append({'repeat':repeat,'first':first['id'],'second':second['id'],
                    'valid':not any(r['phases']['formal']['arrival_limited'] for r in selected),
                    'goodput_second_minus_first':second['phases']['formal']['goodput']-first['phases']['formal']['goodput']})
            pairings[f'{group}-{rate}']=pairs
    blocked=[]
    if not any(sum(p['valid'] for p in pairings[f'H-{rate}'])>=2 for rate in [20,60]):blocked.append('H arrival control')
    if sum(p['valid'] for p in pairings['Q-60'])<2:blocked.append('Q arrival control')
    repeats={}
    for row in results:
        if row['group']=='T':continue
        key=f"{row['group']}/{row['path']}/C{row['concurrency']}/rate{row['rate']}/q{row['queue_count']}/nodelay{row['nodelay']}"
        repeats.setdefault(key,[]).append(row['phases']['formal']['goodput'])
    repeat_stats={k:{'values':v,'median':statistics.median(v),'min':min(v),'max':max(v)} for k,v in repeats.items()}
    result={'status':'BLOCKED' if blocked else 'PASS','blocked':blocked,'flags':flags,'controls_throughput':t,
            'pairings':pairings,'goodput_three_repeats':repeat_stats,'cells':results,'unique_ids':len(ids)}
    save(root/'analysis.json',result)
    return result
