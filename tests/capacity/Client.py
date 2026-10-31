"""Open-loop asyncio generator: bounded tasks, absolute deadlines, every planned ID."""
import argparse
import asyncio
import hashlib
import json
import re
import signal
from Common import Chunks, COLUMNS, now, payload, request, write


class ProtocolError(Exception):
    pass


class Response:
    def __init__(self, reader, row):
        self.reader, self.row = reader, row
        self.buffer = bytearray()

    async def receive(self):
        data = await self.reader.read(32768)
        if data:
            self.row['rx'] += len(data)
            self.row['wire'] = self.row['wire'] or now()
            self.buffer.extend(data)
        return bool(data)

    async def exact(self, length):
        while len(self.buffer) < length:
            if not await self.receive():
                raise ProtocolError('premature EOF')
        value = bytes(self.buffer[:length])
        del self.buffer[:length]
        return value

    async def line(self, delimiter=b'\r\n', cap=8192):
        while True:
            position = self.buffer.find(delimiter)
            if position >= 0:
                if position > cap:
                    raise ProtocolError('line bound')
                return await self.exact(position + len(delimiter))
            if len(self.buffer) > cap:
                raise ProtocolError('missing delimiter')
            if not await self.receive():
                if self.row['rx'] == 0:
                    raise ConnectionError('EOF before any response')
                raise ProtocolError('missing delimiter')

    async def read(self):
        head = await self.line(b'\r\n\r\n')
        lines = head[:-4].split(b'\r\n')
        status = lines[0].split(b' ')
        if len(status) < 2 or status[0] != b'HTTP/1.1':
            raise ProtocolError('status line')
        self.row['status'] = int(status[1])
        headers = {}
        for line in lines[1:]:
            key, value = line.split(b':', 1)
            key = key.lower()
            if key in headers:
                raise ProtocolError('duplicate header')
            headers[key] = value.strip().lower()
        chunked = headers.get(b'transfer-encoding') == b'chunked'
        if b'transfer-encoding' in headers and not chunked:
            raise ProtocolError('unknown transfer coding')
        if chunked and b'content-length' in headers:
            raise ProtocolError('ambiguous frame')
        result = bytearray()
        if chunked:
            while True:
                token = (await self.line())[:-2]
                if not re.fullmatch(rb'[0-9A-Fa-f]+', token):
                    raise ProtocolError('invalid chunk length')
                length = int(token, 16)
                if length == 0:
                    if await self.line() != b'\r\n':
                        raise ProtocolError('unexpected trailer')
                    break
                if length < 0 or len(result) + length > 16384:
                    raise ProtocolError('body bound')
                # Mark body arrival before waiting for the whole chunk.
                if not self.buffer and not await self.receive():
                    raise ProtocolError('body missing')
                self.row['body'] = self.row['body'] or now()
                result.extend(await self.exact(length))
                if await self.exact(2) != b'\r\n':
                    raise ProtocolError('chunk terminator')
        elif b'content-length' in headers:
            if not re.fullmatch(rb'[0-9]+', headers[b'content-length']):
                raise ProtocolError('invalid content length')
            length = int(headers[b'content-length'])
            if not 0 <= length <= 16384:
                raise ProtocolError('body bound')
            if length:
                if not self.buffer and not await self.receive():
                    raise ProtocolError('body missing')
                self.row['body'] = now()
                result.extend(await self.exact(length))
        else:
            raise ProtocolError('unframed response')
        self.row['http'] = now()
        if self.buffer or await self.receive():
            raise ProtocolError('trailing data')
        self.row['eof'] = now()
        return bytes(result)


async def run(args):
    spec = json.loads(open(args.spec).read())
    output = Chunks(args.output, 'client-' + str(args.worker), spec['client_bytes'], row_limit=512)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    active, errors = set(), []
    def done(task):
        active.discard(task)
        if not task.cancelled() and task.exception() is not None:
            if not errors:
                errors.append(repr(task.exception()))
            stop.set()

    peak = 0
    interrupted = False

    def emit(row):
        output.row([row.get(key) for key in COLUMNS])

    def blank(identity, phase, scheduled):
        return dict.fromkeys(COLUMNS) | dict(id=identity, phase=phase, scheduled=scheduled, outcome='not_started', tx=0, rx=0)

    async def attempt(row, port):
        writer = None
        row['dispatch'] = now()
        try:
            if row['dispatch'] - row['scheduled'] > 50_000_000:
                row['outcome'] = 'not_sent'
                return
            async with asyncio.timeout_at(loop.time() + max(0, (row['scheduled'] + 5_000_000_000 - now()) / 1e9)):
                reader, writer = await asyncio.open_connection('127.0.0.1', port, limit=32768)
                row['connect'] = now()
                data = request(row['id'], spec['workload'])
                writer.write(data)
                row['tx'] = len(data)  # bytes accepted by asyncio transport; wire not claimed
                await writer.drain()
                row['send'] = now()
                content = await Response(reader, row).read()
                row['digest'] = hashlib.sha256(content).hexdigest()
                if row['status'] != 200:
                    row['outcome'] = 'http_rejection'
                elif content != payload(row['id'], spec['workload']):
                    row['outcome'] = 'body_error'
                else:
                    row['outcome'] = 'success'
        except TimeoutError:
            row['outcome'] = 'client_deadline'
        except asyncio.CancelledError:
            row['outcome'] = 'interrupted'
        except (ProtocolError, ValueError) as error:
            row['outcome'], row['error'] = 'protocol_error', str(error)
        except (ConnectionError, OSError) as error:
            row['outcome'], row['error'] = 'transport_failure', str(error)
        finally:
            if writer:
                writer.close()
                try:
                    async with asyncio.timeout(.1):
                        await writer.wait_closed()
                except (TimeoutError, ConnectionError, OSError):
                    pass
            row['closed'] = now()
            emit(row)

    try:
        for phase, duration, start in [('w', spec['warm'], spec['start']), ('f', spec['duration'], spec['measure_start'])]:
            count = int(spec['rate'] * duration)
            for index in range(args.worker, count, spec['workers']):
                identity = f"{spec['id']}-{phase}-{index}"
                scheduled = start + index * 1_000_000_000 // spec['rate']
                row = blank(identity, phase, scheduled)
                if stop.is_set():
                    interrupted = True
                    row['closed'] = now()
                    emit(row)
                    continue
                delay = (scheduled - now()) / 1e9
                if delay > 0:
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=delay)
                    except TimeoutError:
                        pass
                if stop.is_set():
                    interrupted = True
                    row['closed'] = now()
                    emit(row)
                    continue
                if len(active) >= spec['slots'] // spec['workers'] or now() - scheduled > 50_000_000:
                    row['outcome'] = 'not_sent'
                    row['dispatch'], row['closed'] = now(), now()
                    emit(row)
                    continue
                task = asyncio.create_task(attempt(row, spec['targets'][index % len(spec['targets'])]))
                active.add(task)
                task.add_done_callback(done)
                peak = max(peak, len(active))
            if stop.is_set():
                for task in list(active):
                    task.cancel()
            if active:
                await asyncio.gather(*active)
    finally:
        for task in list(active):
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)
        output.close()
    write(args.output + f'/client-{args.worker}-summary.json', {'peak': peak, 'interrupted': interrupted, 'errors': errors}, limit=16384)
    return 2 if interrupted or errors else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--worker', type=int, default=0)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
