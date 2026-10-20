#!/usr/bin/env python3
"""Explicit P1 run. No model/download is invoked by --check or ordinary CTest."""
import argparse
import json
import os
import pathlib
import platform
import signal
import subprocess
import sys
import time
from Client import PAYLOADS, digest, request_bytes
from Measure import batch, CANCEL, request_cancel

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1] / 'integration'))
from Support import Backend, Host, OwnedProcess, free_port, save, sha

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def schedule():
    cells = []
    for repeat in range(3):
        concurrencies = [1, 4, 16]
        concurrencies = concurrencies[repeat:] + concurrencies[:repeat]
        for group in ('A', 'B'):
            for scenario, concurrency in enumerate(concurrencies):
                paths = ['D', 'PC', 'PR'] if group == 'A' else ['D', 'P']
                shift = (repeat + scenario) % len(paths)
                for path in paths[shift:] + paths[:shift]:
                    cells.append(dict(group=group, repeat=repeat, concurrency=concurrency, path=path))
        for path in (['D', 'P'] if repeat % 2 == 0 else ['P', 'D']):
            cells.append(dict(group='C', repeat=repeat, concurrency=4, path=path))
        for scenario, (group, concurrency, stream) in enumerate([('R1', 1, False), ('R1', 1, True), ('R2', 2, True)]):
            for path in (['D', 'P'] if (repeat + scenario) % 2 == 0 else ['P', 'D']):
                cells.append(dict(group=group, repeat=repeat, concurrency=concurrency, path=path, stream=stream,
                                  block=f'r{repeat}-s{scenario}'))
    for index, cell in enumerate(cells):
        group = cell['group']
        cell.update(id=f'{index:02d}-{group}-r{cell["repeat"]}-c{cell["concurrency"]}-{cell["path"]}',
                    stream=cell.get('stream', group != 'A'),
                    warmup={'A': 50, 'B': 10, 'C': 4}.get(group, 2),
                    count={'A': 500, 'B': 100, 'C': 20}.get(group, 40),
                    guard={'A': 60, 'B': 90, 'C': 120}.get(group, 180),
                    timeout={'A': 5, 'B': 5, 'C': 10}.get(group, 150))
    return cells


def configuration(upstream, path):
    return {'listen_address': '127.0.0.1', 'listen_port': 0,
        'upstream_address': '127.0.0.1', 'upstream_port': upstream,
        'max_connections': 64, 'max_reserved_bytes': 1073741824,
        'upstream_pool': {'max_connections': 64, 'max_idle': 0 if path == 'PC' else 64,
                          'idle_timeout_ms': 300000},
        'stream_buffer': {'high_water_bytes': 196608, 'low_water_bytes': 65536,
                          'max_total_bytes': 16777216},
        'timeouts_ms': {'request': 10000, 'connect': 3000, 'upstream_write': 5000,
            'response': 120000, 'downstream_write': 10000, 'total': 150000,
            'shutdown': 3000, 'stream_idle': 30000}}


class Gateway:
    def __init__(self, args, backend_port, path, output, host=False):
        self.host = None
        self.output = output
        config = configuration(backend_port, path)
        if host:
            self.host = Host(args.host, config, output)
            self.owned, self.port = self.host.owned, self.host.port
            return
        save(output / 'gateway-config.json', config)
        log = output / 'gateway.log'
        self.owned = OwnedProcess([args.gateway, '--config', output / 'gateway-config.json'],
                                  log, output / 'processes.jsonl')
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                lines = log.read_text().splitlines()
                if lines and lines[0].startswith('READY '):
                    self.port = int(lines[0].rsplit(':', 1)[1])
                    return
                if self.owned.process.poll() is not None:
                    raise RuntimeError('gateway startup exit')
                time.sleep(.01)
            raise TimeoutError('gateway startup')
        except BaseException:
            self.owned.stop()
            raise

    def stop(self):
        try:
            if self.host:
                self.host.drain()
                self.host.refresh()
                save(self.output / 'host-maxima.json', self.host.maxima)
        finally:
            self.owned.stop()


def wait_ready(owned, log):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if 'READY' in log.read_text():
            return
        if owned.process.poll() is not None:
            raise RuntimeError('synthetic startup exit')
        time.sleep(.01)
    raise TimeoutError('synthetic startup')


def run_batch(port, cell, phase, count, folder, pids, processes=1):
    result = batch(port, {**cell, 'phase': phase}, count, folder / phase, pids, processes)
    if result['not_started']:
        raise RuntimeError(f'incomplete cell {cell["id"]}: not_started')
    rows = [json.loads(line) for line in (folder / phase / 'attempts.jsonl').read_text().splitlines()]
    if phase == 'warmup' and any(not row['success'] for row in rows):
        raise RuntimeError(f'warmup failed {cell["id"]}')
    return result


def synthetic(args, cell, base, processes=1):
    folder = base / cell['id']
    folder.mkdir()
    port = free_port()
    backend = gateway = None
    try:
        log = folder / 'backend.log'
        backend = OwnedProcess([sys.executable, HERE / 'Backend.py', '--port', port,
            '--group', cell['group'], '--output', folder / 'backend-counts.json'], log, folder / 'processes.jsonl')
        wait_ready(backend, log)
        pids = {'backend': backend.process.pid}
        if cell['path'] != 'D':
            gateway = Gateway(args, port, cell['path'], folder, cell['group'] == 'C')
            port = gateway.port
            pids['gateway_test_host' if cell['group'] == 'C' else 'gateway'] = gateway.owned.process.pid
        run_batch(port, cell, 'warmup', cell['warmup'], folder, pids)
        os.kill(backend.process.pid, signal.SIGUSR1)
        time.sleep(2)
        result = run_batch(port, cell, 'formal', cell['count'], folder, pids, processes)
        return result
    finally:
        try:
            if gateway:
                gateway.stop()
        finally:
            if backend:
                backend.stop()


