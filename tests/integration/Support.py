"""仅标准库的显式集成工具；不被普通 CTest 自动下载或启动模型。"""
import hashlib
import http.client
import json
import os
import pathlib
import signal
import socket
import struct
import subprocess
import threading
import time
import itertools
from contextlib import nullcontext
from WireResponse import WireResponse

ROOT = pathlib.Path(__file__).resolve().parents[2]
INPUTS = json.loads((pathlib.Path(__file__).with_name('Inputs.json')).read_text())


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for part in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()


def save(path, value):
    pathlib.Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False))


def append(path, value):
    with open(path, 'a') as output:
        output.write(json.dumps(value, ensure_ascii=False) + '\n')
    check(pathlib.Path(path).stat().st_size < 64 * 1024 * 1024, 'individual evidence limit')


def free_port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def process_stats(pid):
    base = pathlib.Path('/proc') / str(pid)
    try:
        values = (base / 'statm').read_text().split()
        return {'rss': int(values[1]) * os.sysconf('SC_PAGE_SIZE'),
                'fd': len(list((base / 'fd').iterdir()))}
    except FileNotFoundError:
        return None


class OwnedProcess:
    def __init__(self, command, log, record):
        self.log = open(log, 'wb')
        self.command = [str(value) for value in command]
        self.record = record
        try:
            self.process = subprocess.Popen(self.command, stdout=self.log, stderr=self.log,
                                            start_new_session=True)
        except BaseException:
            self.log.close()
            raise
        append(record, {'event': 'start', 'pid': self.process.pid,
                        'command': self.command, 'time': time.time()})

    def stop(self, signum=signal.SIGTERM):
        if self.process.poll() is None:
            os.killpg(self.process.pid, signum)
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(5)
        self.log.close()
        append(self.record, {'event': 'reaped', 'pid': self.process.pid,
                             'exit': self.process.returncode, 'time': time.time()})


def get_json(port, path):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        connection.request('GET', path, headers={'Connection': 'close'})
        response = connection.getresponse()
        check(response.status == 200, f'{path}: {response.status}')
        return json.loads(response.read())
    finally:
        connection.close()


class Backend:
    def __init__(self, assets, output):
        self.assets = pathlib.Path(assets).resolve()
        self.output = pathlib.Path(output)
        self.port = free_port()
        self.owned = None
        self.generation = 0
        asset_list = json.loads((self.assets / 'asset-verification.json').read_text())
        expected = [(19144446, '9cbbff430e4f2d976135d68d998576530cc1bd87babe1d71db4886d8a79e7b2e'),
                    (491400032, '74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db')]
        check([(a['bytes'], a['sha256']) for a in asset_list] == expected, 'Approved asset identities')
        for asset in asset_list:
            path = ROOT / asset['path']
            check(path.stat().st_size == asset['bytes'], f'asset size {path}')
            check(sha(path) == asset['sha256'], f'asset hash {path}')
        self.executable = self.assets / 'backend/llama-b7481/llama-server'
        self.model = self.assets / 'models/qwen2.5-0.5b-instruct-q4_k_m.gguf'
        save(self.output / 'assets.json', {'verified': asset_list, 'server_sha256': sha(self.executable),
             'libraries': {str(p): sha(p) for p in self.executable.parent.glob('*.so*') if p.is_file()}})

    def start(self):
        check(self.owned is None, 'one model server at a time')
        startup_deadline = time.monotonic() + 120
        port_deadline = time.monotonic() + 65
        while True:
            try:
                with socket.socket() as probe:
                    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    probe.bind(('127.0.0.1', self.port))
                break
            except OSError:
                # 已回收的模型连接可留下 TIME_WAIT；不改固定上游端口。
                check(self.generation > 0, 'initial backend port conflict')
                with open('/proc/net/tcp') as connections:
                    active_listener = any(line.split()[1].endswith(f':{self.port:04X}')
                        and line.split()[3] == '0A' for line in list(connections)[1:])
                check(not active_listener, 'backend port has a live listener')
                check(time.monotonic() < port_deadline, 'backend TIME_WAIT port timeout')
                time.sleep(.2)
        command = [self.executable, '-m', self.model, '--host', '127.0.0.1', '--port', self.port,
                   '--alias', 'gateway-qwen', '--ctx-size', 2048, '--parallel', 1,
                   '--threads', 4, '--threads-batch', 4, '--n-gpu-layers', 0, '--metrics']
        self.generation += 1
        self.owned = OwnedProcess(command, self.output / f'backend-{self.generation}.log',
                                  self.output / 'processes.jsonl')
        while time.monotonic() < startup_deadline:
            check(self.owned.process.poll() is None, 'backend startup exit')
            stats = process_stats(self.owned.process.pid)
            check(stats is not None and stats['rss'] <= 2 * 1024**3, 'backend startup RSS guard')
            try:
                if get_json(self.port, '/health').get('status') == 'ok':
                    return
            except (OSError, AssertionError):
                pass
            time.sleep(.1)
        raise TimeoutError('backend startup 120 seconds')

    def stop(self, signum=signal.SIGTERM):
        if self.owned:
            self.owned.stop(signum)
            self.owned = None


