"""Fixed S2 preflight matrix; delegates requests and lifecycle to frozen S1 tools."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import sys
import time
import threading
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/capacity'))
import Run
from Runtime import Ledger, Owned
from Common import MIB, rows, write
from Environment import identity

LIMIT = 1536 * MIB
CLOSURE = 16 * MIB
CELL_METADATA = 320 * 1024
ROLES = ['controller', 'backend-0', 'gateway-0', 'gateway-1', 'l4lb', 'generator-0', 'generator-1']
CONFIG = dict(workers=2, slots=128, capacity=32, reuse=False, nodelay=1, stream_mib=4, sample_interval=.1, fault='none')
S1_MANIFEST_SHA = 'f059fc20bf38d0c7f333440d925f1ff70316cd19beac7769b5fdc9bc49018e9a'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def used(root):
    return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file())


def matrix(role):
    if role not in ('builder', 'reviewer'):
        raise ValueError('unknown role')
    result = []
    for repeat in range(3):
        conditions = ['M1', 'L1', 'L2', 'LP']
        conditions = conditions[repeat:] + conditions[:repeat]
        if role == 'reviewer':
            conditions.reverse()
        for condition in conditions:
            result.append(dict(id=f'P-{condition}-r{repeat}', kind='diagnostic', condition=condition,
                               repeat=repeat, path='M' if condition == 'M1' else 'L', workload='A',
                               rate=3840, warm=3, duration=20, backend_workers=2 if condition == 'L2' else 1))
    return result


def reservation(spec):
    count = spec['rate'] * (spec['warm'] + spec['duration'])
    return count * (512 + 192 * spec['backend_workers'] + (256 if spec['path'] == 'L' else 0)) + 3 * MIB + CELL_METADATA


def topology():
    output = []
    for cpu in sorted(os.sched_getaffinity(0)):
        root = Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        output.append(dict(cpu=cpu, package=int((root / 'physical_package_id').read_text()),
                           core=int((root / 'core_id').read_text())))
    return output


def cpu_map(available):
    selected, seen = [], set()
    for item in available:
        key = item['package'], item['core']
        if key not in seen:
            selected.append(item['cpu'])
            seen.add(key)
    if len(selected) < 7:
        raise ValueError('seven visible distinct physical cores required')
    return dict(zip(ROLES, selected))


def source_check(previous_path, gateway, l4lb):
    previous = json.loads(Path(previous_path).read_text())
    current = {'gateway': identity(ROOT), 'l4lb': identity('/home/power/projects/L4-LoadBalancer-withXDP'),
               'binaries': {gateway: sha(gateway), l4lb: sha(l4lb)}}
    for role in ('gateway', 'l4lb'):
        for field in ('files', 'source_diff'):
            if current[role][field] != previous[role][field]:
                raise ValueError('S1 source protection differs: ' + role + '/' + field)
    if current['binaries'] != previous['binaries']:
        raise ValueError('S1 binaries differ or paths changed')
    return current


def tool_hashes():
    return {str(p.relative_to(ROOT)): sha(p) for folder in ['tests/capacity', 'tests/capacity_diagnosis']
            for p in sorted((ROOT / folder).glob('*.py'))}


def validate(manifest):
    if manifest['status'] != 'Frozen' or manifest['cells'] != matrix(manifest['role']) or manifest['configuration'] != CONFIG:
        raise ValueError('matrix or configuration is not the approved fixed experiment')
    if manifest['limits'] != {'cells': 12, 'active_seconds': 540, 'cell_seconds': 45, 'evidence_bytes': LIMIT,
                              'file_bytes': MIB, 'sampled_rss': 1024*MIB, 'sampled_fds': 2048}:
        raise ValueError('limits differ')
    expected_map = cpu_map(manifest['topology'])
    if manifest['cpu_map'] != expected_map or manifest['inherited_affinity'] != [r['cpu'] for r in manifest['topology']]:
        raise ValueError('CPU mapping differs')
    if manifest['worst_matrix_bytes'] != sum(map(reservation, manifest['cells'])):
        raise ValueError('matrix reservation differs')
    if manifest['worst_matrix_bytes'] + CLOSURE >= LIMIT:
        raise ValueError('whole matrix exceeds evidence budget')
    return manifest


def verify(manifest):
    validate(manifest)
    if manifest['tools'] != tool_hashes():
        raise ValueError('frozen tools changed')
    if topology() != manifest['topology'] or sorted(os.sched_getaffinity(0)) != manifest['inherited_affinity']:
        raise ValueError('runtime CPU availability changed')
    if shutil.which('taskset') != manifest['taskset'] or sha(manifest['taskset']) != manifest['taskset_sha256']:
        raise ValueError('taskset changed')
    if sha(manifest['s1_source_path']) != manifest['s1_source_sha256']:
        raise ValueError('S1 source evidence changed')
    observed = source_check(manifest['s1_source_path'], manifest['gateway'], manifest['l4lb'])
    if observed != manifest['sources']:
        raise ValueError('source identity changed after freeze')
    old = ROOT / 'docs/performance/V0.6/S1-manifest.json'
    if sha(old) != S1_MANIFEST_SHA:
        raise ValueError('S1 frozen manifest changed')
    frozen = json.loads(old.read_text())
    if any(manifest['tools'].get(k) != v for k, v in frozen['tools'].items()):
        raise ValueError('protected S1 tools changed')


def prepare(args):
    destination = Path(args.manifest)
    if destination.exists():
        raise ValueError('manifest already exists')
    available = topology()
    old = ROOT / 'docs/performance/V0.6/S1-manifest.json'
    if sha(old) != S1_MANIFEST_SHA:
        raise ValueError('S1 manifest identity')
    taskset = shutil.which('taskset')
    if not taskset:
        raise ValueError('taskset unavailable')
    def optional(path):
        try:
            return {'path': path, 'value': Path(path).read_text(), 'error': None}
        except OSError as error:
            return {'path': path, 'value': None, 'error': repr(error)}
    data = dict(status='Frozen', role=args.role, cells=matrix(args.role), configuration=CONFIG,
                gateway=args.gateway, l4lb=args.l4lb, s1_source_path=args.s1_source,
                s1_source_sha256=sha(args.s1_source), sources=source_check(args.s1_source, args.gateway, args.l4lb),
                tools=tool_hashes(), topology=available, cpu_map=cpu_map(available),
                inherited_affinity=sorted(os.sched_getaffinity(0)), taskset=taskset, taskset_sha256=sha(taskset),
                limits=dict(cells=12, active_seconds=540, cell_seconds=45, evidence_bytes=LIMIT,
                            file_bytes=MIB, sampled_rss=1024*MIB, sampled_fds=2048),
                worst_matrix_bytes=sum(map(reservation, matrix(args.role))),
                environment=dict(platform=platform.platform(), cpu_count=os.cpu_count(),
                                 cgroups=[optional(p) for p in ['/proc/self/cgroup', '/proc/self/mountinfo',
                                          '/sys/fs/cgroup/cpu.max', '/sys/fs/cgroup/memory.max']],
                                 route={k: os.getenv(k) for k in ['TMPDIR','TMP','TEMP','XDG_CACHE_HOME','PYTHONPYCACHEPREFIX']}))
    verify(data)
    write(destination, data, limit=MIB)
    print(json.dumps({'manifest': str(destination), 'sha256': sha(destination), 'worst_matrix_bytes': data['worst_matrix_bytes']}))


class DiagnosisLedger(Ledger):
    def reserve(self, spec):
        if len(self.data['cells']) >= 12 or self.data['active_seconds'] + 45 > 540:
            raise RuntimeError('diagnosis cell/activity budget')
        if used(self.budget_root) + reservation(spec) + CLOSURE > LIMIT:
            raise RuntimeError('diagnosis evidence budget')
        row = super().reserve(spec)
        row['reserved'] += CELL_METADATA
        self.save()
        return row


def owned_factory(mapping, taskset):
    class DiagnosisOwned(Owned):
        def __init__(self, command, name, root, limit):
            expected = mapping.get(name)
            if mapping and expected is None:
                raise ValueError('unknown pinned process role')
            if expected is not None:
                command = [taskset, '--cpu-list', str(expected), *command]
            super().__init__(command, name, root, limit)
            self.affinity_observed = None
            # taskset exec races Popen return; verify actual child, without starting HTTP early.
            try:
                deadline = time.monotonic() + 1
                while True:
                    observed = sorted(os.sched_getaffinity(self.process.pid))
                    if expected is None or observed == [expected]:
                        self.affinity_observed = observed
                        break
                    if time.monotonic() >= deadline or self.process.poll() is not None:
                        raise RuntimeError('child affinity did not match: ' + name)
                    time.sleep(.001)
                threads = [{'name': t.name, 'tid': t.native_id, 'affinity': sorted(os.sched_getaffinity(t.native_id))}
                           for t in threading.enumerate() if t.native_id is not None]
                controller_expected = [mapping['controller']] if mapping else sorted(os.sched_getaffinity(0))
                if any(t['affinity'] != controller_expected for t in threads):
                    raise ValueError('controller/capture/monitor thread affinity mismatch')
                write(Path(root) / ('affinity-startup-' + name + '.json'),
                      {'pid': self.process.pid, 'child_affinity': self.affinity_observed, 'threads': threads}, limit=32768)
            except BaseException:
                try:
                    record = self.close()
                    write(Path(root) / ('affinity-startup-failure-' + name + '.json'), record, limit=32768)
                finally:
                    raise

        def close(self):
            return super().close() | {'affinity_at_start': self.affinity_observed}
    return DiagnosisOwned


def check_affinities(folder, mapping, inherited, expected_roles, measure_start=0, measure_end=float("inf")):
    total, seen = 0, set()
    for row in rows(folder, 'resources'):
        for name, value in row['processes'].items():
            if name not in expected_roles:
                raise ValueError('unexpected resource process: ' + name)
            if measure_start <= row.get('start', 0) <= measure_end:
                seen.add(name)
            expected = [mapping[name]] if mapping else inherited
            if value['affinity'] != expected:
                raise ValueError('sampled affinity differs: ' + name)
        total += 1
    if not total or seen != set(expected_roles):
        raise ValueError('missing affinity samples or expected process')
    return total


def activity_guard(start, reserve=0):
    elapsed = time.monotonic() - start
    if elapsed + reserve > 540:
        raise RuntimeError('whole-run activity budget')
    return elapsed


def run(args):
    active_start = time.monotonic()
    path = Path(args.manifest)
    if sha(path) != args.sha256:
        raise ValueError('manifest SHA mismatch')
    manifest = json.loads(path.read_text())
    verify(manifest)
    output = Path(args.output)
    # No resume or retry: a previously created output is itself a permanent gate.
    if output.exists():
        raise ValueError('unique diagnosis output required')
    if used(output.parent) + manifest['worst_matrix_bytes'] + CLOSURE > LIMIT:
        raise ValueError('whole matrix reservation unavailable')
    output.mkdir()
    write(output / 'provenance.json', {'manifest': str(path), 'sha256': args.sha256, 'matrix_reservation': manifest['worst_matrix_bytes']})
    original_affinity = sorted(os.sched_getaffinity(0))
    original_owned, original_ledger = Run.Owned, Run.Ledger
    completed, attempted = [], []
    try:
        Run.Ledger = DiagnosisLedger
        for spec in manifest['cells']:
            activity_guard(active_start, 45)
            mapping = manifest['cpu_map'] if spec['condition'] == 'LP' else {}
            os.sched_setaffinity(0, [mapping['controller']] if mapping else original_affinity)
            if len(list(Path('/proc/self/task').iterdir())) != 1:
                raise RuntimeError('prior monitor/capture threads not joined')
            Run.Owned = owned_factory(mapping, manifest['taskset'])
            options = SimpleNamespace(**CONFIG, output=str(output), gateway=manifest['gateway'],
                                      l4lb=manifest['l4lb'], backends=spec['backend_workers'])
            attempted.append(spec['id'])
            result = Run.cell(spec, options)
            if result['corruption_all_phases'] or not result['drained']:
                raise RuntimeError('diagnostic correctness or drain failure')
            roles = {'controller', 'gateway-0', 'gateway-1', 'generator-0', 'generator-1'}
            roles.update('backend-' + str(i) for i in range(spec['backend_workers']))
            if spec['path'] == 'L':
                roles.add('l4lb')
            actual_spec = json.loads((output / spec['id'] / 'spec.json').read_text())
            samples = check_affinities(output / spec['id'], mapping, original_affinity, roles, actual_spec['measure_start'], actual_spec['measure_start'] + spec['duration'] * 1e9)
            thread_names = set()
            for item in (output / spec['id']).glob('affinity-startup-*.json'):
                thread_names.update(t['name'] for t in json.loads(item.read_text())['threads'])
            if not {'MainThread', 'resource-monitor', *('capture-' + name for name in roles if name != 'controller')} <= thread_names:
                raise ValueError('missing actual controller/monitor/capture thread affinity evidence')
            write(output / spec['id'] / 'affinity-verification.json', {'mapping': mapping, 'inherited': original_affinity, 'samples': samples}, limit=32768)
            completed.append({'id': spec['id'], 'condition': spec['condition'], 'repeat': spec['repeat'],
                              'result_sha256': sha(output / spec['id'] / 'result.json'), 'metrics': result})
            write(output / ('checkpoint-' + spec['id'] + '.json'), completed[-1], limit=MIB)
            activity_guard(active_start)
            print(json.dumps({'id': spec['id'], 'good_fraction': result['good_fraction'], 'outcomes': result['outcomes']}), flush=True)
            if used(output.parent) + CLOSURE > LIMIT:
                raise RuntimeError('diagnosis evidence limit')
        write(output / 'summary.json', completed, limit=MIB)
        activity_guard(active_start)
    except BaseException as error:
        write(output / 'stopped.json', {'error': repr(error), 'attempted_ids': attempted, 'verified_ids': [r['id'] for r in completed],
                                       'failed_verification_ids': [i for i in attempted if i not in {r['id'] for r in completed}],
                                       'not_started_ids': [s['id'] for s in manifest['cells'] if s['id'] not in attempted]})
        raise
    finally:
        Run.Owned, Run.Ledger = original_owned, original_ledger
        os.sched_setaffinity(0, original_affinity)
        write(output / 'controller-closure.json', {'whole_run_active_seconds': time.monotonic() - active_start,
                                                  'whole_run_within_540s': time.monotonic() - active_start <= 540, 'affinity': sorted(os.sched_getaffinity(0)), 'threads': len(list(Path('/proc/self/task').iterdir()))})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'run'])
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--role', choices=['builder','reviewer'])
    parser.add_argument('--gateway')
    parser.add_argument('--l4lb')
    parser.add_argument('--s1-source')
    parser.add_argument('--output')
    parser.add_argument('--sha256')
    args = parser.parse_args()
    if args.mode == 'run':
        if any(getattr(args, name) is not None for name in ['role','gateway','l4lb','s1_source']):
            raise ValueError('run configuration override prohibited')
        if not args.output or not args.sha256:
            raise ValueError('output and frozen sha256 required')
        def interrupted(signum, frame):
            raise KeyboardInterrupt('controller interrupted: ' + str(signum))
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGINT, interrupted)
        run(args)
    else:
        if not all([args.role, args.gateway, args.l4lb, args.s1_source]):
            raise ValueError('prepare requires role, binaries, S1 source identity')
        prepare(args)


if __name__ == '__main__':
    main()
