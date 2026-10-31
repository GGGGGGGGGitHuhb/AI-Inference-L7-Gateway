"""Independent asynchronous persistent fixture with bounded connection admission."""
import argparse
import asyncio
import json
import signal
import socket
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "capacity"))
from Common import Chunks, payload, now, write


async def serve(args):
    out = Chunks(args.output, 'backend', args.limit, row_limit=192)
    endpoints = Chunks(args.output, 'backend-endpoints', args.limit, row_limit=192)
    active = set()
    errors = []
    counters = {'accepts': 0, 'requests': 0, 'rejected_connections': 0, 'empty_connections': 0}
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async def handle(reader, writer):
        counters['accepts'] += 1
        conn = counters['accepts']
        handled_requests = 0
        task = asyncio.current_task()
        if len(active) >= 512:
            counters['rejected_connections'] += 1
            writer.close()
            return
        active.add(task)
        sock = writer.get_extra_info('socket')
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, args.nodelay)
        try:
            while not stop.is_set():
                identity, rx, tx, begin = None, 0, 0, now()
                try:
                    async with asyncio.timeout(6):
                        head = await reader.readuntil(b'\r\n\r\n')
                        if len(head) > 8192:
                            raise ValueError('large request header')
                        fields = {}
                        for line in head.split(b'\r\n')[1:-2]:
                            key, value = line.split(b':', 1)
                            fields[key.lower()] = value.strip()
                        length = int(fields.get(b'content-length', 0))
                        if not 0 < length <= 4096:
                            raise ValueError('invalid request length')
                        raw = await reader.readexactly(length)
                        rx = len(head) + len(raw)
                        identity = json.loads(raw)['messages'][0]['content']
                        endpoints.row([identity, conn, begin, now(), writer.get_extra_info('sockname'), writer.get_extra_info('peername')])
                        counters['requests'] += 1
                        handled_requests += 1
                        content = payload(identity, args.workload)
                        if args.fault == 'bad_body':
                            content = b'!' + content[1:]
                        if args.fault == 'timeout':
                            await asyncio.sleep(6)
                        keep = fields.get(b'connection', b'').lower() != b'close'
                        status = b'503 Service Unavailable' if args.fault == 'overload' else b'200 OK'
                        response = (b'HTTP/1.1 ' + status + b'\r\nContent-Type: ' +
                                    (b'text/event-stream' if args.workload == 'S' else b'application/json') +
                                    b'\r\nContent-Length: ' + str(len(content)).encode() + b'\r\nConnection: ' +
                                    (b'keep-alive' if keep else b'close') + b'\r\n\r\n')
                        writer.write(response)
                        tx += len(response)
                        chunks = [content] if args.workload == 'A' else [content[i:i+1024] for i in range(0, len(content), 1024)]
                        for index, chunk in enumerate(chunks):
                            if index:
                                await asyncio.sleep(.002)
                            writer.write(chunk)
                            tx += len(chunk)
                            await writer.drain()
                        out.row([identity, conn, begin, now(), rx, tx, 'complete'])
                        if not keep:
                            break
                except asyncio.CancelledError:
                    if identity:
                        out.row([identity, conn, begin, now(), rx, tx, 'interrupted'])
                    raise
                except asyncio.IncompleteReadError as error:
                    if identity or error.partial:
                        out.row([identity, conn, begin, now(), rx, tx, 'eof'])
                    break
                except Exception as error:
                    out.row([identity, conn, begin, now(), rx, tx, type(error).__name__])
                    break
        except Exception as error:
            if not errors:
                errors.append(repr(error))
            stop.set()
        finally:
            if not handled_requests:
                counters['empty_connections'] += 1
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass
            active.discard(task)

    server = await asyncio.start_server(handle, '127.0.0.1', args.port, limit=8192, backlog=512)
    print('READY', flush=True)
    await stop.wait()
    server.close()
    for task in list(active):
        task.cancel()
    await asyncio.gather(*active, return_exceptions=True)
    await server.wait_closed()
    out.close()
    endpoints.close()
    write(args.output + '/backend-summary.json', counters | {'errors': errors}, limit=16384)
    return 1 if errors else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--workload', choices=['A', 'S'], required=True)
    parser.add_argument('--limit', type=int, required=True)
    parser.add_argument('--nodelay', type=int, default=1)
    parser.add_argument('--fault', default='none')
    raise SystemExit(asyncio.run(serve(parser.parse_args())))
