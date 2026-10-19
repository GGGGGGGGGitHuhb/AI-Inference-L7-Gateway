import json
import os
from pathlib import Path
import selectors
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
from support.ProxyBackend import ProxyBackend, BODY

EXE = sys.argv[1]
PROMPT = b'{"model":"demo","messages":[{"role":"user","content":"unique-private-prompt"}]}'
checks = 0

def check(condition, detail=""):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(detail)

def wire(body=PROMPT, extra=b"", chunked=False):
    prefix=b"POST /v1/chat/completions HTTP/1.1\r\nHost: client\r\nContent-Type: application/json\r\nAuthorization: unique-private-secret\r\n"+extra
    if chunked:
        return prefix+b"Transfer-Encoding: chunked\r\n\r\n"+hex(len(body))[2:].encode()+b";key = value\r\n"+body+b"\r\n0\r\n\r\n"
    return prefix+b"Content-Length: "+str(len(body)).encode()+b"\r\n\r\n"+body

def receive(connection):
    result=bytearray()
    while True:
        try:
            part=connection.recv(65536)
        except ConnectionResetError:
            break
        if not part:
            break
        result.extend(part)
    return bytes(result)

class Gateway:
    def __init__(self, temporary, backend, **overrides):
        config={"listen_port":0,"upstream_address":"127.0.0.1","upstream_port":backend.port}
        config.update(overrides)
        handle=tempfile.NamedTemporaryFile(mode="w",dir=temporary,delete=False)
        json.dump(config,handle);handle.close()
        self.process=subprocess.Popen([EXE,"--config",handle.name],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout,selectors.EVENT_READ)
                check(bool(selector.select(5)),"READY timeout")
            ready=self.process.stdout.readline()
            check(ready.startswith("READY 127.0.0.1:"),(ready,self.process.poll()))
            self.port=int(ready.rsplit(":",1)[1])
            self.ready=ready
        except BaseException:
            self.process.kill()
            self.process.communicate(timeout=3)
            backend.close()
            raise

    def client(self):
        return socket.create_connection(("127.0.0.1",self.port),timeout=4)

    def close(self, expected=0):
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
        try:
            stdout,stderr=self.process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill();self.process.communicate(timeout=3)
            raise AssertionError("gateway failed to stop")
        check(self.process.returncode==expected,(self.process.returncode,stderr))
        check("unique-private" not in self.ready+stdout+stderr,"sensitive log")
        check("AddressSanitizer" not in stderr and "runtime error:" not in stderr,stderr)
        try:
            survivor=self.client()
        except OSError:
            pass
        else:
            survivor.close();raise AssertionError("listener survived")

def response_case(temporary,mode,expected=200,fragment=False,halfclose=False,chunked=False,body=PROMPT):
    backend=ProxyBackend(mode)
    gateway=Gateway(temporary,backend)
    try:
        with gateway.client() as client:
            request=wire(body,b"Connection: X-Hop\r\nX-Hop: remove\r\nX-Keep: one\r\nX-Keep: two\r\n",chunked)
            if fragment:
                for offset in range(0,len(request),3):client.sendall(request[offset:offset+3])
            else:client.sendall(request)
            if halfclose:client.shutdown(socket.SHUT_WR)
            result=receive(client)
        check(result.startswith(b"HTTP/1.1 "+str(expected).encode()),(mode,result[:150]))
        check(result.count(b"HTTP/1.1 ")==1,mode)
        headers,response=result.split(b"\r\n\r\n",1)
        check(b"Connection: close" in headers,mode)
        if mode not in ["malformed","truncated","600","sse"]:
            check(response==(b"" if mode in ["204","304"] else BODY),mode)
            check(b"x-hop:" not in headers.lower(),mode)
        check(backend.request_seen.wait(1),mode)
        upstream_headers,upstream_body=backend.requests[0]
        if mode!="early":check(upstream_body==body,mode)
        check(b"unique-private-secret" not in upstream_headers,mode)
        check(b"Host: 127.0.0.1:"+str(backend.port).encode() in upstream_headers,mode)
        check(b"Connection: close" not in upstream_headers,mode) # S3 upstream policy is independent of downstream close.
        check(b"x-keep: one\r\nx-keep: two" in upstream_headers.lower(),mode)
    finally:
        gateway.close();backend.close()