def gateway_config(upstream, real):
    config = {'listen_address': '127.0.0.1', 'listen_port': 0,
              'upstream_address': '127.0.0.1', 'upstream_port': upstream,
              'max_connections': 4, 'max_reserved_bytes': 67108864,
              'upstream_pool': {'max_connections': 4, 'max_idle': 1, 'idle_timeout_ms': 1000},
              'stream_buffer': {'high_water_bytes': 196608, 'low_water_bytes': 65536,
                                'max_total_bytes': 1048576}}
    if real:
        config['timeouts_ms'] = {'request': 10000, 'connect': 3000, 'upstream_write': 5000,
            'response': 120000, 'downstream_write': 10000, 'total': 150000,
            'shutdown': 3000, 'stream_idle': 30000}
    return config


class Host:
    def __init__(self, executable, config, output, name='host'):
        self.output = pathlib.Path(output)
        self.path = self.output / f'{name}-snapshots.jsonl'
        self.config = config
        config_path = self.output / f'{name}-config.json'
        save(config_path, config)
        self.owned = OwnedProcess([executable, config_path], self.path, self.output / 'processes.jsonl')
        self.port = None
        self.cursor = 0
        self.latest = None
        self.maxima = {}
        try:
            self.wait_ready()
        except BaseException:
            self.owned.stop()
            raise

    def wait_ready(self):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.refresh()
            if self.port and self.latest:
                self.baseline_fd = process_stats(self.owned.process.pid)['fd']
                return
            check(self.owned.process.poll() is None, 'host startup failure')
            time.sleep(.02)
        raise TimeoutError('host startup')

    def refresh(self):
        with open(self.path) as source:
            source.seek(self.cursor)
            while True:
                line = source.readline()
                if not line or not line.endswith('\n'):
                    break
                self.cursor = source.tell()
                value = json.loads(line)
                if 'ready_port' in value:
                    self.port = value['ready_port']
                    continue
                self.latest = value
                check(value['reserved'] <= self.config['max_reserved_bytes'], 'reservation overflow')
                check(value['capacity'] <= self.config['stream_buffer']['max_total_bytes'], 'capacity overflow')
                check(value['pending'] <= value['capacity'], 'pending exceeds allocation')
                check(value['peak_reserved'] <= self.config['max_reserved_bytes'], 'peak reservation overflow')
                check(value['peak_capacity'] <= self.config['stream_buffer']['max_total_bytes'], 'peak capacity overflow')
                for key, item in value.items():
                    self.maxima[key] = max(self.maxima.get(key, 0), item)
        return self.latest

    def drain(self):
        start = time.monotonic()
        # 新请求完成后要读取新快照，不能误用上一个空闲点。
        time.sleep(.15)
        while time.monotonic() - start < 5:
            value = self.refresh()
            if all(value[key] == 0 for key in ('sessions', 'reserved', 'capacity', 'pending',
                    'paused', 'timers', 'upstreams', 'leased', 'idle', 'pool_total', 'retired')):
                stats = process_stats(self.owned.process.pid)
                check(stats['fd'] == self.baseline_fd, f'FD baseline {stats} != {self.baseline_fd}')
                point = {'time': time.monotonic(), 'snapshot': value, **stats}
                append(self.output / 'drains.jsonl', point)
                return point
            time.sleep(.05)
        raise AssertionError(f'resource drain timeout: {value}')

    def stop(self):
        self.owned.stop()


