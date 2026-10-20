"""Fixed 28-attempt CPU compatibility matrix. No model acquisition, soak, or tuning."""
import json
import os
from pathlib import Path
import signal
import tarfile
import time

from Attempts import Attempt
from Common import (ROOT, Host, OwnedProcess, ResourceSampler, append, body, check, configuration,
                    free_port, get_json, process_stats, save, sha, summary, wait_for, cleanup_all)

SERVER_SHA = '45938e6847d403ff6486cd692de9441aeb330e971a5dd8ad6f695b60bae2d081'
MODEL_SHA = '74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db'
ARCHIVE_SHA = '9cbbff430e4f2d976135d68d998576530cc1bd87babe1d71db4886d8a79e7b2e'


def verify_identity(path, size, digest):
    check(Path(path).is_file(), 'missing asset: ' + str(path))
    check(Path(path).stat().st_size == size and sha(path) == digest, 'asset identity: ' + str(path))


def verify_assets(assets, output):
    import hashlib
    assets = Path(assets).resolve()
    executable = assets / 'backend/llama-b7481/llama-server'
    model = assets / 'models/qwen2.5-0.5b-instruct-q4_k_m.gguf'
    archive = assets / 'downloads/llama-b7481-bin-ubuntu-x64.tar.gz'
    verify_identity(archive, 19144446, ARCHIVE_SHA)
    verify_identity(model, 491400032, MODEL_SHA)
    check(sha(executable) == SERVER_SHA, 'server identity')
    members = {}
    with tarfile.open(archive, 'r:gz') as source:
        for member in source:
            if member.isfile() and ('.so' in member.name or 'LICENSE' in member.name or member.name.endswith('/llama-server')):
                data = source.extractfile(member).read()
                deployed = executable.parent / Path(member.name).name
                check(deployed.is_file(), 'missing library/license')
                digest = hashlib.sha256(data).hexdigest()
                check(sha(deployed) == digest, 'deployed library/license differs from fixed archive')
                members[str(deployed)] = digest
    license_path = assets / 'models/LICENSE'
    text = license_path.read_text()
    check('Apache License' in text and 'Version 2.0' in text, 'Qwen license')
    save(Path(output) / 'assets.json', {'server': str(executable), 'server_sha256': sha(executable),
        'model': str(model), 'model_sha256': sha(model), 'model_bytes': model.stat().st_size,
        'model_license': str(license_path), 'model_license_sha256': sha(license_path),
        'archive_sha256': sha(archive), 'archive_verified_members': members})
    return executable, model


class CpuBackend:
    def __init__(self, executable, model, output, index):
        self.port = free_port()
        self.owned = OwnedProcess([executable, '-m', model, '--host', '127.0.0.1', '--port', self.port,
             '--alias', 'gateway-qwen', '--ctx-size', 2048, '--parallel', 1, '--threads', 2,
             '--threads-batch', 2, '--n-gpu-layers', 0, '--metrics'],
             Path(output) / f'backend-{index}.log', Path(output) / 'processes.jsonl')
        try:
            def ready():
                check(self.owned.process.poll() is None, 'backend startup failed')
                stats = process_stats(self.owned.process.pid)
                check(stats and stats['rss'] <= 2 * 1024**3, 'backend startup RSS')
                try:
                    return get_json(self.port, '/health').get('status') == 'ok'
                except (OSError, AssertionError):
                    return False
            wait_for(ready, 120, 'backend startup')
        except BaseException:
            self.owned.stop()
            raise