def real_block(args, pair, base):
    folder = base / pair[0]['block']
    folder.mkdir()
    backend = Backend(args.assets, folder)
    gateway = None
    results = []
    try:
        backend.start()
        gateway = Gateway(args, backend.port, 'PR', folder)
        pids = {'backend': backend.owned.process.pid, 'gateway': gateway.owned.process.pid}
        for cell in pair:
            output = base / cell['id']
            output.mkdir()
            port = backend.port if cell['path'] == 'D' else gateway.port
            run_batch(port, cell, 'warmup', cell['warmup'], output, pids)
        for cell in pair:
            time.sleep(2)
            port = backend.port if cell['path'] == 'D' else gateway.port
            results.append(run_batch(port, cell, 'formal', cell['count'], base / cell['id'], pids))
            print(json.dumps({'event': 'cell', 'id': cell['id'], 'attempted': results[-1]['attempted']}), flush=True)
        return results
    finally:
        try:
            if gateway:
                gateway.stop()
        finally:
            backend.stop()


def manifest(args):
    sources = [p for root in ('src', 'tests/performance', 'tests/integration')
               for p in (ROOT / root).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    sources += [ROOT / 'CMakeLists.txt', ROOT / 'CMakePresets.json']
    return {'schema': 1, 'command': sys.argv, 'wall_time': time.time(),
        'sources': {str(p.relative_to(ROOT)): sha(p) for p in sources},
        'binaries': {str(pathlib.Path(p).resolve()): sha(p) for p in (args.gateway, args.host)},
        'fixtures': {name: {'bytes': len(body), 'sha256': digest(body)} for name, body in PAYLOADS.items()},
        'requests': {f'{real}-{stream}': digest(request_bytes(stream, real)) for real in (False, True) for stream in (False, True)},
        'python': sys.version, 'platform': platform.platform(), 'cpu_count': os.cpu_count(),
        'cpuinfo': pathlib.Path('/proc/cpuinfo').read_text().split('\n\n')[0],
        'clock': vars(time.get_clock_info('monotonic')),
        'compiler': subprocess.check_output(['c++', '--version'], text=True),
        'configuration': configuration(1, 'PR'), 'constraints': 'closed-loop CPU chain observation; not capacity'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--gateway')
    parser.add_argument('--host')
    parser.add_argument('--assets')
    parser.add_argument('--output', type=pathlib.Path)
    args = parser.parse_args()
    if args.check:
        from DetectorTests import main as check_main
        return check_main(args.output)
    for name in ('gateway', 'host', 'assets', 'output'):
        if getattr(args, name) is None:
            parser.error(f'--{name} is required')
    for name in ('gateway', 'host', 'assets'):
        if not pathlib.Path(getattr(args, name)).exists():
            parser.error(f'missing {name}')
    args.output.mkdir(parents=True, exist_ok=False)
    cells = schedule()
    controls = [{**cells[0], 'id': f'control-{i}', 'concurrency': 16, 'path': 'D',
                 'processes': 2 if i == 1 else 1} for i in range(3)]
    save(args.output / 'schedule.json', controls[:2] + cells + controls[2:])
    save(args.output / 'manifest.json', manifest(args))
    started = time.monotonic()
    results, status, error = [], 'FAIL', None
    signal.signal(signal.SIGTERM, lambda *_: request_cancel())
    signal.signal(signal.SIGINT, lambda *_: request_cancel())
    try:
        # Verify fixed assets/license before any formal measurement.
        backend = Backend(args.assets, args.output)
        license_path = pathlib.Path(args.assets) / 'models/LICENSE'
        if sha(license_path) != '832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e':
            raise ValueError('model license identity')
        save(args.output / 'license.json', {'path': str(license_path), 'sha256': sha(license_path)})
        queue = controls[:2] + cells + controls[2:]
        index = 0
        while index < len(queue):
            if CANCEL.is_set():
                raise InterruptedError('matrix cancelled')
            if time.monotonic() - started >= 2400:
                raise TimeoutError('matrix 2400 seconds guard')
            cell = queue[index]
            if cell['group'].startswith('R'):
                results.extend(real_block(args, queue[index:index + 2], args.output))
                index += 2
            else:
                results.append(synthetic(args, cell, args.output, cell.get('processes', 1)))
                index += 1
            save(args.output / 'cells.json', results)
            print(json.dumps({'event': 'progress', 'cells': len(results), 'total': 72,
                'elapsed': time.monotonic() - started, 'last': results[-1]['id']}), flush=True)
        status = 'COMPLETE'
    except BaseException as failure:
        error = repr(failure)
        raise
    finally:
        save(args.output / 'run-status.json', {'status': status, 'error': error,
             'completed_cells': len(results), 'not_started_cells': [c['id'] for c in controls[:2] + cells + controls[2:] if not (args.output / c['id']).exists()], 'elapsed': time.monotonic() - started,
             'exit_code': 0 if status == 'COMPLETE' else 1})
        save(args.output / 'cells.json', results)
    from Summarize import summarize
    save(args.output / 'summary.json', summarize(args.output))
    return 0


if __name__ == '__main__':
    sys.exit(main())
