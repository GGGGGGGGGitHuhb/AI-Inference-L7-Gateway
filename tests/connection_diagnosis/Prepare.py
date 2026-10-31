"""Write a reviewable Draft only; never starts a cell or silently freezes it."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
from Matrix import CONFIG,LIMITS,GATES,plan,sha
from Common import write,MIB


def prepare(args):
    root=Path(args.root).resolve();output=root/'evidence/run';output.mkdir(parents=True,exist_ok=True)
    snapshot=Path(args.source_snapshot).resolve();source=json.loads(snapshot.read_text())
    binaries={variant:dict(gateway=str((root/'gateway'/folder/'ai-inference-gateway').resolve()),
                           l4lb=str((root/'l4-build'/folder/'bin/l4lb').resolve())) for variant,folder in (('U','uninstrumented'),('trace','trace'))}
    paths=list(Path('tests/connection_diagnosis').glob('*.py'))+list(Path('tests/capacity').glob('*.py'))
    paths += [Path('tests/connection_diagnosis/L4ConnectionTrace.patch'),snapshot,Path(source['l4_original_manifest'])]
    for variant in binaries.values():paths.extend(Path(p) for p in variant.values())
    for project in ('gateway','l4-build'):
        for folder in ('uninstrumented','trace'):paths.append(root/project/folder/'CMakeCache.txt')
    files={str(p):sha(p) for p in paths}
    manifest=dict(schema='S2-trace-1',status='Draft',role=args.role,output=str(output),cells=plan(args.role),
                  configuration=CONFIG,limits=LIMITS,gates=GATES,binaries=binaries,files=files,
                  cpu_affinity=sorted(os.sched_getaffinity(0)),environment=dict(platform=platform.platform(),
                  python=platform.python_version(),clock='Linux CLOCK_MONOTONIC ns',
                  compiler=subprocess.check_output(['c++','--version'],text=True).splitlines()[0]),
                  source_snapshot=str(snapshot),l4_source=str(root/'l4-source'),external_l4=args.external_l4,
                  budget=dict(full_reservation_bytes=4016*MIB,negative_connections=[2,2,1],
                  maximum_performance_scheduled=88320,record_bytes=256,slots_per_process=131071,
                  maximum_trace_processes=3,maximum_export_bytes_per_process=32*MIB,
                  row_caps=dict(client=512,backend=192,client_endpoints=256,backend_endpoints=192,association=256,l4_log_per_request=256)))
    write(args.manifest,manifest,limit=MIB)
    print(json.dumps(dict(manifest=args.manifest,sha256=sha(args.manifest),status='Draft')))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--role',choices=['builder','reviewer'],required=True)
    parser.add_argument('--source-snapshot',required=True);parser.add_argument('--external-l4',default='/home/power/projects/L4-LoadBalancer-withXDP');parser.add_argument('--manifest',required=True)
    prepare(parser.parse_args())