class Matrix:
    def __init__(self, args, output):
        self.args, self.output = args, Path(output)
        self.backends, self.attempts = [], []
        self.host = None
        self.sampler = None
        self.official = None
        self.start_time = time.monotonic()

    def start(self, identity, port=None, stream=True, long=False, slow=False, half=False,
              expected='success', cohort='formal'):
        check(time.monotonic() - self.start_time < 1800, 'real fixed run guard')
        attempt = Attempt(identity, identity.split('-')[0], port or self.host.port,
                          body('gateway-qwen', stream, long), self.output, expected,
                          timeout=155, slow=slow, half=half, cohort=cohort)
        self.attempts.append(attempt)
        return attempt

    def active_content(self, attempt):
        check(attempt.first.wait(150), 'real first content deadline')
        row = wait_for(lambda: self.host.active(attempt), .5, 'real active at content')
        append(self.output / 'events.jsonl', {'id': attempt.row['id'], 'event': 'first-content-active',
                                            'time': time.monotonic(), 'record': row, 'state': self.host.state()})
        return row

    def official_smoke(self):
        config = configuration([b.port for b in self.backends], True)
        config['listen_port'] = free_port()
        path = self.output / 'official-config.json'; save(path, config)
        log = self.output / 'official.log'
        self.official = OwnedProcess([self.args.gateway, '--config', path], log, self.output / 'processes.jsonl')
        def ready():
            check(self.official.process.poll() is None, 'official startup failure')
            return 'READY ' in log.read_text()
        wait_for(ready, 5, 'official ready')
        self.start('R0-07', config['listen_port'], stream=False, cohort='official').join()
        self.start('R0-08', config['listen_port'], cohort='official').join()
        self.official.stop()
        check(self.official.process.returncode == 0, 'official normal exit')
        self.official = None

    def normal(self):
        for index in range(1, 9):
            self.start(f'R1-{index:02}', stream=index % 2 == 0).join()
        state = self.host.state()
        rows = [self.host.record(a) for a in self.attempts if a.row['group'] == 'R1']
        indices = [row['backend_index'] for row in rows]
        check(set(indices) == {0, 1} and all(indices[i] != indices[i-1] for i in range(1, 8)), 'actual RR order')
        append(self.output / 'events.jsonl', {'event': 'R1-routing', 'indices': indices, 'state': state})
        self.host.drain('R1-drained')

    def concurrent(self):
        first = self.start('R2-01', long=True, slow=True)
        second = self.start('R2-02', long=True)
        self.active_content(first); self.active_content(second)
        check(self.host.active(first) and self.host.active(second), 'two real active before queue requests')
        short = [self.start(f'R2-{index:02}') for index in range(3, 7)]
        for attempt in [first, second] + short:
            attempt.join()
        queued = [self.host.record(a) for a in short if self.host.record(a)['enqueued']]
        check(len(queued) >= 1, 'R2 actual queue coverage missing')
        append(self.output / 'events.jsonl', {'event': 'R2-actual-queue', 'count': len(queued), 'records': queued,
                                            'slow_pause_start': first.row['slow_pause_start'],
                                            'slow_pause_end': first.row['slow_pause_end'],
                                            'state': self.host.state()})
        self.host.drain('R2-drained')

    def cancellation(self):
        for number in (1, 3):
            attempt = self.start(f'R3-{number:02}', long=True, expected='cancelled')
            record = self.active_content(attempt)
            backend = self.backends[record['backend_index']]
            slots_before = get_json(backend.port, '/slots')
            link_path = Path('/proc') / str(self.host.owned.process.pid) / 'fd' / str(record['upstream_fd'])
            check(record['upstream_fd'] >= 0 and link_path.exists(), 'L2 live upstream fd required')
            inode = os.readlink(link_path)
            cancelled_at = time.monotonic()
            attempt.cancel_at_gate(); attempt.join()
            point = self.host.drain(f'R3-{number:02}-cancelled')
            check(point['time'] - cancelled_at < 5, 'L1 cancel <=5s')
            check(not link_path.exists() or os.readlink(link_path) != inode, 'L2 upstream fd retained')
            slots = []
            slot_deadline = time.monotonic() + 10
            while time.monotonic() < slot_deadline:
                slots = get_json(backend.port, '/slots')
                if all(not slot.get('is_processing', True) for slot in slots):
                    break
                time.sleep(.05)
            recovery = self.start(f'R3-{number+1:02}')
            recovery.join()
            append(self.output / 'cancellations.jsonl', {'id': attempt.row['id'], 'cancelled_at': cancelled_at,
                'before_record': record, 'before_slots': slots_before, 'L1_drained': point,
                'L2_upstream_inode': inode, 'L2_inode_released': True, 'after_slots': slots,
                'L3_slot_idle': bool(slots) and all(not slot.get('is_processing', True) for slot in slots),
                'recovery_id': recovery.row['id'], 'recovery_end': recovery.row['ended']})
            self.host.drain(f'R3-{number+1:02}-recovery')
        for index in (5, 6):
            self.start(f'R3-{index:02}', half=True).join()
        self.host.drain('R3-final')

    def run(self):
        try:
            executable, model = verify_assets(self.args.assets, self.output)
            for index in (1, 2):
                self.backends.append(CpuBackend(executable, model, self.output, index))
            self.host = Host(self.args.host, configuration([b.port for b in self.backends], True), self.output, 'real')
            self.sampler = ResourceSampler({'gateway': self.host.owned, **{f'backend{i}': b.owned for i, b in enumerate(self.backends)}}, self.output)
            for index, backend in enumerate(self.backends):
                self.start(f'R0-{index*2+1:02}', backend.port, stream=False, cohort='direct').join()
                self.start(f'R0-{index*2+2:02}', backend.port, cohort='direct').join()
            self.start('R0-05', cohort='warmup').join(); self.start('R0-06', cohort='warmup').join()
            baseline = self.host.drain('R0-warmup', check_rss=False)
            self.host.baseline['rss'] = baseline['rss']
            self.official_smoke()
            self.normal(); self.concurrent(); self.cancellation()
            expected = [f'{group}-{index:02}' for group, count in [('R0', 8), ('R1', 8), ('R2', 6), ('R3', 6)] for index in range(1, count+1)]
            rows = [a.row for a in self.attempts]
            result = summary(rows, expected)
            check(sum(row['outcome'] == 'success' for row in rows) == 26, 'real 26 successes')
            check(sum(row['outcome'] == 'cancelled' for row in rows) == 2, 'real two cancellations')
            save(self.output / 'summary.json', result)
        finally:
            actions = [(a.row['id'], a.stop) for a in self.attempts]
            if self.sampler:
                actions.append(('sampler', self.sampler.stop))
            if self.official:
                actions.append(('official', self.official.stop))
            if self.host:
                actions.append(('host', self.host.stop))
            actions.extend((f'backend-{i}', b.owned.stop) for i, b in enumerate(self.backends))
            cleanup_all(actions, self.output)
