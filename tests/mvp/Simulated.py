"""Five exact, gated S3 groups; no extra HTTP health probes or replacement requests."""
import http.server
import json
import os
from pathlib import Path
import signal
import socket
import threading
import time
from types import SimpleNamespace

from Attempts import Attempt, FIRST, LAST
from Common import Host, ResourceSampler, append, body, check, configuration, save, summary, wait_for, cleanup_all

COUNTS = {'M1': 6, 'M2': 5, 'M3': 6, 'M4': 8, 'M5': 4}
EXPECTED = {'success': 19, 'cancelled': 2, 'backend_failure': 2, 'queue_timeout': 1, 'rejected': 5}


class Backend(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, label, output, gates, bad, port=0):
        super().__init__(('127.0.0.1', port), Handler)
        self.label, self.output, self.gates, self.bad = label, output, gates, bad
        self.connections = set()
        self.lock = threading.Lock()
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def run(self):
        self.serve_forever(poll_interval=.01)

    def close(self):
        self.shutdown()
        with self.lock:
            for sock in list(self.connections):
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()
        self.server_close()
        self.worker.join(1)
        check(not self.worker.is_alive(), 'backend thread remained')


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        with self.server.lock:
            self.server.connections.add(self.connection)

    def finish(self):
        try:
            super().finish()
        finally:
            with self.server.lock:
                self.server.connections.discard(self.connection)

    def do_POST(self):
        identity = self.headers.get('X-Mvp-Id')
        try:
            request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            append(self.server.output / (self.server.label + '-requests.jsonl'),
                   {'id': identity, 'time': time.monotonic(), 'request': request, 'backend': self.server.label})
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Transfer-Encoding', 'chunked')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(f'{len(FIRST):X}\r\n'.encode() + FIRST + b'\r\n')
            self.wfile.flush()
            check(self.server.gates[identity].wait(5), 'backend fixed gate timeout')
            if identity in self.server.bad:
                self.wfile.write(b'Z\r\ninvalid')
            else:
                self.wfile.write(f'{len(LAST):X}\r\n'.encode() + LAST + b'\r\n0\r\n\r\n')
            self.wfile.flush()
        except (OSError, ValueError):
            pass
        finally:
            self.close_connection = True