def request_body(stream, long=False, context=False):
    prompt = INPUTS['context_unit'] * 600 if context else INPUTS['long' if long else 'short']
    return {'model': 'gateway-qwen', 'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0, 'max_tokens': 512 if long else 32, 'stream': stream, 'n': 1}


def exchange(port, request, slow=False, half_close=False, on_content=None, synthetic=False, timeout=150):
    start = time.monotonic()
    result = {'request_sha256': None, 'start': start,
              'complete': False, 'pieces': [], 'content_times': [], 'done': 0, 'finish': [],
              'status': None, 'error': None}
    received = bytearray()
    event_buffer = b''
    content = []
    sock = None
    response = None
    try:
        body = json.dumps(request, ensure_ascii=False).encode()
        result['request_sha256'] = hashlib.sha256(body).hexdigest()
        sock = socket.create_connection(('127.0.0.1', port), timeout=timeout)
        if slow and synthetic:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        headers = (f'POST /v1/chat/completions HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n'
                   f'Content-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode()
        sock.sendall(headers + body)
        if half_close:
            sock.shutdown(socket.SHUT_WR)
        if slow:
            time.sleep(1)
        response = WireResponse(sock)
        response.begin()
        result.update(status=response.status, headers=response.getheaders(), raw_head=response.raw_head.decode('latin1'), head=time.monotonic(),
                      framing='chunked' if response.chunked else 'CL' if response.length is not None else 'EOF')
        while True:
            part = response.read1(1024 if slow else 16384)
            if not part:
                check(response.chunked or response.length in (None, 0), 'short Content-Length body')
                if request.get('stream') and response.status == 200 and not synthetic:
                    check(not event_buffer.strip(), 'unfinished SSE event')
                result['complete'] = True
                break
            now = time.monotonic()
            received.extend(part)
            check(len(received) <= 16 * 1024**2, 'client response bound')
            result['pieces'].append([now, len(part)])
            if not synthetic and request['stream'] and response.status == 200:
                event_buffer += part
                while b'\n\n' in event_buffer:
                    event, event_buffer = event_buffer.split(b'\n\n', 1)
                    if not event.startswith(b'data: '):
                        raise AssertionError('invalid SSE event')
                    data = event[6:]
                    if data == b'[DONE]':
                        result['done'] += 1
                        continue
                    check(result['done'] == 0, 'event after DONE')
                    value = json.loads(data)
                    choice = value['choices'][0]
                    if choice.get('finish_reason') is not None:
                        result['finish'].append(choice['finish_reason'])
                    text = choice.get('delta', {}).get('content')
                    if text:
                        content.append(text)
                        result['content_times'].append(now)
                        if on_content:
                            action = on_content(sock)
                            on_content = None
                            if action == 'cancel':
                                result['cancelled'] = True
                                return result
            elif synthetic and on_content:
                action = on_content(sock)
                on_content = None
                if action == 'cancel':
                    result['cancelled'] = True
                    return result
            if slow:
                time.sleep(.02 if not synthetic else .001)
    except BaseException as error:
        result['error'] = repr(error)
        result['error_type'] = type(error).__name__
        result['interrupted'] = isinstance(error, (KeyboardInterrupt, SystemExit))
        # 已有网络/HTTP失败仍返回失败结果；其他异常及连接失败保留传播。
        if sock is None or not isinstance(error, (OSError, http.client.HTTPException)):
            error.integration_result = result
            raise
    finally:
        result['end'] = time.monotonic()
        result['bytes'] = len(received)
        result['body_sha256'] = hashlib.sha256(received).hexdigest()
        try:
            result['text'] = ''.join(content)
        except BaseException as error:
            result['error'] = repr(error)
            result['error_type'] = type(error).__name__
            error.integration_result = result
            raise
        finally:
            if not synthetic:
                result['body'] = received.decode('utf-8', errors='replace')
            if response:
                # begin失败时仍保留已知状态和原始头，不覆盖已经采样的字段。
                result.setdefault('headers', response.getheaders())
                result.setdefault('raw_head', response.raw_head.decode('latin1'))
                if result['status'] is None:
                    result['status'] = response.status
            try:
                if response:
                    response.close()
            finally:
                if sock:
                    sock.close()
    return result



_ATTEMPT_IDS = itertools.count()


def recorded_exchange(port, request, path, metadata, lock=None, validator=None, **options):
    """唯一落盘出口；失败记录后继续原异常传播，不把失败变成成功。"""
    result = {'attempt_id': next(_ATTEMPT_IDS), **metadata}
    try:
        result.update(exchange(port, request, **options))
        if validator:
            validator(result)
        return result
    except BaseException as error:
        result.update(getattr(error, 'integration_result', {}))
        result['error'] = repr(error)
        result['error_type'] = type(error).__name__
        result['interrupted'] = isinstance(error, (KeyboardInterrupt, SystemExit))
        raise
    finally:
        if path is not None:
            with lock if lock is not None else nullcontext():
                append(path, result)


def validate_real(result, stream, long=False):
    check(result['status'] == 200 and result['complete'] and not result['error'], f'real HTTP failure {result}')
    types = [value for key, value in result['headers'] if key.lower() == 'content-type']
    check(len(types) == 1, 'unique content type')
    if stream:
        check(types[0].lower() in ('text/event-stream', 'text/event-stream; charset=utf-8'), 'SSE type')
        check(result['done'] == 1 and len(result['finish']) == 1 and result['text'].strip(), 'SSE terminal/content')
        check(result['content_times'][0] < result['end'], 'incremental content observed')
        if long:
            check(len(result['content_times']) >= 16, 'long stream <16 content increments')
    else:
        value = json.loads(result['body'])
        check(value['choices'][0]['message']['content'].strip(), 'empty assistant text')
        check(value['choices'][0]['finish_reason'] in ('stop', 'length'), 'finish reason')


def reset_client(sock):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
    return 'cancel'


class Sampler:
    def __init__(self, host, backend, output):
        self.host, self.backend, self.output = host, backend, output
        self.stop_event = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            while not self.stop_event.is_set():
                backend = self.backend.owned if self.backend else None
                append(self.output, {'time': time.monotonic(),
                    'gateway': process_stats(self.host.owned.process.pid),
                    'backend': process_stats(backend.process.pid) if backend else None})
                self.stop_event.wait(1)
        except BaseException as error:
            self.error = error

    def stop(self):
        self.stop_event.set()
        self.thread.join(2)
        if self.error:
            raise self.error


def validate_rss(baseline, drains):
    check(len(drains) >= 5, 'at least five drained samples')
    check(max(point['rss'] for point in drains) <= baseline + 32 * 1024**2, 'RSS B+32MiB')
    last = [point['rss'] for point in drains[-5:]]
    check(max(last) - min(last) <= 8 * 1024**2, 'RSS last five span 8MiB')


def interrupt_run(signum, frame):
    raise KeyboardInterrupt(f'integration signal {signum}')


def install_interrupt_handlers():
    signal.signal(signal.SIGTERM, interrupt_run)
    signal.signal(signal.SIGINT, interrupt_run)


def source_identity():
    paths = [ROOT / 'CMakeLists.txt', ROOT / 'CMakePresets.json']
    for directory in ('src', 'tests', 'config'):
        paths.extend(path for path in (ROOT / directory).rglob('*')
                     if path.is_file() and path.suffix in ('.h', '.cpp', '.py', '.json'))
    return {str(path.relative_to(ROOT)): sha(path) for path in sorted(paths)}
