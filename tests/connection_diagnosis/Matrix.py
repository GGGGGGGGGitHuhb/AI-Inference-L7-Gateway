"""Frozen 18-cell plan, hard gates, no retry/resume or critical CLI overrides."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from types import SimpleNamespace
import Negative
import RunCell
from TraceRuntime import LIMIT, CLOSURE, used
from Common import MIB, write

CONFIG=dict(workers=2,slots=128,backends=1,capacity=32,reuse=False,nodelay=1,stream_mib=4,sample_interval=.1,fault='none')
LIMITS=dict(cells=18,seconds=1200,cell_seconds=60,evidence_bytes=4096*MIB,performance_cell_bytes=256*MIB,negative_cell_bytes=16*MIB,closure_bytes=128*MIB,rss_bytes=1024*MIB,fds=2048,child_as_bytes=128*MIB,export_seconds=10)
GATES=dict(low_good=.99,low_difference=.01,latency_ratio=1.1,cpu_ratio=1.1,high_difference=.02)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plan(role):
    if role not in ('builder','reviewer'):raise ValueError('role')
    result=[dict(id='N-'+name,stage='negative',variant='T',negative=name) for name in Negative.KINDS]
    for repeat in range(3):
        order='UOT'[repeat:]+'UOT'[:repeat]
        if role=='reviewer':order=order[::-1]
        for variant in order:
            result.append(dict(id=f'L-1920-{variant}-r{repeat}',stage='low',variant=variant,repeat=repeat,path='L',workload='A',rate=1920,warm=3,duration=20))
    for repeat,order in enumerate(('UT','TU','UT')):
        if role=='reviewer':order=order[::-1]
        for variant in order:
            result.append(dict(id=f'L-3840-{variant}-r{repeat}',stage='high',variant=variant,repeat=repeat,path='L',workload='A',rate=3840,warm=3,duration=20))
    return result


def cpu_cost(metrics):
    values=metrics['resources']['processes']
    expected={'controller','generator-0','generator-1','backend-0','gateway-0','gateway-1','l4lb'}
    if set(values)!=expected:raise ValueError('CPU role coverage')
    total=0
    for value in values.values():
        if value['window_seconds']<19:raise ValueError('insufficient CPU measurement window')
        total+=(value['last']['ticks']-value['first']['ticks'])/value['ticks_per_second']
    return total/metrics['planned']


def gates(completed,stage):
    selected=[v for v in completed if v['spec']['stage']==stage]
    expected=9 if stage=='low' else 6
    if len(selected)!=expected:raise ValueError('incomplete gate input')
    failures=[];pairs=[]
    by_key={(v['spec']['repeat'],v['spec']['variant']):v['metrics'] for v in selected}
    if len(by_key)!=expected:raise ValueError('duplicate gate input')
    for item in selected:
        m=item['metrics']
        if not m['generator_valid'] or m['corruption_all_phases']:failures.append(item['spec']['id']+':invalid')
        if stage=='low' and m['good_fraction']<GATES['low_good']:failures.append(item['spec']['id']+':SLO')
    for repeat in range(3):
        for before,after in (('U','O'),('O','T')) if stage=='low' else (('U','T'),):
            a,b=by_key[repeat,before],by_key[repeat,after]
            entry=dict(repeat=repeat,before=before,after=after,good_difference=abs(b['good_fraction']-a['good_fraction']),cpu_ratio=cpu_cost(b)/cpu_cost(a))
            if entry['good_difference']>GATES['low_difference' if stage=='low' else 'high_difference']+1e-12:failures.append(f'{repeat}:{before}{after}:good difference')
            if entry['cpu_ratio']>GATES['cpu_ratio']:failures.append(f'{repeat}:{before}{after}:CPU')
            if stage=='low':
                for quantile in ('p95','p99'):
                    av=a['latency_ms']['http'].get(quantile);bv=b['latency_ms']['http'].get(quantile)
                    if av is None or bv is None or av<=0:raise ValueError('insufficient successful latency samples')
                    entry[quantile+'_ratio']=bv/av
                    if bv/av>GATES['latency_ratio']:failures.append(f'{repeat}:{before}{after}:{quantile}')
            pairs.append(entry)
    return dict(passed=not failures,failures=failures,pairs=pairs)


def verify(manifest):
    if manifest.get('status')!='Frozen' or manifest['cells']!=plan(manifest['role']):raise ValueError('frozen exact matrix required')
    if manifest['configuration']!=CONFIG or manifest['limits']!=LIMITS or manifest['gates']!=GATES:raise ValueError('frozen constants mismatch')
    if sorted(os.sched_getaffinity(0))!=manifest['cpu_affinity']:raise ValueError('controller affinity differs')
    required=set(str(p) for p in Path('tests/connection_diagnosis').glob('*.py')) | set(str(p) for p in Path('tests/capacity').glob('*.py'))
    required.add('tests/connection_diagnosis/L4ConnectionTrace.patch')
    required.add(manifest['source_snapshot'])
    required.update(p for v in manifest['binaries'].values() for p in v.values())
    if not required.issubset(manifest['files']):raise ValueError('missing frozen input')
    for path,digest in manifest['files'].items():
        if sha(path)!=digest:raise ValueError('file hash mismatch '+path)
    source=json.loads(Path(manifest['source_snapshot']).read_text())
    for path,digest in source['gateway'].items():
        if sha(path)!=digest:raise ValueError('Gateway source mismatch '+path)
    for path,digest in source['l4_modified_files'].items():
        if sha(Path(manifest['l4_source'])/path)!=digest:raise ValueError('isolated L4 mismatch '+path)
    if manifest['files'].get(source['l4_original_manifest'])!=source['l4_original_manifest_sha256']:raise ValueError('original source manifest identity')
    if sha(source['l4_patch'])!=source['l4_patch_sha256']:raise ValueError('patch source identity')
    original=json.loads(Path(source['l4_original_manifest']).read_text())
    isolated=Path(manifest['l4_source'])
    expected=set(original)|set(source['l4_modified_files'])
    actual={str(p.relative_to(isolated)) for p in isolated.rglob('*') if p.is_file()}
    if actual!=expected:raise ValueError('isolated L4 input set mismatch')
    for path in expected:
        digest=source['l4_modified_files'].get(path,original.get(path))
        if sha(isolated/path)!=digest:raise ValueError('isolated L4 full source mismatch '+path)
    for path,digest in original.items():
        if sha(Path(manifest['external_l4'])/path)!=digest:raise ValueError('external L4 source mismatch '+path)
    if shutil.disk_usage(manifest['output']).free<2*LIMIT:raise ValueError('insufficient disk for both roles')
    if used(Path(manifest['output']).parent)+4016*MIB>LIMIT:raise ValueError('whole matrix evidence reservation')


def run(manifest,manifest_sha,cell_runner=RunCell.cell,negative_runner=Negative.cell):
    started=time.monotonic();output=Path(manifest['output'])
    completed=[];attempted=[];error=None;gate_results={};status='complete';fresh=False
    try:
        output.mkdir(parents=True,exist_ok=True)
        if any(output.iterdir()):raise ValueError('fresh output required; no resume')
        fresh=True
        verify(manifest)
        write(output/'provenance.json',dict(manifest_sha256=manifest_sha,manifest=manifest),limit=MIB)
        for spec in manifest['cells']:
            if spec['stage']=='high' and 'low' not in gate_results:
                gate_results['low']=gates(completed,'low');write(output/'low-gate.json',gate_results['low'])
                if not gate_results['low']['passed']:status='blocked-low-overhead';break
            if time.monotonic()-started+60>1200:raise RuntimeError('whole matrix activity reservation')
            variant='U' if spec['variant']=='U' else 'trace'
            args=SimpleNamespace(**CONFIG,output=str(output),gateway=manifest['binaries'][variant]['gateway'],l4lb=manifest['binaries'][variant]['l4lb'])
            attempted.append(spec['id'])
            metrics=(negative_runner if spec['stage']=='negative' else cell_runner)(spec,args)
            completed.append(dict(spec=spec,metrics=metrics))
            write(output/f'checkpoint-{len(completed):02}.json',completed[-1],limit=MIB)
            print(json.dumps({'completed':len(completed),'id':spec['id'],'good_fraction':metrics.get('good_fraction'),'generator_valid':metrics.get('generator_valid')}),flush=True)
        if len(completed)==18:
            gate_results['high']=gates(completed,'high')
            if not gate_results['high']['passed']:status='blocked-high-overhead'
    except BaseException as failure:error=repr(failure);status='failed'
    finally:
        elapsed=time.monotonic()-started
        if elapsed>1200 or used(output.parent)>LIMIT:error=(error or '')+'; whole activity/evidence ceiling';status='failed'
        result=dict(status=status,error=error,elapsed_seconds=elapsed,attempted_ids=attempted,
                    verified_ids=[v['spec']['id'] for v in completed],not_started_ids=[v['id'] for v in manifest['cells'] if v['id'] not in attempted],
                    gates=gate_results,completed=completed)
        if fresh:
            write(output/'summary.json',result,limit=MIB)
            after_summary=time.monotonic()-started
            evidence_bytes=used(output.parent)
            closing_error=after_summary>1200 or evidence_bytes>LIMIT
            write(output/'closure.json',dict(elapsed_through_summary_seconds=after_summary,evidence_bytes=evidence_bytes,budget_pass=not closing_error))
            if closing_error or time.monotonic()-started>1200 or used(output.parent)>LIMIT:
                error=(error or '')+'; post-summary budget failure'
                write(output/'closure-failure.json',dict(error=error))
        else:
            # A rejected existing directory is never rewritten or resumed.
            output.parent.mkdir(parents=True,exist_ok=True)
            write(output.parent/f'preflight-failure-{time.monotonic_ns()}.json',result,limit=MIB)
    if error:raise RuntimeError(error)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--sha256',required=True);parser.add_argument('--verify-only',action='store_true')
    args=parser.parse_args()
    if sha(args.manifest)!=args.sha256:raise SystemExit('manifest SHA mismatch')
    manifest=json.loads(Path(args.manifest).read_text())
    if args.verify_only:verify(manifest)
    else:run(manifest,args.sha256)
