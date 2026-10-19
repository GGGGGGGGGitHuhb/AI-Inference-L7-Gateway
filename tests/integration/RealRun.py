"""显式真实 CPU 后端协议与 600 秒稳定性；失败保留，退出非零。"""
import argparse
import json
import os
import pathlib
import platform
import signal
import subprocess
import time
from Support import (ROOT, INPUTS, Backend, Host, OwnedProcess, Sampler, append, check,
                     exchange, free_port, gateway_config, get_json, process_stats,
                     request_body, reset_client, save, sha, validate_real, validate_rss, install_interrupt_handlers, source_identity, recorded_exchange)


class RealRun:
    def __init__(self, args):
        self.args = args
        self.output = pathlib.Path(args.output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.backend = None
        self.host = None
        self.sampler = None
        self.samples = 0

    def sample(self, label, port, stream, **options):
        long = options.pop('long', False)
        context = options.pop('context', False)
        request = request_body(stream, long, context)
        validator = options.pop('_validator', None)
        result = recorded_exchange(port, request, self.output / 'protocol-samples.jsonl',
                                   {'label': label, 'stream': stream, 'long': long},
                                   validator=validator, **options)
        self.samples += 1
        return result

    def normal(self, label, port, stream, **options):
        result = self.sample(label, port, stream,
                             _validator=lambda result: validate_real(result, stream, options.get('long', False)),
                             **options)
        return result

    def protocol(self):
        for number in range(2):
            for stream in (False, True):
                for name, port in [('direct', self.backend.port), ('proxy', self.host.port)]:
                    self.normal(f'warmup-{name}-{number}', port, stream)
        for number in range(10):
            for stream in (False, True):
                for name, port in [('direct', self.backend.port), ('proxy', self.host.port)]:
                    self.normal(f'formal-{name}-{number}', port, stream)
        for number in range(3):
            self.normal(f'long-{number}', self.host.port, True, long=True)
            self.normal(f'slow-{number}', self.host.port, True, slow=True)
            self.normal(f'half-close-{number}', self.host.port, True, half_close=True)
        errors = []
        for name, port in [('direct', self.backend.port), ('proxy', self.host.port)]:
            result = self.sample(f'context-{name}', port, False, context=True)
            check(400 <= result['status'] < 500 and result['complete'], 'context error must be real 4xx')
            errors.append(json.loads(result['body']))
        check(errors[0] == errors[1], 'context error structure preserved')
        print('protocol complete', self.samples, flush=True)

    def cancel(self):
        for number in range(5):
            evidence = {'case': number}
            def on_content(sock):
                evidence['before_slots'] = get_json(self.backend.port, '/slots')
                evidence['cancel_time'] = time.monotonic()
                evidence['before_snapshot'] = self.host.refresh()
                return reset_client(sock)
            result = self.sample(f'cancel-{number}', self.host.port, True, long=True, on_content=on_content)
            check(result.get('cancelled') and not result['complete'], 'RST after real content')
            evidence['drained'] = self.host.drain()
            check(evidence['drained']['time'] - evidence['cancel_time'] < 5, 'cancel local cleanup <=5s')
            slots = []
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                slots = get_json(self.backend.port, '/slots')
                if all(not slot.get('is_processing', True) for slot in slots):
                    break
                time.sleep(.05)
            evidence['after_slots'] = slots
            evidence['slot_idle_observed'] = bool(slots) and all(not slot.get('is_processing', True) for slot in slots)
            self.normal(f'cancel-recovery-{number}', self.host.port, False)
            evidence['recovery_time'] = time.monotonic()
            append(self.output / 'cancellation.jsonl', evidence)
        print('cancellation complete', flush=True)

    def faults(self):
        for number, signum in enumerate([signal.SIGTERM, signal.SIGTERM, signal.SIGKILL]):
            if number == 0:
                self.backend.stop(signum)
                result = self.sample('fault-before-request', self.host.port, False)
                check(result['status'] in (502, 503) and result['complete'], 'closed backend definite error')
            else:
                def stop_backend(sock):
                    self.backend.stop(signum)
                result = self.sample(f'fault-in-stream-{number}', self.host.port, True,
                                     long=True, on_content=stop_backend)
                check(result['status'] == 200 and result['content_times'] and not result['complete']
                      and result['done'] == 0, 'stream fault must truncate')
            drained = self.host.drain()
            append(self.output / 'backend-faults.jsonl', {'case': number, 'signal': signum,
                  'result': result, 'drained': drained})
            self.backend.start()
            for recovery in range(2):
                for stream in (False, True):
                    self.normal(f'fault-recovery-{number}-{recovery}', self.host.port, stream)
        print('backend faults/recovery complete', flush=True)

    def official_smoke(self):
        config = gateway_config(self.backend.port, True)
        config['listen_port'] = free_port()
        config_path = self.output / 'official-config.json'
        save(config_path, config)
        owned = OwnedProcess([self.args.gateway, '--config', config_path],
                             self.output / 'official.log', self.output / 'processes.jsonl')
        try:
            time.sleep(.2)
            check(owned.process.poll() is None, 'official gateway running')
            for stream in (False, True):
                self.normal('official-smoke', config['listen_port'], stream)
            def shutdown(sock):
                os.kill(owned.process.pid, signal.SIGTERM)
            result = self.sample('official-active-shutdown', config['listen_port'], True,
                                 long=True, on_content=shutdown)
            check(result['status'] == 200 and result['content_times'], 'active shutdown content')
            # 3秒停止期限允许长响应被截断；不能把截断标正常。
            check(result['complete'] or (result['error'] and result['done'] == 0), 'bounded shutdown terminal')
            owned.process.wait(5)
            check(owned.process.returncode == 0, 'official shutdown exit')
        finally:
            owned.stop()

    def soak(self):
        for number in range(5):
            self.normal(f'soak-warmup-{number}', self.host.port, bool(number % 2))
        baseline = self.host.drain()
        drains = []
        start = time.monotonic()
        count = 0
        next_progress = start + 60
        while time.monotonic() - start < 600 or count < 60 or count % 10:
            check(time.monotonic() - start < 1800, 'real soak guard 1800s')
            stream = bool(count % 2)
            result = recorded_exchange(self.host.port, request_body(stream),
                                       self.output / 'real-soak.jsonl',
                                       {'index': count, 'stream': stream},
                                       validator=lambda result: validate_real(result, stream))
            count += 1
            self.host.refresh()
            if count % 10 == 0:
                drains.append(self.host.drain())
                check(drains[-1]['rss'] <= baseline['rss'] + 32 * 1024**2, 'RSS fixed bound')
            time.sleep(.1)
            if time.monotonic() >= next_progress:
                print('real-soak', round(time.monotonic()-start, 1), 'seconds', count,
                      'requests', 'last-drain', drains[-1] if drains else None, flush=True)
                next_progress += 60
        validate_rss(baseline['rss'], drains)
        self.normal('post-soak-recovery', self.host.port, False)
        self.host.drain()
        save(self.output / 'real-soak-summary.json', {'seconds': time.monotonic()-start,
             'count': count, 'nonstream': count//2, 'stream': count//2,
             'unexpected_failures': 0, 'baseline': baseline, 'last_five': drains[-5:],
             'maxima': self.host.maxima})

    def run(self):
        save(self.output / 'manifest.json', {'stage': 'V0.2/S3', 'workload': 'real',
             'minimum_seconds': 600, 'minimum_requests': 60, 'concurrency': 1,
             'inputs': INPUTS, 'inputs_sha256': sha(pathlib.Path(__file__).with_name('Inputs.json')),
             'host_sha256': sha(self.args.host), 'gateway_sha256': sha(self.args.gateway),
             'source_sha256': source_identity(), 'platform': platform.platform(), 'started': time.time(), 'arguments': vars(self.args)})
        try:
            self.backend = Backend(self.args.assets, self.output)
            self.backend.start()
            self.host = Host(self.args.host, gateway_config(self.backend.port, True), self.output)
            self.sampler = Sampler(self.host, self.backend, self.output / 'resources.jsonl')
            self.protocol()
            self.cancel()
            self.faults()
            self.official_smoke()
            if not self.args.calibration:
                self.soak()
            save(self.output / 'result.json', {'status': 'CALIBRATION_PASS' if self.args.calibration else 'PASS', 'protocol_samples': self.samples})
        except BaseException as error:
            save(self.output / 'result.json', {'status': 'FAIL', 'error': repr(error)})
            raise
        finally:
            try:
                if self.sampler:
                    self.sampler.stop()
            finally:
                try:
                    if self.host:
                        self.host.stop()
                finally:
                    if self.backend:
                        self.backend.stop()
            size = sum(p.stat().st_size for p in self.output.rglob('*') if p.is_file())
            check(size <= 128 * 1024**2, 'role run log bound')


def main():
    install_interrupt_handlers()
    parser = argparse.ArgumentParser()
    parser.add_argument('--assets', required=True)
    parser.add_argument('--host', required=True)
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--calibration', action='store_true', help='protocol only; never a soak acceptance result')
    args = parser.parse_args()
    RealRun(args).run()


if __name__ == '__main__':
    main()
