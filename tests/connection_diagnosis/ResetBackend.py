"""Negative-only peer: explicit complete synthetic request then SO_LINGER reset."""
import argparse
import asyncio
import json
from pathlib import Path
import signal
import socket
import struct
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'capacity'))
from Common import Chunks, now

async def run(args):
    stop=asyncio.Event();active=set();out=Chunks(args.output,'reset-peer',65536,row_limit=512)
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(sig,stop.set)
    async def handle(reader,writer):
        task=asyncio.current_task();active.add(task)
        try:
            async with asyncio.timeout(3):
                head=await reader.readuntil(b'\r\n\r\n')
                fields=dict(line.split(b':',1) for line in head.split(b'\r\n')[1:-2])
                body=await reader.readexactly(int(fields[b'Content-Length']))
                identity=json.loads(body)['messages'][0]['content']
                out.row([identity,now(),writer.get_extra_info('sockname'),writer.get_extra_info('peername'),'reset'])
                writer.get_extra_info('socket').setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
        except (asyncio.IncompleteReadError,TimeoutError):pass
        finally:
            writer.close();active.discard(task)
    server=await asyncio.start_server(handle,'127.0.0.1',args.port,limit=8192)
    print('READY',flush=True)
    await stop.wait();server.close();await server.wait_closed()
    for task in list(active):task.cancel()
    await asyncio.gather(*list(active),return_exceptions=True);out.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);parser.add_argument('--output',required=True)
    asyncio.run(run(parser.parse_args()))