def bad_requests(temporary):
    backend=ProxyBackend();gateway=Gateway(temporary,backend)
    try:
        cases=[(wire(b"{}"),400),(wire().replace(b"/v1/chat/completions",b"/other"),404),(wire().replace(b"POST ",b"GET "),405),(b"POST /v1/chat/completions HTTP/1.1\r\nHost: h\r\nExpect: 100-continue\r\nContent-Length: 100\r\n\r\n",417),(wire().replace(b"application/json",b"text/plain"),415),(b"POST / HTTP/1.1\r\nHost: h\r\nContent-Length: 1048577\r\n\r\n",413),(wire(b"abc")[:-1],400)]
        for request,expected in cases:
            with gateway.client() as client:
                client.sendall(request)
                if request==cases[-1][0]:client.shutdown(socket.SHUT_WR)
                result=receive(client)
            check(result.startswith(b"HTTP/1.1 "+str(expected).encode()),(expected,result[:100]))
            if expected==405:check(b"Allow: POST" in result)
        check(backend.accepted==0,"bad request contacted upstream")
    finally:
        try:gateway.close()
        finally:backend.close()

def pipeline_and_limits(temporary):
    backend=ProxyBackend(delay=.04);gateway=Gateway(temporary,backend,max_connections=2,max_reserved_bytes=33554432)
    try:
        for same_batch in [True,False]:
            before=backend.accepted
            with gateway.client() as client:
                client.sendall(wire()+(wire() if same_batch else b""))
                if not same_batch:
                    time.sleep(.01);client.sendall(wire())
                result=receive(client)
            check(result.startswith(b"HTTP/1.1 200"))
            check(backend.accepted==before+1,"second request dispatched")
        first=gateway.client();second=gateway.client()
        try:
            first.sendall(b"POST /");second.sendall(b"POST /")
            third=gateway.client()
            try:check(receive(third)==b"","capacity client was retained")
            finally:third.close()
        finally:
            for connection in [first,second]:
                connection.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack("ii",1,0));connection.close()
        time.sleep(.03)
        with gateway.client() as client:
            client.sendall(wire());check(receive(client).startswith(b"HTTP/1.1 200"))
    finally:
        try:gateway.close()
        finally:backend.close()
    backend=ProxyBackend();gateway=Gateway(temporary,backend,max_connections=2,max_reserved_bytes=16777216)
    first=gateway.client()
    try:
        first.sendall(b"POST /")
        with gateway.client() as client:check(receive(client)==b"","reservation limit")
    finally:
        first.close()
        try:gateway.close()
        finally:backend.close()

def timeouts_and_shutdown(temporary):
    backend=ProxyBackend(delay=.3)
    gateway=Gateway(temporary,backend,timeouts_ms={"request":70,"response":70,"total":1000,"shutdown":80})
    try:
        with gateway.client() as client:
            started=time.monotonic();client.sendall(b"POST /");result=receive(client)
            check(b"408" in result[:20] and b"request_timeout" in result,result)
            elapsed=time.monotonic()-started
            print("request deadline elapsed_seconds",elapsed)
            check(elapsed<2)
        with gateway.client() as client:
            client.sendall(wire());result=receive(client)
            check(b"504" in result[:20] and b"response_timeout" in result,result)
        with gateway.client() as client:
            client.sendall(b"POST /");gateway.process.send_signal(signal.SIGTERM)
            result=receive(client);check(time.monotonic()>0)
        gateway.process.wait(timeout=2)
    finally:
        try:gateway.close()
        finally:backend.close()
    for second_signal in [False,True]:
        backend=ProxyBackend(delay=.05);gateway=Gateway(temporary,backend,timeouts_ms={"shutdown":400 if second_signal else 150})
        try:
            with gateway.client() as client:
                if second_signal:client.sendall(b"POST /")
                else:client.sendall(wire());check(backend.request_seen.wait(1))
                gateway.process.send_signal(signal.SIGTERM)
                if second_signal:
                    time.sleep(.03);gateway.process.send_signal(signal.SIGINT)
                result=receive(client)
                if not second_signal:check(result.startswith(b"HTTP/1.1 200"),result)
            gateway.process.wait(timeout=2)
        finally:
            try:gateway.close()
            finally:backend.close()
    backend=ProxyBackend();gateway=Gateway(temporary,backend,timeouts_ms={"shutdown":60})
    client=gateway.client()
    try:
        client.sendall(b"POST /");time.sleep(.02)
        start=time.monotonic();gateway.process.send_signal(signal.SIGTERM)
        check(receive(client)==b"")
        gateway.process.wait(timeout=2)
        elapsed=time.monotonic()-start
        print("shutdown deadline elapsed_seconds",elapsed)
        check(elapsed<1)
    finally:
        client.close()
        try:gateway.close()
        finally:backend.close()