class Matrix:
    def __init__(self, host, output):
        self.host_executable = host
        self.output = Path(output)
        self.attempts = []
        self.gates, self.bad = {}, set()
        self.backends = []
        self.host = None
        self.group_started = None
        self.sampler = None

    def start_group(self, group):
        self.group = group
        self.group_started = time.monotonic()
        self.backends = [Backend(label, self.output, self.gates, self.bad) for label in ('a1', 'a2', 'b1')]
        self.host = Host(self.host_executable, configuration([b.server_port for b in self.backends]), self.output, group)
        self.host.drain(group + '-baseline')
        self.sampler = ResourceSampler({'gateway': self.host.owned, 'sim_backend_driver': SimpleNamespace(process=SimpleNamespace(pid=os.getpid()))}, self.output)

    def start(self, number, model='a', hold=False, expected='success', code=None, half=False, large=False):
        identity = f'{self.group}-{number:02}'
        gate = threading.Event()
        if not hold:
            gate.set()
        self.gates[identity] = gate
        attempt = Attempt(identity, self.group, self.host.port, body(model, large=large), self.output,
                          expected, code, timeout=3, half=half, synthetic=True)
        self.attempts.append(attempt)
        check(attempt.sent.wait(1), 'request send gate')
        return attempt

    def active(self, attempt):
        check(attempt.first.wait(1), 'first content gate')
        row = wait_for(lambda: self.host.active(attempt), .4, 'host active')
        self.event('active', attempt, row)
        return row

    def waiting(self, attempt):
        wait_for(lambda: self.host.waiting(attempt), .4, 'Waiting gate')
        self.event('waiting', attempt, self.host.record(attempt))

    def event(self, name, attempt=None, state=None):
        append(self.output / 'events.jsonl', {'event': name, 'time': time.monotonic(),
               'id': attempt.row['id'] if attempt else None, 'state': state if state is not None else self.host.state()})

    def release(self, attempt):
        self.gates[attempt.row['id']].set()

    def finish_group(self, stopping=False):
        for attempt in [a for a in self.attempts if a.row['group'] == self.group]:
            attempt.join()
        if not stopping:
            self.host.drain(self.group + '-drained')
        else:
            self.event('stopped-final')
        check(time.monotonic() - self.group_started <= 15, 'fixed group guard')
        self.sampler.stop()
        self.sampler = None
        self.host.stop()
        self.host = None
        for backend in self.backends:
            if backend:
                backend.close()
        self.backends = []

    def m1(self):
        self.start_group('M1')
        a = self.start(1, hold=True); self.active(a)
        b = self.start(2, hold=True); self.active(b)
        c = self.start(3); self.waiting(c)
        d = self.start(4); self.waiting(d)
        rejected = self.start(5, expected='rejected', code='queue_full'); rejected.join()
        other = self.start(6, model='b'); self.waiting(other)
        self.release(a)
        self.release(b)
        self.finish_group()

    def m2(self):
        self.start_group('M2')
        a = self.start(1, hold=True); self.active(a)
        b = self.start(2, hold=True); self.active(b)
        large = self.start(3, large=True, expected='rejected', code='queue_bytes_exceeded'); large.join()
        check(large.row['logical_charge'] > 4096, 'large valid queue charge')
        timed = self.start(4, expected='queue_timeout', code='queue_timeout'); self.waiting(timed); timed.join()
        self.release(a); self.release(b); a.join(); b.join()
        self.start(5).join()
        self.finish_group()

    def m3(self):
        self.start_group('M3')
        a = self.start(1, hold=True); self.active(a)
        b = self.start(2, hold=True, expected='cancelled'); self.active(b)
        cancelled = self.start(3, expected='cancelled'); self.waiting(cancelled)
        cancelled.cancel_at_gate(queued=True); cancelled.join()
        wait_for(lambda: not self.host.waiting(cancelled), .4, 'queued RST release')
        half = self.start(4, half=True); self.waiting(half)
        wait_for(lambda: self.host.record(half)['downstream_eof'], .4, 'half EOF observed')
        b.cancel_at_gate(); b.join()
        self.release(b)
        self.release(a)
        a.join(); half.join()
        self.start(5).join(); self.start(6).join()
        self.finish_group()

    def m4(self):
        self.start_group('M4')
        broken = self.start(1, hold=True, expected='backend_failure'); first = self.active(broken)
        check(first['backend_index'] == 0, 'M4-01 actual a1 required')
        other = self.start(2, model='b', hold=True); self.active(other)
        queued = self.start(3, hold=True); self.waiting(queued)
        self.bad.add(broken.row['id']); self.release(broken); broken.join()
        target = self.active(queued)
        check(target['backend_index'] == 1, 'M4-03 a2 dispatch required')
        self.release(other); self.release(queued); other.join(); queued.join()
        a2_port = self.backends[1].server_port
        self.backends[1].close(); self.backends[1] = None
        state = self.host.state()
        check(state['backends'][0]['state'] == 1 and state['now'] < state['backends'][0]['eligible_at'], 'a1 cooldown before04')
        self.event('before-a2-failure', state=state)
        self.start(4, expected='backend_failure', code='upstream_error').join()
        state = wait_for(lambda: self.host.state() if all(b['state'] == 1 for b in self.host.state()['backends'][:2]) else None,
                         .2, 'both ejected')
        check(all(state['now'] < b['eligible_at'] for b in state['backends'][:2]), 'both before cooldown')
        self.event('before-only-unavailable', state=state)
        self.start(5, expected='rejected', code='no_available_backend').join()
        a1_port = self.backends[0].server_port
        self.backends[0].close()
        self.backends[0] = Backend('a1', self.output, self.gates, self.bad, a1_port)
        wait_for(lambda: self.host.state()['now'] >= self.host.state()['backends'][0]['eligible_at'], 1.1, 'a1 cooldown end')
        trial = self.start(6, hold=True); target = self.active(trial)
        check(target['backend_index'] == 0, 'actual a1 trial required')
        check(self.host.state()['backends'][0]['state'] == 2, 'Trial before HTTP completion')
        self.event('a1-trial', trial)
        self.release(trial); trial.join()
        wait_for(lambda: self.host.state()['backends'][0]['state'] == 0, .3, 'a1 full HTTP recovery')
        self.backends[1] = Backend('a2', self.output, self.gates, self.bad, a2_port)
        self.start(7).join(); self.start(8, model='b').join()
        self.finish_group()

    def m5(self):
        self.start_group('M5')
        a = self.start(1, hold=True); self.active(a)
        b = self.start(2, hold=True); self.active(b)
        c = self.start(3, expected='rejected', code='gateway_stopping'); self.waiting(c)
        d = self.start(4, expected='rejected', code='gateway_stopping'); self.waiting(d)
        self.event('before-sigterm')
        os.kill(self.host.owned.process.pid, signal.SIGTERM)
        c.join(); d.join()
        self.release(a); self.release(b)
        self.finish_group(stopping=True)

    def run(self):
        begin = time.monotonic()
        try:
            for method in (self.m1, self.m2, self.m3, self.m4, self.m5):
                method()
                check(time.monotonic() - begin < 120, 'fixed simulated run guard')
            rows = [attempt.row for attempt in self.attempts]
            expected_ids = [f'{g}-{i:02}' for g, count in COUNTS.items() for i in range(1, count + 1)]
            result = summary(rows, expected_ids)
            counts = {key: sum(row['outcome'] == key for row in rows) for key in EXPECTED}
            check(counts == EXPECTED, 'fixed 29 denominator')
            for group in COUNTS:
                state = json.loads((self.output / (group + '-state.json')).read_text())
                for model in ('a', 'b'):
                    queued = [r for r in state['records'] if r['model'] == model and r['enqueued'] and r['dispatched']]
                    check([r['id'] for r in sorted(queued, key=lambda r: r['enqueued'])] ==
                          [r['id'] for r in sorted(queued, key=lambda r: r['dispatched'])], 'actual FIFO')
            observed = []
            for path in self.output.glob('*-requests.jsonl'):
                observed.extend(json.loads(line)['id'] for line in path.read_text().splitlines())
            check({identity for identity in observed if identity.startswith('M2-')} == {'M2-01', 'M2-02', 'M2-05'}, 'M2 unexpected upstream request')
            check(len(observed) == len(set(observed)), 'upstream retry or duplicate request')
            save(self.output / 'summary.json', result)
        finally:
            for gate in self.gates.values():
                gate.set()
            actions = [(a.row['id'], a.stop) for a in self.attempts]
            if self.sampler:
                actions.append(('sampler', self.sampler.stop))
            if self.host:
                actions.append(('host', self.host.stop))
            actions.extend((b.label, b.close) for b in self.backends if b)
            cleanup_all(actions, self.output)
