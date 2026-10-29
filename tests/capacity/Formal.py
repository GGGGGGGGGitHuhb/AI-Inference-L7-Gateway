"""Strict frozen-matrix validation and execution; no adaptive formal rate selection."""
import itertools
import json
import os
from pathlib import Path
from types import SimpleNamespace
from Common import digest, MIB, write
from Runtime import Ledger


def validate(manifest):
    if manifest.get('schema_version') != 1 or manifest.get('status') != 'Frozen':
        raise ValueError('manifest must be schema 1 and Frozen')
    config = manifest['configuration']
    if set(config) != {'slots', 'backends', 'capacity', 'stream_mib', 'reuse', 'nodelay', 'sample_interval'}:
        raise ValueError('configuration keys')
    if config != {'slots': 128, 'backends': 1, 'capacity': 32, 'stream_mib': 4, 'reuse': False, 'nodelay': 1, 'sample_interval': .1}:
        raise ValueError('unapproved primary configuration')
    if set(manifest['workloads']) != {'A', 'S'}:
        raise ValueError('workloads')
    expected = set()
    for workload, details in manifest['workloads'].items():
        if set(details) != {'rates', 'workers'} or details['workers'] not in (1, 2):
            raise ValueError('workload configuration')
        rates = details['rates']
        if len(rates) != 3 or rates != sorted(set(rates)) or any(not isinstance(r, int) or not 1 <= r <= 3840 for r in rates):
            raise ValueError('three distinct bounded rates required')
        expected.update(itertools.product([workload], rates, range(3), 'BGML'))
    cells = manifest['cells']
    actual, ids = set(), set()
    if len(cells) != 72:
        raise ValueError('formal matrix must have 72 cells')
    for spec in cells:
        if set(spec) != {'id', 'kind', 'path', 'workload', 'rate', 'repeat', 'warm', 'duration'}:
            raise ValueError('cell keys')
        if spec['kind'] != 'formal' or spec['warm'] != 3 or spec['duration'] != 20:
            raise ValueError('formal timing/kind')
        if not spec['id'] or len(spec['id']) > 48 or not all(c.isascii() and (c.isalnum() or c in '-_') for c in spec['id']):
            raise ValueError('bounded ASCII ID')
        combination = spec['workload'], spec['rate'], spec['repeat'], spec['path']
        if spec['id'] in ids or combination in actual:
            raise ValueError('duplicate formal ID/combination')
        ids.add(spec['id'])
        actual.add(combination)
    if actual != expected:
        raise ValueError('incomplete formal matrix')
    for workload, details in manifest['workloads'].items():
        for rate_index, rate in enumerate(details['rates']):
            for repeat in range(3):
                offset = (rate_index + repeat) % 4
                order = 'BGML'[offset:] + 'BGML'[:offset]
                observed = ''.join(c['path'] for c in cells if c['workload'] == workload and c['rate'] == rate and c['repeat'] == repeat)
                if observed != order:
                    raise ValueError('formal topology rotation')
    required = {
        'semantics': {'A_slo_ms': 100, 'S_slo_ms': 250, 'S_first_body_ms': 50,
                      'slo_fraction': .99, 'not_sent_fraction_max': .01, 'dispatch_lag_p95_ms_max': 5,
                      'quantile_min_success': {'p50': 20, 'p95': 100, 'p99': 1000},
                      'generator_control_sensitive_relative_change': .1, 'busy_core_flag': .85},
        'resources': {'aggregate_gateway_connections': 32, 'aggregate_gateway_admission': 32,
                      'aggregate_gateway_reserved_bytes': 536870912, 'aggregate_stream_bytes': 4194304,
                      'per_stream_bytes': 262144, 'backend_workers': 1, 'slots_are_aggregate': True},
        'limits': {'per_role_cells': 120, 'E1': 28, 'E2': 8, 'formal': 72, 'diagnostic': 12,
                   'active_seconds': 5400, 'cell_active_seconds': 45, 'request_seconds': 5,
                   'drain_seconds': 5, 'cleanup_term_seconds': 5, 'evidence_bytes': 2147483648,
                   'single_file_bytes': 1048576, 'rss_bytes': 1073741824, 'fds': 2048}}
    for section, fields in required.items():
        for key, value in fields.items():
            if manifest.get(section, {}).get(key) != value:
                raise ValueError('manifest differs from implementation: ' + section + '.' + key)
    if manifest['resources'].get('affinity') != sorted(os.sched_getaffinity(0)):
        raise ValueError('inherited CPU affinity differs from manifest')
    tools = manifest.get('tools')
    if not isinstance(tools, dict) or not tools:
        raise ValueError('frozen tool identities required')
    repo = Path(__file__).resolve().parents[2]
    expected_tools = {str(p.relative_to(repo)) for p in (repo / 'tests/capacity').glob('*.py')}
    if set(tools) != expected_tools:
        raise ValueError('complete tool file set required')
    for path, sha in tools.items():
        if digest((repo / path).read_bytes()) != sha:
            raise ValueError('tool hash changed: ' + path)
    references = list(manifest.get('selection', {}).get('calibration', [])) + [manifest.get('environment', {}), manifest.get('sources', {})]
    if len(references) < 3 or any(not ref.get('path') or not ref.get('sha256') for ref in references):
        raise ValueError('selection/environment/source evidence required')
    def nested_refs(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                yield value
            for item in value.values():
                yield from nested_refs(item)
        elif isinstance(value, list):
            for item in value:
                yield from nested_refs(item)
    references = list(nested_refs(manifest['selection'])) + [manifest['environment'], manifest['sources']]
    for ref in references:
        path = Path(ref['path'])
        if not path.is_absolute():
            path = repo / path
        if digest(path.read_bytes()) != ref['sha256']:
            raise ValueError('referenced evidence changed: ' + ref['path'])
    if 'continuation' in manifest:
        from Resume import check_parent_manifest
        check_parent_manifest(manifest)
    return manifest


def worst_bytes(manifest):
    return sum(int(c['rate'] * (c['warm'] + c['duration'])) *
               (512 + 192 * manifest['configuration']['backends'] + (256 if c['path'] == 'L' else 0)) + 3*MIB
               for c in manifest['cells'])


def verify_sources(manifest):
    repo = Path(__file__).resolve().parents[2]
    reference = Path(manifest['sources']['path'])
    if not reference.is_absolute():
        reference = repo / reference
    sources = json.loads(reference.read_text())
    for name, expected_root in [('gateway', repo), ('l4lb', Path('/home/power/projects/L4-LoadBalancer-withXDP'))]:
        if Path(sources[name]['root']) != expected_root:
            raise ValueError('source root changed')
        for relative, sha in sources[name]['files'].items():
            if digest((expected_root / relative).read_bytes()) != sha:
                raise ValueError('actual source changed: ' + name + '/' + relative)


def run(args):
    from Run import cell
    if not args.manifest:
        raise ValueError('--manifest required')
    raw = Path(args.manifest).read_bytes()
    manifest = validate(json.loads(raw))
    verify_sources(manifest)
    ledger = Ledger(args.output)
    used = sum(p.stat().st_size for p in ledger.budget_root.rglob('*') if p.is_file())
    reservation = worst_bytes(manifest)
    diagnostic_reserve = (12 - sum(c['kind'] == 'diagnostic' for c in ledger.data['cells'])) * 7876608
    if used + reservation + diagnostic_reserve + 16*MIB > 2*1024*MIB:
        raise RuntimeError('entire frozen matrix does not fit remaining evidence budget')
    if len(ledger.data['cells']) + 72 > 120 or ledger.data['active_seconds'] + 72*45 > 5400:
        raise RuntimeError('entire matrix does not fit remaining cell/time budget')
    if any(c['kind'] == 'formal' for c in ledger.data['cells']):
        raise RuntimeError('formal rerun/resume requires explicit new coordination')
    write(Path(args.output) / 'formal-plan.json', manifest)
    write(Path(args.output) / 'formal-provenance.json', {'manifest_path': str(Path(args.manifest).resolve()),
          'manifest_sha256': digest(raw), 'worst_matrix_bytes': reservation, 'used_before': used, 'remaining_diagnostic_reservation': diagnostic_reserve,
          'binaries': {name: digest(Path(getattr(args, name)).read_bytes()) for name in ['gateway', 'l4lb']}})
    for spec in manifest['cells']:
        options = SimpleNamespace(**vars(args))
        for key, value in manifest['configuration'].items():
            setattr(options, key, value)
        options.workers = manifest['workloads'][spec['workload']]['workers']
        options.fault = 'none'
        result = cell(spec, options)
        print(json.dumps({k: result[k] for k in ['id', 'good_fraction', 'generator_valid', 'outcomes']}), flush=True)
        if result['corruption_all_phases']:
            raise RuntimeError('formal correctness corruption: ' + result['id'])
