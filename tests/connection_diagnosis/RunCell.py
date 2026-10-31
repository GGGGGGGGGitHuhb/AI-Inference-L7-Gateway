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
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "capacity"))
from Common import MIB, now, proc, write as write_artifact, rows
from TraceRuntime import preserve_early_failure, Ledger, Monitor, Owned, close_all
from Decode import correlate, read_trace
from Common import Chunks
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


@preserve_early_failure
def cell(spec, args):
    spec = dict(spec, workers=args.workers, backend_workers=args.backends)
    ledger = Ledger(args.output)
    entry = ledger.reserve(spec)
    root = Path(args.output) / spec['id']
    root.mkdir()
    owned, clients, processes = [], [], []
    start = time.monotonic()
    Owned.variant = spec['variant']
    Owned.activity_deadline = start + 60
    monitor = Monitor(owned, root, getattr(args, 'sample_interval', .1))
    monitor.activity_deadline_ns = int((start + 60) * 1e9)
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
    old_alarm = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('absolute 60s cell deadline')))
    signal.setitimer(signal.ITIMER_REAL, 60)
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
            if time.monotonic() - start > 60:
                raise RuntimeError('60 second cell activity deadline')
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
        # 先停可抛异常的计时器；清理依据同一绝对deadline，不给每个child重开时限。
        signal.setitimer(signal.ITIMER_REAL, 0)
        cleanup_signals=[]
        def remember_cleanup_signal(signum, frame):
            cleanup_signals.append(signum)
        old_signals={sig:signal.signal(sig,remember_cleanup_signal) for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGALRM)}
        monitor.phase='cleanup'
        try:
            processes,cleanup_errors=close_all(owned)
            if cleanup_errors:error=(error or '')+'; '+repr(cleanup_errors)
            try:
                write(root/'processes.json',processes)
                remaining=start+60-time.monotonic()
                if remaining<=0:raise TimeoutError('cell deadline before audit')
                # 子进程已reap，余下解析可以被剩余deadline安全中断。
                signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('cell audit deadline')))
                signal.setitimer(signal.ITIMER_REAL,remaining)
                result=audit(root)
                result['drained']=(root/'drain.json').exists()
                if spec['variant']=='T':
                    joined=correlate(root)
                    details=Chunks(root,'association',count*256+65536,row_limit=256)
                    try:
                        for row in joined.pop('failures'):
                            lb=row.get('l4',{});gw=row.get('gateway',{})
                            details.row([row['id'],row['branch'],lb.get('process'),lb.get('generation'),
                                         gw.get('process'),gw.get('generation'),row.get('l4_match'),row.get('gateway_match')])
                    finally:details.close()
                    result['association']=joined
                elif any(root.glob('*/header.bin')):raise ValueError('U/O unexpected trace output')
                if result['corruption_all_phases']:raise ValueError('trace correctness corruption')
            except BaseException as failure:
                error=(error or '')+'; audit '+repr(failure)
            finally:
                signal.setitimer(signal.ITIMER_REAL,0)
                signal.signal(signal.SIGALRM,remember_cleanup_signal)
        finally:
            try:monitor.close()
            except BaseException as failure:error=(error or '')+'; monitor '+repr(failure)
            if result is not None:
                try:result['resources']=summarize(root,spec['measure_start'],spec['duration'])
                except BaseException as failure:error=(error or '')+'; resources '+repr(failure)
            if time.monotonic()-start>60:error=(error or '')+'; cell lifecycle exceeded60s'
            if cleanup_signals:error=(error or '')+'; interrupted during cleanup '+repr(cleanup_signals)
            try:
                write(root/'result.json',{'error':error,'metrics':result})
            except BaseException as failure:
                error=(error or '')+'; result write '+repr(failure)
                raise
            finally:
                try:ledger.close(entry,time.monotonic()-start,'failed' if error else 'complete')
                finally:
                    signal.setitimer(signal.ITIMER_REAL,0)
                    for sig,handler in old_signals.items():signal.signal(sig,handler)
                    signal.signal(signal.SIGALRM,old_alarm)
    if error:
        raise RuntimeError(spec['id'] + ': ' + error)
    return result

