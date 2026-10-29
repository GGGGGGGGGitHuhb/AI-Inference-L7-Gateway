"""V0.5/S1 production-binary composition and deterministic failure matrix."""
import argparse
import http.client
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import subprocess
import time

from Checks import require, response, receipts, truncated
from Fixture import Backend, prefix
from Identity import sha


def wait_for(predicate, detail, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = predicate()
        if result:
            return result
        time.sleep(.02)
    raise AssertionError('deadline: ' + detail)


def free_ports(count):
    holders = []
    try:
        for _ in range(count):
            sock = socket.socket()
            sock.bind(('127.0.0.1', 0))
            holders.append(sock)
        return [sock.getsockname()[1] for sock in holders]
    finally:
        for sock in holders:
            sock.close()


class Owned:
    def __init__(self, command, directory, name):
        self.name = name
        self.command = command
        self.out = directory / (name + '.stdout')
        self.err = directory / (name + '.stderr')
        with self.out.open('xb') as out, self.err.open('xb') as err:
            # prlimit applies limits without Python preexec_fn in a threaded fixture.
            self.process = subprocess.Popen(['prlimit', '--fsize=1048576:1048576', '--core=0:0', '--',
                                             *command], stdout=out, stderr=err, start_new_session=True)
        self.expected = 0
        self.stop_requested = False
        self.baseline_fd = None

    def text(self, stderr=False):
        return (self.err if stderr else self.out).read_text(errors='replace')

    def ready(self, marker):
        def poll():
            require(self.process.poll() is None, self.name + ' exited before ready')
            return marker in self.text()
        wait_for(poll, self.name + ' ready')
        self.baseline_fd = len(list(Path(f'/proc/{self.process.pid}/fd').iterdir()))

    def kill(self):
        require(self.process.poll() is None, self.name + ' already exited')
        self.expected = -signal.SIGKILL
        self.process.kill()
        self.process.wait(timeout=5)

    def close(self):
        forced = False
        if self.process.poll() is None and not self.stop_requested:
            self.stop_requested = True
            self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            forced = True
            self.process.kill()
            self.process.wait(timeout=5)
        return {'name': self.name, 'pid': self.process.pid, 'command': self.command,
                'exit': self.process.returncode, 'expected': self.expected, 'forced_cleanup': forced}


class Matrix:
    def __init__(self, args):
        self.args = args
        self.output = Path(args.output).resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.started = time.monotonic()
        self.backends = []
        self.owned = []
        self.connections = []
        self.responses = []
        self.expected_ids = []
        self.attempts = []
        self.cases = []
        self.events = []
        self.generations = [0, 0]
        self.gateways = [None, None]
        self.lb = None

    def event(self, event, **values):
        row = {'event': event, 'seconds': time.monotonic() - self.started, **values}
        self.events.append(row)
        with (self.output / 'events.jsonl').open('a') as file:
            file.write(json.dumps(row) + '\n')

    def spawn_gateway(self, index):
        self.generations[index] += 1
        name = f'gateway-{index}-{self.generations[index]}'
        owned = Owned([self.args.gateway, '--config', str(self.output / f'gateway-{index}.json')], self.output, name)
        self.owned.append(owned)
        self.gateways[index] = owned
        owned.ready('READY ')
        self.event('gateway_ready', index=index, pid=owned.process.pid)

    def setup(self):
        for model in ('model-a', 'model-b'):
            self.backends.append(Backend(model))
        self.lb_port, *self.gw_ports = free_ports(3)
        templates = Path(__file__).parent / 'configs'
        for index, port in enumerate(self.gw_ports):
            config = json.loads((templates / f'gateway-{index}.json').read_text())
            config['listen_port'] = port
            for model, backend in zip(config['models'], self.backends):
                model['backends'][0]['port'] = backend.server_port
            (self.output / f'gateway-{index}.json').write_text(json.dumps(config, indent=2) + '\n')
            self.spawn_gateway(index)
        text = (templates / 'l4lb.conf').read_text()
        for old, new in zip((8080, 18080, 18081), (self.lb_port, *self.gw_ports)):
            text = text.replace(f':{old}\n', f':{new}\n')
        conf = self.output / 'l4lb.conf'
        conf.write_text(text)
        self.lb = Owned([self.args.l4lb, '--run', str(conf)], self.output, 'l4lb')
        self.owned.append(self.lb)
        self.lb.ready('TCP 服务已启动')

    def accepted(self):
        return re.findall(r'session=(\d+) backend=127\.0\.0\.1:(\d+) reason=accepted', self.lb.text(True))

    def health(self, index, state, after=0):
        pattern = rf'health backend=127\.0\.0\.1:{self.gw_ports[index]} from=\w+ to=(\w+)'
        def poll():
            require(self.lb.process.poll() is None, 'L4 exited during health wait')
            matches = re.findall(pattern, self.lb.text(True)[after:])
            return bool(matches and matches[-1] == state)
        wait_for(poll, f'gateway-{index} {state}', 12)
        self.event('health_observed', index=index, state=state)

    def connect(self):
        count = len(self.accepted())
        conn = http.client.HTTPConnection('127.0.0.1', self.lb_port, timeout=5)
        conn.connect()
        self.connections.append(conn)
        rows = wait_for(lambda: self.accepted() if len(self.accepted()) > count else None, 'L4 accepted')
        require(len(rows) == count + 1, 'ambiguous L4 connection association')
        sid, port = rows[-1]
        index = self.gw_ports.index(int(port))
        self.event('connection', session=sid, gateway=index)
        return conn, index

    def send(self, conn, index, identity, model='model-a', stream=False, expected_backend=True, half=False):
        require(identity not in [row['id'] for row in self.attempts], 'duplicate request identity')
        body = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': identity}], 'stream': stream})
        self.attempts.append({'id': identity, 'gateway': index, 'model': model, 'stream': stream,
                              'expected_backend': expected_backend})
        if expected_backend:
            self.expected_ids.append(identity)
        conn.request('POST', '/v1/chat/completions', body, {'Content-Type': 'application/json'})
        if half:
            conn.sock.shutdown(socket.SHUT_WR)
        result = conn.getresponse()
        self.responses.append(result)
        self.event('response_headers', id=identity, status=result.status)
        return result

    def exchange(self, identity, model='model-a', expected_gateway=None, half=False):
        conn, index = self.connect()
        if expected_gateway is not None:
            require(index == expected_gateway, f'{identity}: selected failed gateway')
        result = self.send(conn, index, identity, model, half=half)
        data = result.read()
        response(result.status, data, identity, model)
        self.event('response_complete', id=identity, body=data.decode())
        result.close()
        conn.close()
        return index

    def stream(self, conn, index, identity):
        gate = self.backends[0].gate(identity)
        raw = conn.sock
        result = self.send(conn, index, identity, stream=True)
        first = result.read(len(prefix(identity, 'model-a')))
        require(result.status == 200 and first == prefix(identity, 'model-a'), 'stream prefix mismatch')
        require(not gate.is_set(), 'stream not observed before gate release')
        self.event('stream_prefix', id=identity, body=first.decode())
        return result, first, gate, raw

    def finish_stream(self, state, identity):
        result, first, gate, _ = state
        gate.set()
        body = first + result.read()
        response(result.status, body, identity, 'model-a', True)
        self.event('stream_complete', id=identity, body=body.decode())
        result.close()

    def reject_transport(self, identity):
        before = len(self.accepted())
        with socket.create_connection(('127.0.0.1', self.lb_port), timeout=5) as sock:
            try:
                sock.sendall(b'POST /v1/chat/completions HTTP/1.1\r\nHost: local\r\nContent-Length: 0\r\n\r\n')
                data = sock.recv(1024)
            except (ConnectionResetError, BrokenPipeError):
                data = b''
            require(data == b'', identity + ' must close without response')
        require(len(self.accepted()) == before, 'no-healthy path created backend session')
        self.event('transport_rejected', id=identity)

    def case(self, name, operation):
        self.event('case_start', case=name)
        operation()
        self.cases.append(name)
        self.event('case_pass', case=name)
        print('PASS', name, flush=True)

    def startup(self):
        require(not self.accepted(), 'unexpected initial session')
        require('to=Healthy' not in self.lb.text(True), 'missed Unknown window')
        self.reject_transport('unknown')
        for index in range(2):
            self.health(index, 'Healthy')

    def routing(self):
        selected = [self.exchange(f'route-{n}', ('model-a', 'model-b')[(n // 2) % 2]) for n in range(6)]
        require(set(selected) == {0, 1} and all(a != b for a, b in zip(selected, selected[1:])), 'RR coverage')
        conn, index = self.connect()
        result = self.send(conn, index, 'downstream-close')
        response(result.status, result.read(), 'downstream-close', 'model-a')
        require(result.will_close and conn.sock is None, 'downstream single-request close contract')
        self.event('downstream_close', id='downstream-close', connection=result.getheader('Connection'))
        result.close()
        conn.close()
        self.exchange('half-close', half=True)

    def quota_cancel(self):
        first, a = self.connect()
        second, b = self.connect()
        require(a != b, 'quota requires two Gateway instances')
        one = self.stream(first, a, 'quota-a')
        two = self.stream(second, b, 'quota-b')
        conn, index = self.connect()
        result = self.send(conn, index, 'quota-reject', expected_backend=False)
        data = result.read()
        require(result.status == 503 and json.loads(data)['error']['code'] == 'queue_full', 'local admission rejection')
        self.event('admission_rejected', id='quota-reject', gateway=index, body=data.decode())
        result.close()
        conn.close()
        self.finish_stream(one, 'quota-a')
        self.finish_stream(two, 'quota-b')
        first.close()
        second.close()
        conn, index = self.connect()
        cancelled = self.stream(conn, index, 'cancel')
        result, _, gate, raw = cancelled
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
        result.close()
        conn.close()
        gate.set()
        # Allow the actual RST and capacity release to travel through both proxies.
        time.sleep(.2)
        for n in range(2):
            self.exchange(f'after-cancel-{n}')

    def failover(self):
        conn, failed_index = self.connect()
        other, survivor_index = self.connect()
        require(failed_index != survivor_index, 'fault streams must bind different Gateways')
        failed = self.stream(conn, failed_index, 'failed-stream')
        survivor = self.stream(other, survivor_index, 'survivor-stream')
        offset = len(self.lb.text(True))
        self.gateways[failed_index].kill()
        result, first, gate, _ = failed
        framing_failed = False
        try:
            tail = result.read()
            first += tail
        except http.client.IncompleteRead as error:
            first += error.partial
            framing_failed = True
        truncated(result.status, first, 'failed-stream', 'model-a', framing_failed)
        self.event('stream_truncated', id='failed-stream', gateway=failed_index, body=first.decode())
        gate.set()
        result.close()
        conn.close()
        self.finish_stream(survivor, 'survivor-stream')
        other.close()
        self.health(failed_index, 'Unhealthy', offset)
        for n in range(4):
            self.exchange(f'survivor-{n}', expected_gateway=survivor_index)
        offset = len(self.lb.text(True))
        self.spawn_gateway(failed_index)
        self.health(failed_index, 'Healthy', offset)
        require({self.exchange(f'recovered-{n}') for n in range(4)} == {0, 1}, 'recovered Gateway never selected')

    def all_down(self):
        offset = len(self.lb.text(True))
        for gateway in self.gateways:
            gateway.kill()
        for index in range(2):
            self.health(index, 'Unhealthy', offset)
        self.reject_transport('all-down')
        require(self.lb.process.poll() is None, 'L4 must remain alive')
        offset = len(self.lb.text(True))
        for index in range(2):
            self.spawn_gateway(index)
        for index in range(2):
            self.health(index, 'Healthy', offset)
        require({self.exchange(f'all-recovered-{n}') for n in range(2)} == {0, 1}, 'all-down recovery')

    def app_health(self):
        self.backends[0].unavailable = True
        offset = len(self.lb.text(True))
        selected = []
        for n in range(2):
            conn, index = self.connect()
            selected.append(index)
            identity = f'app-failure-{n}'
            result = self.send(conn, index, identity)
            require(result.status == 503, 'application failure must be visible')
            result.read()
            result.close()
            conn.close()
        require(set(selected) == {0, 1}, 'application failure did not cover both Gateways')
        time.sleep(2.3)
        require('to=Unhealthy' not in self.lb.text(True)[offset:], 'HTTP error changed L4 health')
        for n in range(2):
            self.exchange(f'other-model-{n}', 'model-b')
        self.backends[0].unavailable = False

    def audit(self):
        records = [row for backend in self.backends for row in backend.records]
        receipts(records, self.expected_ids)
        require(all(not backend.errors for backend in self.backends), 'fixture errors')
        for owned in [self.lb, *self.gateways]:
            def count():
                require(owned.process.poll() is None, owned.name + ' unexpected exit')
                fds = len(list(Path(f'/proc/{owned.process.pid}/fd').iterdir()))
                return fds if fds <= owned.baseline_fd + 2 else None
            fds = wait_for(count, owned.name + ' FD return')
            self.event('fds', process=owned.name, baseline=owned.baseline_fd, final=fds, tolerance=2)

    def close(self):
        errors = []
        for result in self.responses:
            try:
                result.close()
            except Exception as error:
                errors.append('response close: ' + repr(error))
        for conn in self.connections:
            try:
                conn.close()
            except Exception as error:
                errors.append('connection close: ' + repr(error))
        for backend in self.backends:
            try:
                backend.close()
            except Exception as error:
                errors.append(repr(error))
        processes = []
        for owned in reversed(self.owned):
            try:
                processes.append(owned.close())
            except Exception as error:
                errors.append(owned.name + ' cleanup: ' + repr(error))
                processes.append({'name': owned.name, 'pid': owned.process.pid,
                                  'command': owned.command, 'exit': owned.process.poll(),
                                  'expected': owned.expected, 'forced_cleanup': True})
        records = [row for backend in self.backends for row in backend.records]
        for backend in self.backends:
            errors.extend(backend.errors)
        for process in processes:
            if process['forced_cleanup'] or process['exit'] != process['expected']:
                errors.append('unexpected process exit: ' + process['name'])
        (self.output / 'processes.json').write_text(json.dumps(processes, indent=2) + '\n')
        (self.output / 'backend-records.json').write_text(json.dumps(records, indent=2) + '\n')
        (self.output / 'attempts.json').write_text(json.dumps(self.attempts, indent=2) + '\n')
        return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--l4lb', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    args.gateway, args.l4lb = str(Path(args.gateway).resolve()), str(Path(args.l4lb).resolve())
    for path in (args.gateway, args.l4lb):
        require(Path(path).is_file() and os.access(path, os.X_OK), 'executable missing: ' + path)
    matrix = Matrix(args)
    identity = {name: {'path': path, 'sha256': sha(path)} for name, path in [('gateway', args.gateway), ('l4lb', args.l4lb)]}
    identity['tools'] = {p.name: sha(p) for p in Path(__file__).parent.glob('*.py')}
    (matrix.output / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    def interrupted(signum, frame):
        raise RuntimeError(f'run interrupted by signal {signum}')
    signal.signal(signal.SIGALRM, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    signal.alarm(120)
    error = None
    try:
        matrix.setup()
        for name, operation in [('unknown', matrix.startup), ('routing-close-halfclose', matrix.routing),
                                ('quota-stream-cancel', matrix.quota_cancel), ('gateway-failure-recovery', matrix.failover),
                                ('all-down-recovery', matrix.all_down), ('tcp-vs-application-health', matrix.app_health)]:
            matrix.case(name, operation)
        matrix.audit()
    except Exception as failure:
        error = repr(failure)
    finally:
        signal.alarm(0)
        cleanup_errors = matrix.close()
        if cleanup_errors:
            error = (error or '') + '; cleanup: ' + repr(cleanup_errors)
        result = {'status': 'FAIL' if error else 'PASS', 'cases': matrix.cases, 'error': error,
                  'seconds': time.monotonic() - matrix.started, 'request_count': len(matrix.attempts),
                  'backend_expected_count': len(matrix.expected_ids)}
        (matrix.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    return 1 if error else 0


if __name__ == '__main__':
    raise SystemExit(main())
