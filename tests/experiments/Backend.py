"""One bounded synthetic process: <=256 handlers, <=256 per-cell summaries."""
import argparse
import http.server
import json
import signal
import socket
import threading
import time
from Client import PAYLOADS


class Server(http.server.ThreadingHTTPServer):
    daemon_threads=True
    block_on_close=False
    request_queue_size=128

    def __init__(self,port,group,delay,nodelay):
        super().__init__(('127.0.0.1',port),Handler)
        self.group=group;self.delay=delay;self.nodelay=nodelay
        self.lock=threading.RLock();self.accepts=0;self.rows=[];self.sockets=set()

    def get_request(self):
        connection,address=super().get_request()
        connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,int(self.nodelay))
        with self.lock:
            if len(self.sockets)>=128:connection.close();raise OSError('handler cap')
            self.accepts+=1;self.sockets.add(connection)
        return connection,address


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'

    def log_message(self,*args):pass

    def finish(self):
        try:super().finish()
        finally:
            with self.server.lock:self.server.sockets.discard(self.connection)

    def do_POST(self):
        row={'id':self.headers.get('X-Experiment-Id'),'handler_start':time.monotonic_ns(),
             'nodelay':self.connection.getsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY)}
        error=None
        try:
            length=int(self.headers['Content-Length'])
            if length>65536:raise ValueError('request bound')
            json.loads(self.rfile.read(length))
            index=int(row['id'].rsplit('-',1)[1]);long=self.server.group=='H' and index%4==3
            if self.server.delay:time.sleep(self.server.delay*(4 if long else 1))
            body=PAYLOADS[self.server.group]
            close=self.headers.get('Connection','').lower()=='close';self.close_connection=close
            self.send_response(200);self.send_header('Content-Type','application/json' if self.server.group=='A' else 'text/event-stream')
            self.send_header('Connection','close' if close else 'keep-alive')
            self.send_header('Content-Length' if self.server.group=='A' else 'Transfer-Encoding',str(len(body)) if self.server.group=='A' else 'chunked')
            self.end_headers();row['head_sent']=time.monotonic_ns();row['first_send']=time.monotonic_ns()
            if self.server.group=='A':self.wfile.write(body)
            else:
                for offset in range(0,len(body),16384):
                    part=body[offset:offset+16384];self.wfile.write(f'{len(part):x}\r\n'.encode()+part+b'\r\n')
                self.wfile.write(b'0\r\n\r\n')
            row['last_send']=time.monotonic_ns();row['close']=close
        except BaseException as failure:error=repr(failure)[:512]
        finally:
            row['ended']=time.monotonic_ns();row['error']=error
            with self.server.lock:
                if len(self.server.rows)>=256:raise RuntimeError('backend record cap')
                self.server.rows.append(row)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);parser.add_argument('--group',required=True)
    parser.add_argument('--delay',type=float,default=0);parser.add_argument('--nodelay',type=int,default=0);parser.add_argument('--output',required=True)
    args=parser.parse_args();stopping=threading.Event();server=Server(args.port,args.group,args.delay,args.nodelay)
    def stop(*args):stopping.set()
    def checkpoint(*args):
        with server.lock:
            with open(args_path+'.warmup','w') as out:json.dump({'accepts':server.accepts,'requests':len(server.rows)},out)
    args_path=args.output
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGUSR1,checkpoint);server.timeout=.02
    print('READY',flush=True)
    try:
        while not stopping.is_set():server.handle_request()
    finally:
        with server.lock:
            for sock in server.sockets:
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
        server.server_close()
        with server.lock:
            with open(args.output,'w') as out:json.dump({'accepts':server.accepts,'requests':server.rows},out)


if __name__=='__main__':main()