def config_cases(temporary):
    check(subprocess.run([EXE,"--help"],capture_output=True,timeout=3).returncode==0)
    for args in [[],["--bad"],["--config","x","--config","y"]]:
        check(subprocess.run([EXE]+args,capture_output=True,timeout=3).returncode==2)
    base={"upstream_address":"127.0.0.1","upstream_port":9,"listen_port":0}
    invalid=[{},[],dict(base,unknown=1),dict(base,upstream_port=True),dict(base,upstream_port=9.0),dict(base,listen_address="localhost"),dict(base,upstream_address="0.0.0.0"),dict(base,upstream_port=0),dict(base,upstream_port=65536),dict(base,max_connections=0),dict(base,max_connections=257),dict(base,max_reserved_bytes=16777215),dict(base,max_reserved_bytes=4294967297),dict(base,timeouts_ms={"request":9}),dict(base,timeouts_ms={"request":300001}),dict(base,timeouts_ms={"bad":10}),dict(base,timeouts_ms={"request":True}),dict(base,listen_port=9)]
    contents=[json.dumps(value) for value in invalid]+['{"upstream_address":"127.0.0.1","upstream_port":9,"upstream_port":10}','{"upstream_address":"127.0.0.1","upstream_port":9,"timeouts_ms":{"total":10,"total":20}}'," "*65537]
    for content in contents:
        path=Path(temporary)/"invalid.json";path.write_text(content)
        outcome=subprocess.run([EXE,"--config",str(path)],capture_output=True,timeout=3)
        check(outcome.returncode==2 and b"READY" not in outcome.stdout,(content[:80],outcome))

def stress_boundaries(temporary):
    backend=ProxyBackend(response_body=b"z"*4194304)
    gateway=Gateway(temporary,backend)
    try:
        with gateway.client() as client:
            client.sendall(wire())
            check(backend.request_seen.wait(1))
            time.sleep(.03)
            result=receive(client)
            headers,body=result.split(b"\r\n\r\n",1)
            check(headers.startswith(b"HTTP/1.1 200") and body==b"z"*4194304,"maximum response/slow client")
        backend.response_body=b"z"*4194305
        with gateway.client() as client:
            client.sendall(wire());result=receive(client)
            check(result.startswith(b"HTTP/1.1 502"),"oversize upstream")
    finally:
        try:gateway.close()
        finally:backend.close()
    backend=ProxyBackend(delay=.12);gateway=Gateway(temporary,backend,timeouts_ms={"request":90,"total":1000})
    try:
        hot=gateway.client();hot.sendall(wire());check(backend.request_seen.wait(1))
        hot.setblocking(False)
        with gateway.client() as slow:
            slow.sendall(b"POST /")
            end=time.monotonic()+.15
            while time.monotonic()<end:
                try:hot.send(b"ignored"*8000)
                except (BlockingIOError,BrokenPipeError,ConnectionResetError):pass
                time.sleep(.001)
            result=receive(slow)
            check(result.startswith(b"HTTP/1.1 408"),"hot sender starved request timer")
        hot.setblocking(True);hot.settimeout(3);result=receive(hot);hot.close()
        check(result.startswith(b"HTTP/1.1 200"),("extra bytes cancelled first request",result[:200]))
        check(backend.accepted==1,"hot input redispatched")
    finally:
        try:gateway.close()
        finally:backend.close()
    backend=ProxyBackend(delay=.2);gateway=Gateway(temporary,backend)
    try:
        cancelled=gateway.client();cancelled.sendall(wire());check(backend.request_seen.wait(1))
        cancelled.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack("ii",1,0));cancelled.close()
        with gateway.client() as client:
            client.sendall(wire());check(receive(client).startswith(b"HTTP/1.1 200"),"RST affected healthy request")
    finally:
        try:gateway.close()
        finally:backend.close()
    backend=ProxyBackend();backend.close();gateway=Gateway(temporary,backend)
    try:
        with gateway.client() as client:
            client.sendall(wire());check(receive(client).startswith(b"HTTP/1.1 502"),"real connect refusal")
    finally:gateway.close()
    backend=ProxyBackend(delay=.2);gateway=Gateway(temporary,backend,timeouts_ms={"total":50,"response":500})
    try:
        with gateway.client() as client:
            client.sendall(wire());result=receive(client)
            check(b"504" in result[:20] and b"total_timeout" in result,result)
    finally:
        try:gateway.close()
        finally:backend.close()
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1",0));occupied.listen(1)
        path=Path(temporary)/"occupied.json"
        path.write_text(json.dumps({"listen_port":occupied.getsockname()[1],"upstream_address":"127.0.0.1","upstream_port":9}))
        outcome=subprocess.run([EXE,"--config",str(path)],capture_output=True,timeout=3)
        check(outcome.returncode==1 and b"READY" not in outcome.stdout,"bind failure")

