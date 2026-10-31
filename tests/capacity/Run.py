"""Bounded E1 and explicitly selected control cells. Formal mode needs frozen manifest."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
from functools import partial
from Common import MIB, now, proc, write as write_artifact, rows
from Runtime import Ledger, Monitor, Owned
from Analyze import audit
from ResourceSummary import summarize

HERE = Path(__file__).resolve().parent
write = partial(write_artifact, limit=32768)


def ports(count):
    sockets = [socket.socket() for _ in range(count)]
    try:
        for sock in sockets:
            sock.bind(('127.0.0.1', 0))
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


def gateway_config(port, backend_ports, capacity, reuse, stream_bytes=4*MIB):
    return {'listen_address': '127.0.0.1', 'listen_port': port, 'max_connections': capacity,
            'max_reserved_bytes': capacity * 16 * MIB,
            'stream_buffer': {'max_total_bytes': stream_bytes},
            'models': [{'name': 'capacity-model', 'policy': 'round_robin', 'backends': [
                {'id': f'b{i}', 'address': '127.0.0.1', 'port': p} for i, p in enumerate(backend_ports)]}],
            'health': {'failure_threshold': 2, 'cooldown_ms': 1000},
            'upstream_pool': {'max_connections': capacity, 'max_idle': capacity if reuse else 0, 'idle_timeout_ms': 1000},
            'admission': {'max_inflight': capacity, 'max_inflight_per_backend': capacity,
                          'max_queue_requests_per_model': 0, 'max_queue_bytes_per_model': 65536, 'queue_timeout_ms': 1000}}


def cell(spec, args):
    spec = dict(spec, workers=args.workers, backend_workers=args.backends)
    ledger = Ledger(args.output)
    entry = ledger.reserve(spec)
    root = Path(args.output) / spec['id']
    root.mkdir()
    owned, clients, processes = [], [], []
    start = time.monotonic()
    monitor = Monitor(owned, root, getattr(args, 'sample_interval', .1))
    monitor.activity_deadline_ns = int((start + 45) * 1e9)
    error, result = None, None
    count = int(spec['rate'] * (spec['warm'] + spec['duration']))
    spec = dict(spec, slots=args.slots, workers=args.workers, capacity=args.capacity,
                backend_workers=args.backends, reuse=args.reuse, nodelay=args.nodelay,
                stream_aggregate_bytes=getattr(args, 'stream_mib', 4) * MIB,
                sample_interval=getattr(args, 'sample_interval', .1),
                client_bytes=((count + args.workers - 1) // args.workers + 2) * 512 + 65536)
    def spawn(command, name, marker=None, log_bytes=65536):
        item = Owned(command, name, root, log_bytes)
        owned.append(item)
        if marker:
            item.ready(marker)
        monitor.check()
        return item
    old_alarm = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('absolute 45s cell deadline')))
    signal.setitimer(signal.ITIMER_REAL, 45)
    try:
        backend_ports = ports(args.backends)
        for index, port in enumerate(backend_ports):
            folder = root if args.backends == 1 else root / f'backend-{index}'
            folder.mkdir(exist_ok=True)
            spawn([sys.executable, str(HERE / 'Backend.py'), '--port', str(port), '--workload', spec['workload'],
                   '--output', str(folder), '--limit', str(count * 192 + 65536), '--nodelay', str(args.nodelay), '--fault', args.fault], 'backend-' + str(index), 'READY')
        targets = backend_ports
        if spec['path'] != 'B':
            instances = 1 if spec['path'] == 'G' else 2
            gateway_ports = ports(instances)
            for index, port in enumerate(gateway_ports):
                config = root / f'gateway-{index}.json'
                write(config, gateway_config(port, backend_ports, args.capacity // instances, args.reuse, spec['stream_aggregate_bytes'] // instances))
                spawn([args.gateway, '--config', str(config)], 'gateway-' + str(index), 'READY')
            targets = gateway_ports
            if spec['path'] == 'L':
                port = ports(1)[0]
                config = root / 'l4lb.conf'
                config.write_text(f'protocol=tcp\nlisten=127.0.0.1:{port}\n' + ''.join(f'backend=127.0.0.1:{p}\n' for p in gateway_ports) + 'scheduler=round_robin\nhealth_check=tcp_connect\nmetrics=off\n')
                lb = spawn([args.l4lb, '--run', str(config)], 'l4lb', 'TCP 服务已启动', count * 256 + 131072)
                until = time.monotonic() + 10
                while lb.tail.count(b'to=Healthy') < 2:
                    if time.monotonic() >= until:
                        raise RuntimeError('L4 health timeout')
                    time.sleep(.05)
                    monitor.check()
                targets = [port]
        spec.update(start=now() + 600_000_000, targets=targets)
        spec['measure_start'] = spec['start'] + int((spec['warm'] + 1) * 1e9)
        write(root / 'spec.json', spec)
        monitor.windows = (spec['measure_start'], spec['measure_start'] + int(spec['duration'] * 1e9))
        monitor.phase = 'requests'
        for worker in range(args.workers):
            clients.append(spawn([sys.executable, str(HERE / 'Client.py'), '--spec', str(root / 'spec.json'),
                                  '--output', str(root), '--worker', str(worker)], 'generator-' + str(worker)))
        while any(p.process.poll() is None for p in clients):
            monitor.check()
            if time.monotonic() - start > 45:
                raise RuntimeError('45 second cell activity deadline')
            for item in owned:
                if item not in clients and item.process.poll() is not None:
                    raise RuntimeError(item.name + ' unexpected exit')
            time.sleep(.02)
        if any(p.process.returncode for p in clients):
            raise RuntimeError('generator interrupted or failed')
        monitor.phase = 'fd-drain'
        # Bounded resource drain; fixture accepts health checks that send no HTTP.
        deadline = time.monotonic() + 2
        while True:
            pending = [p for p in owned if p not in clients and p.baseline_fd is not None and proc(p.process.pid)['fds'] > p.baseline_fd + (args.capacity if args.reuse else 2)]
            if not pending:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('FD drain failed: ' + ','.join(p.name for p in pending))
            time.sleep(.02)
        write(root / 'drain.json', {p.name: proc(p.process.pid) for p in owned if p not in clients})
    except BaseException as failure:
        error = repr(failure)
    finally:
        monitor.phase = 'cleanup'
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_alarm)
        for item in reversed(owned):
            try:
                record = item.close()
                processes.append(record)
                if record['returncode'] != 0:
                    error = (error or '') + '; abnormal exit ' + item.name + ':' + str(record['returncode'])
            except Exception as failure:
                processes.append({'name': item.name, 'pid': item.process.pid, 'returncode': item.process.poll(), 'capture_error': repr(failure)})
                error = (error or '') + '; cleanup ' + repr(failure)
        try:
            monitor.close()
        except Exception as failure:
            error = (error or '') + '; monitor ' + repr(failure)
        write(root / 'processes.json', processes)
        try:
            result = audit(root)
            result['drained'] = (root / 'drain.json').exists()
            result['resources'] = summarize(root, spec['measure_start'], spec['duration'])
        except Exception as failure:
            error = (error or '') + '; audit ' + repr(failure)
        write(root / 'result.json', {'error': error, 'metrics': result})
        ledger.close(entry, time.monotonic() - start, 'failed' if error else 'complete')
    if error:
        raise RuntimeError(spec['id'] + ': ' + error)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--l4lb', required=True)
    parser.add_argument('--mode', choices=['explore', 'cell', 'formal', 'resume'], required=True)
    parser.add_argument('--id')
    parser.add_argument('--manifest')
    parser.add_argument('--path', choices=['B', 'G', 'M', 'L'], default='B')
    parser.add_argument('--workload', choices=['A', 'S'], default='A')
    parser.add_argument('--rate', type=int, default=60)
    parser.add_argument('--kind', choices=['E1', 'E2', 'diagnostic'], default='diagnostic')
    parser.add_argument('--warm', type=int, default=2)
    parser.add_argument('--duration', type=int, default=5)
    parser.add_argument('--workers', type=int, choices=[1, 2], default=1)
    parser.add_argument('--backends', type=int, choices=[1, 2], default=1)
    parser.add_argument('--capacity', type=int, choices=[32, 64], default=32)
    parser.add_argument('--slots', type=int, default=128)
    parser.add_argument('--reuse', action='store_true')
    parser.add_argument('--sample-interval', type=float, choices=[.1, .5], default=.1)
    parser.add_argument('--stream-mib', type=int, choices=[4, 8, 16], default=4)
    parser.add_argument('--nodelay', type=int, choices=[0, 1], default=1)
    parser.add_argument('--fault', choices=['none', 'timeout', 'overload', 'bad_body'], default='none')
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt("controller signal " + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    if args.mode in ('formal', 'resume'):
        allowed = {'--mode', '--manifest', '--output', '--gateway', '--l4lb'}
        if any(word.startswith('--') and word.split('=')[0] not in allowed for word in sys.argv[1:]):
            raise ValueError('formal CLI configuration override prohibited')
        if args.mode == 'resume':
            from Resume import run
        else:
            from Formal import run
        return run(args)
    if not 1 <= args.slots <= 256 or not 1 <= args.rate <= 3840 or not 1 <= args.duration <= 20 or not 0 <= args.warm <= 3:
        raise ValueError('unsupported cell bounds')
    if args.workers + args.backends + (2 if args.path in ('M', 'L') else 1) + (args.path == 'L') > 6:
        raise ValueError('startup address-space aggregate bound')
    if args.mode == 'cell':
        if not args.id or len(args.id) > 48 or not all(c.isascii() and (c.isalnum() or c in '-_') for c in args.id):
            raise ValueError('bounded unique --id required')
        result = cell({'id': args.id, 'kind': args.kind, 'path': args.path, 'workload': args.workload,
                       'rate': args.rate, 'warm': args.warm, 'duration': args.duration}, args)
        print(json.dumps(result), flush=True)
    else:
        for workload in ['A', 'S']:
            for path in ['B', 'G']:
                failures = 0
                for rate in [60, 120, 240, 480, 960, 1920, 3840]:
                    result = cell({'id': f'E1-{workload}-{path}-{rate}', 'kind': 'E1', 'path': path,
                                   'workload': workload, 'rate': rate, 'warm': 2, 'duration': 5}, args)
                    print(json.dumps(result), flush=True)
                    failures = 0 if result['exploration_slo_pass'] else failures + 1
                    if not result['generator_valid'] or failures >= 2:
                        break


if __name__ == '__main__':
    main()
