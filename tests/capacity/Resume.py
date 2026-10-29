"""Approved fixed role-specific continuations only; never a generic resume facility."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import time
import signal
from Common import digest, MIB, write, rows, COLUMNS
from Analyze import audit
from Formal import validate, verify_sources, worst_bytes
from ResourceSummary import summarize
from Runtime import Ledger

V1_SHA = '81877a406c767b66fb90422a79b805f53c3c77a13869219b4f967ee5116358f4'
REWORK = 'docs/leader/reworks/V0.6/S1-rework-001.md'
PREFIX = ['F-A-B-960-r0', 'F-A-G-960-r0', 'F-A-M-960-r0', 'F-A-L-960-r0',
          'F-A-G-1920-r0', 'F-A-M-1920-r0', 'F-A-L-1920-r0']
ORIGINAL_ERROR = "; audit ValueError('incomplete L4 log/session conservation')"
V2_SHA = '292cbafde4460b1af038e909cf82b2d4c6d804022494dc3c9d5286705b698f0e'
REWORK2 = 'docs/leader/reworks/V0.6/S1-rework-002.md'
PREFIX2 = PREFIX + ['F-A-B-1920-r0', 'F-A-M-3840-r0', 'F-A-L-3840-r0',
                    'F-A-B-3840-r0', 'F-A-G-3840-r0', 'F-S-B-240-r0', 'F-S-G-240-r0',
                    'F-S-M-240-r0', 'F-S-L-240-r0', 'F-S-G-480-r0', 'F-S-M-480-r0']
SECOND_ERROR = "; monitor RuntimeError(\"PermissionError(13, 'Permission denied')\")"
V3_SHA = '66b57cde541599fcc8e2666b618d7f5910913a7b9c025a6319cac5db4d026198'
REWORK3 = 'docs/leader/reworks/V0.6/S1-rework-003.md'
PREFIX3 = PREFIX2 + ['F-S-L-480-r0', 'F-S-B-480-r0', 'F-S-M-600-r0', 'F-S-L-600-r0',
                    'F-S-B-600-r0', 'F-S-G-600-r0', 'F-A-G-960-r1', 'F-A-M-960-r1',
                    'F-A-L-960-r1', 'F-A-B-960-r1', 'F-A-M-1920-r1', 'F-A-L-1920-r1',
                    'F-A-B-1920-r1', 'F-A-G-1920-r1', 'F-A-L-3840-r1']
V4_SHA = 'a559456acd9851c51a14b877fcfb42bdfe829c144bd4c61efdf71ebc245fe692'
REWORK4 = 'docs/leader/reworks/V0.6/S1-rework-004.md'
REVIEWER_PROFILE = 'reviewer-v4-prefix33'
REVIEWER_PLAN_SHA = '18a4b89ef89cdeb29beff54e2fe07dbfb60532fc713c37f21feefe1e47ca407b'
REVIEWER_PROVENANCE_SHA = '845b91cfb06b210e538acb0abcbf5b76e5126f83ffa6f3e738c962ed5215c601'
REVIEWER_EVENT_SHA = '0b578739693d88020d038a0b385e9700131369f079aa364d9743ecb26b6f86ff'
REVIEWER_RESULT_SHA = '079695aa476d0d9c3d5f1726f85ff11a3375e97d35b9e44fa2795838c4202777'
REVIEWER_ERROR = '; monitor RuntimeError("FileNotFoundError(2, \'No such file or directory\')")'
ROOT = Path(__file__).resolve().parents[2]


def profile(second=False, third=False, reviewer=False):
    if reviewer:
        return V4_SHA, REWORK4, PREFIX3, 'r5'
    if third:
        return V3_SHA, REWORK3, PREFIX3, 'r4'
    return (V2_SHA, REWORK2, PREFIX2, 'r3') if second else (V1_SHA, REWORK, PREFIX, 'r2')


def check_prefix(data, second=False, third=False, reviewer=False):
    expected_ids = PREFIX3 if third or reviewer else (PREFIX2 if second else PREFIX)
    if any(c['state'] == 'running' for c in data['cells']) or any(a.get('state') == 'running' for a in data.get('auxiliary', [])):
        raise ValueError('in-flight reservation')
    formal = [c for c in data['cells'] if c['kind'] == 'formal']
    if [c['id'] for c in formal] != expected_ids:
        raise ValueError('rework requires the exact approved prefix')
    failed_indices = (32,) if reviewer else ((6, 17, 32) if third else ((6, 17) if second else (6,)))
    if [c['state'] for c in formal] != [('failed' if i in failed_indices else 'complete') for i in range(len(expected_ids))]:
        raise ValueError('unexpected original prefix states')
    return formal


def fingerprints(folder):
    return {str(p.relative_to(folder)): digest(p.read_bytes()) for p in sorted(folder.rglob('*')) if p.is_file()}


def check_fingerprints(folder, expected):
    if fingerprints(folder) != expected:
        raise ValueError('original cell inputs changed: ' + str(folder))


def tool_hashes():
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in (ROOT / 'tests/capacity').glob('*.py')}


def check_parent_manifest(manifest):
    continuation = manifest['continuation']
    reviewer = continuation['rework'] == REWORK4
    if reviewer and continuation.get('profile') != REVIEWER_PROFILE:
        raise ValueError('Reviewer continuation profile mismatch')
    third = continuation['rework'] == REWORK3
    second = third or continuation['rework'] == REWORK2
    parent_sha, rework, prefix_ids, version = profile(second, third, reviewer)
    if continuation['rework'] != rework or continuation['parent_manifest_sha256'] != parent_sha or continuation['prefix_ids'] != prefix_ids:
        raise ValueError('not approved rework-001 continuation')
    if not (ROOT / rework).read_text().splitlines()[2].startswith('Approved'):
        raise ValueError('rework is not approved')
    path = ROOT / continuation['parent_manifest_path']
    raw = path.read_bytes()
    if digest(raw) != parent_sha:
        raise ValueError('parent manifest bytes changed')
    old = json.loads(raw)
    if second or reviewer:
        check_parent_manifest(old)
    for key in ['configuration', 'workloads', 'cells', 'semantics', 'resources', 'limits', 'selection', 'environment', 'sources']:
        if manifest[key] != old[key]:
            raise ValueError('continuation changed frozen inputs: ' + key)
    return old


def check_processes(processes, spec, manifest):
    expected = {f'backend-{i}' for i in range(manifest['configuration']['backends'])}
    expected.update(f'generator-{i}' for i in range(manifest['workloads'][spec['workload']]['workers']))
    gateways = 0 if spec['path'] == 'B' else (1 if spec['path'] == 'G' else 2)
    expected.update(f'gateway-{i}' for i in range(gateways))
    if spec['path'] == 'L':
        expected.add('l4lb')
    if len(processes) != len(expected) or {p.get('name') for p in processes} != expected:
        raise ValueError('original owned process set differs from frozen topology')
    if len({p.get('pid') for p in processes}) != len(expected) or any(p.get('returncode') != 0 or p.get('capture_error') for p in processes):
        raise ValueError('original process/capture failure cannot resume')


def old_state(args, parent_path, second=False, third=False, reviewer=False):
    parent_sha, rework, prefix_ids, version = profile(second, third, reviewer)
    raw = Path(parent_path).read_bytes()
    if digest(raw) != parent_sha:
        raise ValueError('original frozen manifest bytes changed')
    old = json.loads(raw)
    if old['status'] != 'Frozen' or [c['id'] for c in old['cells'][:len(prefix_ids)]] != prefix_ids or len(old['cells']) != 72:
        raise ValueError('original plan identity')
    ledger = Ledger(args.output)
    prefix = check_prefix(ledger.data, second, third, reviewer)
    plan = json.loads((Path(args.output) / 'formal-plan.json').read_text())
    provenance = json.loads((Path(args.output) / 'formal-provenance.json').read_text())
    initial = old
    if reviewer:
        check_parent_manifest(old)
        if (digest((Path(args.output) / 'formal-plan.json').read_bytes()) != REVIEWER_PLAN_SHA
                or digest((Path(args.output) / 'formal-provenance.json').read_bytes()) != REVIEWER_PROVENANCE_SHA):
            raise ValueError('not the approved independent Reviewer run')
    else:
        while 'continuation' in initial:
            initial = check_parent_manifest(initial)
    if plan != initial or provenance['manifest_sha256'] != (V4_SHA if reviewer else V1_SHA):
        raise ValueError('original provenance mismatch')
    if second:
        resumed = json.loads((Path(args.output) / 'formal-resume-r2-provenance.json').read_text())
        if resumed['manifest_sha256'] != V2_SHA or resumed['parent_manifest_sha256'] != V1_SHA or resumed['binaries'] != provenance['binaries']:
            raise ValueError('first continuation provenance mismatch')
    if third:
        resumed = json.loads((Path(args.output) / 'formal-resume-r3-provenance.json').read_text())
        if resumed['manifest_sha256'] != V3_SHA or resumed['parent_manifest_sha256'] != V2_SHA or resumed['binaries'] != provenance['binaries']:
            raise ValueError('second continuation provenance mismatch')
    for name in ['gateway', 'l4lb']:
        if digest(Path(getattr(args, name)).read_bytes()) != provenance['binaries'][name]:
            raise ValueError('binary changed: ' + name)
    verify_sources(old)
    for index, entry in enumerate(prefix):
        if any(entry['spec'].get(k) != v for k, v in old['cells'][index].items()):
            raise ValueError('ledger specification changed')
        folder = Path(args.output) / entry['id']
        disk_spec = json.loads((folder / 'spec.json').read_text())
        expected_spec = old['cells'][index] | {
            'workers': old['workloads'][disk_spec['workload']]['workers'],
            'slots': old['configuration']['slots'], 'capacity': old['configuration']['capacity'],
            'stream_aggregate_bytes': old['configuration']['stream_mib'] * MIB,
            'backend_workers': old['configuration']['backends'], 'reuse': old['configuration']['reuse'],
            'nodelay': old['configuration']['nodelay'], 'sample_interval': old['configuration']['sample_interval']}
        if any(disk_spec.get(k) != value for k, value in expected_spec.items()):
            raise ValueError('actual cell spec differs from frozen manifest')
        result = json.loads((folder / 'result.json').read_text())
        expected = (REVIEWER_ERROR if index == 32 else None) if reviewer else (ORIGINAL_ERROR if index == 6 else (SECOND_ERROR if (second and index == 17) or (third and index == 32) else None))
        if result['error'] != expected:
            raise ValueError('only the specified original audit failure is recoverable')
        if not (folder / 'drain.json').is_file():
            raise ValueError('original resource drain missing')
        processes = json.loads((folder / 'processes.json').read_text())
        check_processes(processes, old['cells'][index], old)
    if reviewer:
        reviewer_exit_error_proof(Path(args.output) / PREFIX3[-1])
    return old, ledger, provenance


def closing_sample_proof(folder):
    spec = json.loads((folder / 'spec.json').read_text())
    samples = list(rows(folder, 'resources'))
    end = spec['measure_start'] + int(spec['duration'] * 1e9)
    last_close = max(dict(zip(COLUMNS, row))['closed'] for row in rows(folder, 'client'))
    lower_bound = samples[-1]['end'] + int(spec['sample_interval'] * 1e9)
    if spec['id'] != PREFIX2[-1] or spec['sample_interval'] != .1 or lower_bound <= max(end, last_close):
        raise ValueError('specific post-window timing proof no longer holds')
    return {'formal_end_ns': end, 'last_complete_sample_end_ns': samples[-1]['end'],
            'next_sampling_round_lower_bound_ns': lower_bound, 'last_client_close_ns': last_close,
            'note': 'post-window closing sample error; exact PID/operation unrecorded, no inferred root cause'}


def explicit_exit_error_proof(folder):
    spec = json.loads((folder / 'spec.json').read_text())
    events = list(rows(folder, 'monitor-events'))
    end = spec['measure_start'] + int(spec['duration'] * 1e9)
    last_close = max(dict(zip(COLUMNS, row))['closed'] for row in rows(folder, 'client'))
    if spec['id'] != PREFIX3[-1] or len(events) != 1:
        raise ValueError('unexpected third failure evidence')
    event = events[0]
    if (event['pid'] != 158143 or event['name'] != 'generator-0' or event['phase'] != 'request-drain'
            or event['exception_type'] != 'PermissionError' or event['action'] != 'fatal'
            or event['returncode'] is not None or '/proc/158143/fd' not in event['traceback']
            or event['time_ns'] < max(end, last_close)):
        raise ValueError('third failure is not the explicitly approved post-window event')
    return {'formal_end_ns': end, 'last_client_close_ns': last_close, 'failure_event': event,
            'note': 'post-window failure retained; original poll lacked exit confirmation; no request recategorized'}


def reviewer_exit_error_proof(folder):
    if (digest((folder / 'monitor-events-0000.jsonl').read_bytes()) != REVIEWER_EVENT_SHA
            or digest((folder / 'result.json').read_bytes()) != REVIEWER_RESULT_SHA):
        raise ValueError('Reviewer original error fingerprint changed')
    spec = json.loads((folder / 'spec.json').read_text())
    events = list(rows(folder, 'monitor-events'))
    end = spec['measure_start'] + int(spec['duration'] * 1e9)
    last_close = max(dict(zip(COLUMNS, row))['closed'] for row in rows(folder, 'client'))
    if spec['id'] != PREFIX3[-1] or len(events) != 1:
        raise ValueError('unexpected Reviewer failure events')
    event = events[0]
    if (event['pid'] != 166168 or event['name'] != 'l4lb' or event['phase'] != 'cleanup'
            or event['exception_type'] != 'FileNotFoundError' or event['action'] != 'fatal'
            or event['returncode'] is not None or event['initial_returncode'] is not None
            or event['exit_wait_start_ns'] is not None or '/proc/166168/stat' not in event['traceback']
            or event['time_ns'] < max(end, last_close)):
        raise ValueError('Reviewer failure is not the approved post-window ENOENT')
    return {'formal_end_ns': end, 'last_client_close_ns': last_close, 'failure_event': event,
            'note': 'Reviewer original post-window ENOENT retained; all request outcomes unchanged'}


def derive(args):
    parent_hash = digest(Path(args.parent).read_bytes())
    reviewer = parent_hash == V4_SHA
    if reviewer and getattr(args, 'profile', None) != REVIEWER_PROFILE:
        raise ValueError('explicit Reviewer derive profile required')
    if not reviewer and getattr(args, 'profile', None) is not None:
        raise ValueError('profile does not match parent')
    third = parent_hash == V3_SHA
    second = third or parent_hash == V2_SHA
    parent_sha, rework, prefix_ids, version = profile(second, third, reviewer)
    old, ledger, provenance = old_state(args, args.parent, second, third, reviewer)
    destination = Path(args.output) / ('formal-reaudit-' + version)
    destination.mkdir(exist_ok=False)
    used = sum(p.stat().st_size for p in ledger.budget_root.rglob('*') if p.is_file())
    if used + 2*MIB + 16*MIB > 2*1024*MIB or ledger.data['active_seconds'] + 45 > 5400:
        raise RuntimeError('derived-audit budget')
    ledger_snapshot = destination / 'ledger-before.json'
    ledger_snapshot.write_bytes(ledger.path.read_bytes())
    entry = {'kind': ('rework-004-derived-audit' if reviewer else 'rework-003-derived-audit' if third else ('rework-002-derived-audit' if second else 'rework-001-derived-audit')), 'state': 'running', 'reserved_seconds': 45}
    ledger.data.setdefault('auxiliary', []).append(entry)
    ledger.data['active_seconds'] += 45
    ledger.save()
    start = time.monotonic()
    outputs = []
    try:
        for identity in prefix_ids:
            folder = Path(args.output) / identity
            inputs = fingerprints(folder)
            result = audit(folder)
            if reviewer or second or identity != PREFIX[-1]:
                previous_path = Path(args.output) / 'formal-reaudit-r2' / (identity + '.json') if second and identity == PREFIX[-1] else folder / 'result.json'
                previous = json.loads(previous_path.read_text())['metrics']
                if result != {k: v for k, v in previous.items() if k not in ('resources', 'drained')}:
                    raise ValueError('previous successful metrics changed')
            if result['corruption_all_phases']:
                raise ValueError('original correctness corruption is not recoverable')
            spec = json.loads((folder / 'spec.json').read_text())
            result['resources'] = summarize(folder, spec['measure_start'], spec['duration'])
            result['drained'] = True
            artifact = destination / (identity + '.json')
            write(artifact, {'classification_version': ('unified-exit-reviewer-r5' if reviewer else 'bounded-exit-r4' if third else ('closing-sample-r3' if second else 'L4-full-reason-r2')),
                  'sampling_coverage': (reviewer_exit_error_proof(folder) if reviewer and identity == PREFIX3[-1] else explicit_exit_error_proof(folder) if third and identity == PREFIX3[-1] else
                                        (closing_sample_proof(folder) if second and identity == PREFIX2[-1] else None)), 'raw_cell': str(folder),
                  'input_sha256': inputs, 'metrics': result, 'original_result_sha256': inputs['result.json']})
            outputs.append({'id': identity, 'path': str(artifact), 'sha256': digest(artifact.read_bytes()),
                            'input_sha256': inputs, 'original_result_sha256': inputs['result.json']})
        write(destination / 'summary.json', {'profile': REVIEWER_PROFILE if reviewer else None, 'rework': rework, 'parent_manifest_sha256': parent_sha,
              'prefix_ids': prefix_ids, 'derived': outputs, 'tools': tool_hashes(), 'binaries': provenance['binaries'],
              'ledger_snapshot': str(ledger_snapshot), 'ledger_snapshot_sha256': digest(ledger_snapshot.read_bytes()),
              'original_provenance_sha256': digest((Path(args.output) / 'formal-provenance.json').read_bytes()),
              'original_plan_sha256': digest((Path(args.output) / 'formal-plan.json').read_bytes()),
              'previous_resume_provenance_sha256': digest((Path(args.output) / 'formal-resume-r2-provenance.json').read_bytes()) if second else None,
              'second_resume_provenance_sha256': digest((Path(args.output) / 'formal-resume-r3-provenance.json').read_bytes()) if third else None})
        entry['state'] = 'complete'
    except BaseException:
        entry['state'] = 'failed'
        raise
    finally:
        elapsed = time.monotonic() - start
        entry['elapsed_seconds'] = elapsed
        ledger.data['active_seconds'] -= max(0, 45-elapsed)
        ledger.save()
    print(json.dumps({'summary': str(destination / 'summary.json'), 'sha256': digest((destination / 'summary.json').read_bytes())}))


def prepare_resume(args):
    raw = Path(args.manifest).read_bytes()
    manifest = validate(json.loads(raw))
    continuation = manifest['continuation']
    reviewer = continuation['rework'] == REWORK4
    if reviewer and continuation.get('profile') != REVIEWER_PROFILE:
        raise ValueError('Reviewer continuation profile mismatch')
    third = continuation['rework'] == REWORK3
    second = third or continuation['rework'] == REWORK2
    parent_sha, rework, prefix_ids, version = profile(second, third, reviewer)
    check_parent_manifest(manifest)
    old, ledger, provenance = old_state(args, ROOT / continuation['parent_manifest_path'], second, third, reviewer)
    reference = continuation['derived_summary']
    summary_path = Path(reference['path'])
    if not summary_path.is_absolute():
        summary_path = ROOT / summary_path
    if digest(summary_path.read_bytes()) != reference['sha256']:
        raise ValueError('derived summary changed')
    summary = json.loads(summary_path.read_text())
    if reviewer and summary.get('profile') != REVIEWER_PROFILE:
        raise ValueError('derived Reviewer profile mismatch')
    if summary['tools'] != manifest['tools'] or summary['parent_manifest_sha256'] != parent_sha or summary['prefix_ids'] != prefix_ids or summary['binaries'] != provenance['binaries']:
        raise ValueError('derived provenance mismatch')
    snapshot = Path(summary['ledger_snapshot'])
    if not snapshot.is_absolute():
        snapshot = ROOT / snapshot
    if digest(snapshot.read_bytes()) != summary['ledger_snapshot_sha256']:
        raise ValueError('original ledger snapshot changed')
    before = json.loads(snapshot.read_text())
    if ledger.data['cells'] != before['cells'] or ledger.data['active_seconds'] < before['active_seconds']:
        raise ValueError('original cumulative ledger changed')
    for name, key in [('formal-plan.json', 'original_plan_sha256'), ('formal-provenance.json', 'original_provenance_sha256')]:
        if digest((Path(args.output) / name).read_bytes()) != summary[key]:
            raise ValueError('original provenance file changed')
    if second and digest((Path(args.output) / 'formal-resume-r2-provenance.json').read_bytes()) != summary['previous_resume_provenance_sha256']:
        raise ValueError('first resume provenance changed')
    if third and digest((Path(args.output) / 'formal-resume-r3-provenance.json').read_bytes()) != summary['second_resume_provenance_sha256']:
        raise ValueError('second resume provenance changed')
    if [item['id'] for item in summary['derived']] != prefix_ids:
        raise ValueError('derived prefix mismatch')
    for item in summary['derived']:
        path = Path(item['path'])
        if not path.is_absolute():
            path = ROOT / path
        if digest(path.read_bytes()) != item['sha256']:
            raise ValueError('derived artifact changed')
        derived = json.loads(path.read_text())
        folder = Path(args.output) / item['id']
        if item['input_sha256'] != derived['input_sha256'] or item['original_result_sha256'] != derived['original_result_sha256']:
            raise ValueError('derived input binding mismatch')
        check_fingerprints(folder, derived['input_sha256'])
        if second and item['id'] == PREFIX2[-1] and derived['sampling_coverage'] != closing_sample_proof(folder):
            raise ValueError('post-window timing proof changed')
        if reviewer and item['id'] == PREFIX3[-1] and derived['sampling_coverage'] != reviewer_exit_error_proof(folder):
            raise ValueError('Reviewer post-window evidence changed')
        if third and item['id'] == PREFIX3[-1] and derived['sampling_coverage'] != explicit_exit_error_proof(folder):
            raise ValueError('third post-window evidence changed')
        if audit(folder) != {k: v for k, v in derived['metrics'].items() if k not in ('resources', 'drained')}:
            raise ValueError('derived metrics differ on independent recomputation')
    remaining = manifest['cells'][len(prefix_ids):]
    if any((Path(args.output) / c['id']).exists() for c in remaining):
        raise ValueError('remaining output already exists')
    used = sum(p.stat().st_size for p in ledger.budget_root.rglob('*') if p.is_file())
    worst = worst_bytes(manifest | {'cells': remaining})
    diagnostic_reserve = (12 - sum(c['kind'] == 'diagnostic' for c in ledger.data['cells'])) * 7876608
    if used + worst + diagnostic_reserve + 16*MIB > 2*1024*MIB:
        raise RuntimeError('remaining matrix evidence budget')
    if len(ledger.data['cells']) + len(remaining) > 120 or ledger.data['active_seconds'] + len(remaining)*45 > 5400:
        raise RuntimeError('remaining matrix activity/cell budget')
    write(Path(args.output) / ('formal-resume-' + version + '-provenance.json'), {'manifest_path': str(Path(args.manifest).resolve()),
          'manifest_sha256': digest(raw), 'parent_manifest_sha256': parent_sha, 'derived_summary_sha256': reference['sha256'],
          'remaining_ids': [c['id'] for c in remaining], 'worst_remaining_bytes': worst, 'used_before': used,
          'remaining_diagnostic_reservation': diagnostic_reserve, 'binaries': provenance['binaries']})
    return manifest, remaining


def run(args):
    ledger = Ledger(args.output)
    if ledger.data['active_seconds'] + 45 > 5400:
        raise RuntimeError('preflight activity budget')
    start = time.monotonic()
    state = 'failed'
    old_alarm = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('45s preflight bound')))
    signal.setitimer(signal.ITIMER_REAL, 45)
    try:
        manifest, remaining = prepare_resume(args)
        state = 'complete'
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_alarm)
        elapsed = time.monotonic() - start
        ledger = Ledger(args.output)
        ledger.data['active_seconds'] += elapsed
        ledger.data.setdefault('auxiliary', []).append({'kind': 'bounded-resume-preflight', 'state': state, 'elapsed_seconds': elapsed})
        ledger.save()
    if ledger.data['active_seconds'] + len(remaining)*45 > 5400:
        raise RuntimeError('remaining activity after charged preflight')
    from Run import cell
    for spec in remaining:
        options = SimpleNamespace(**vars(args))
        for key, value in manifest['configuration'].items():
            setattr(options, key, value)
        options.workers = manifest['workloads'][spec['workload']]['workers']
        options.fault = 'none'
        result = cell(spec, options)
        print(json.dumps({k: result[k] for k in ['id', 'good_fraction', 'generator_valid', 'outcomes']}), flush=True)
        if result['corruption_all_phases']:
            raise RuntimeError('formal correctness corruption: ' + result['id'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--l4lb', required=True)
    parser.add_argument('--parent', required=True)
    parser.add_argument('--profile', choices=[REVIEWER_PROFILE])
    derive(parser.parse_args())