def closing_handshakes(temporary):
    for error in [False, True]:
        backend=ProxyBackend(delay=.08)
        gateway=Gateway(temporary,backend,max_connections=1)
        try:
            with gateway.client() as client:
                request=wire(extra=b"Expect: 100-continue\r\n") if error else wire()
                client.sendall(request+b"before-output"*1000)
                if not error:check(backend.request_seen.wait(1))
                result=receive(client) # EOF proves gateway SHUT_WR after all output.
                header,body=result.split(b"\r\n\r\n",1)
                expected=b'{"error":{"code":"unsupported_expect","message":"Request rejected"}}' if error else BODY
                check(header.startswith(b"HTTP/1.1 417" if error else b"HTTP/1.1 200"))
                check(body==expected,(error,body))
                check(result.count(b"HTTP/1.1 ")==1)
                check(b"Content-Length: "+str(len(expected)).encode()+b"\r\n" in header+b"\r\n")
                # The peer is still writable after output EOF; capacity remains occupied.
                client.sendall(b"after-output"*10000)
                with gateway.client() as rejected:check(receive(rejected)==b"","closing slot released early")
                client.shutdown(socket.SHUT_WR)
                check(client.recv(1)==b"")
            check(backend.accepted==(0 if error else 1),"second request dispatched while closing")
        finally:
            try:gateway.close()
            finally:backend.close()
    backend=ProxyBackend();gateway=Gateway(temporary,backend,max_connections=1)
    try:
        with gateway.client() as client:
            client.sendall(wire());check(receive(client).endswith(BODY))
            client.setblocking(False)
            started=time.monotonic();closed=False
            while time.monotonic()-started<1.6:
                try:client.send(b"drain"*2000)
                except BlockingIOError:pass
                except OSError:
                    closed=True;break
                time.sleep(.001)
            elapsed=time.monotonic()-started
            print("closing hot drain elapsed_seconds",elapsed)
            check(closed and elapsed<1.6,"closing deadline refreshed by input")
        with gateway.client() as healthy:
            healthy.sendall(wire());check(receive(healthy).endswith(BODY))
        check(backend.accepted==2,"closing input redispatched")
    finally:
        try:gateway.close()
        finally:backend.close()
    # Keep the peer write side open after gateway EOF; signal deadline must win.
    for second in [False,True]:
        backend=ProxyBackend();gateway=Gateway(temporary,backend,timeouts_ms={"shutdown":70})
        try:
            with gateway.client() as client:
                client.sendall(wire());check(receive(client).endswith(BODY))
                client.sendall(b"still-open")
                started=time.monotonic();gateway.process.send_signal(signal.SIGTERM)
                if second:
                    time.sleep(.02);gateway.process.send_signal(signal.SIGINT)
                gateway.process.wait(timeout=2)
                elapsed=time.monotonic()-started
                print("closing stop elapsed_seconds",elapsed,"second_signal",second)
                check(elapsed<1)
        finally:
            try:gateway.close()
            finally:backend.close()

with tempfile.TemporaryDirectory(prefix="gateway-s2-",dir=os.environ["TMPDIR"]) as temporary:
    config_cases(temporary)
    for mode in ["fixed","chunked","eof","informational","204","304","400","500","471","599","fragmented","slow_read"]:
        response_case(temporary,mode,int(mode) if mode.isdigit() else 200,fragment=mode=="fragmented",halfclose=mode=="fixed",chunked=mode=="chunked")
    for mode in ["malformed","truncated","600","sse"]:response_case(temporary,mode,502)
    large=json.dumps({"model":"demo","messages":[{"role":"user","content":"x"*900000}]}).encode()
    response_case(temporary,"early",413,body=large)
    prefix=b'{"model":"demo","messages":[{"role":"user","content":"'
    suffix=b'"}]}'
    maximum=prefix+b"x"*(1048576-len(prefix)-len(suffix))+suffix
    response_case(temporary,"slow_read",body=maximum)
    bad_requests(temporary)
    pipeline_and_limits(temporary)
    timeouts_and_shutdown(temporary)
    stress_boundaries(temporary)
    closing_handshakes(temporary)
print("Gateway E2E checks:",checks,"; real socket/owned process scenarios passed")
