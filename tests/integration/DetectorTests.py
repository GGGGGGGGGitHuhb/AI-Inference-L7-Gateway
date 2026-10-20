"""快速负面对照。每个子进程必须非零；不依赖模型。"""
import argparse
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
from Support import Backend, Host, check, exchange, gateway_config, save, validate_rss


def fail_case(case, host, output):
    if case == 'missing-model':
        Backend(output / 'missing', output)
    elif case == 'bad-hash':
        (output / 'asset-verification.json').write_text('[{"path":"CMakeLists.txt","bytes":1,"sha256":"bad"}]')
        Backend(output, output)
    elif case == 'port-conflict':
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); listener.listen()
            config = gateway_config(1, True)
            config['listen_port'] = listener.getsockname()[1]
            Host(host, config, output)
    elif case == 'startup-exit':
        Host('/bin/false', gateway_config(1, True), output)
    elif case in ('bad-http', 'short-body', 'timeout'):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); listener.listen()
            def serve():
                connection, _ = listener.accept()
                with connection:
                    connection.recv(65536)
                    if case == 'timeout':
                        connection.settimeout(.1)
                        try: connection.recv(1)
                        except TimeoutError: pass
                    else:
                        connection.sendall(b'invalid\r\n\r\n' if case == 'bad-http' else
                                           b'HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nabc')
            thread = threading.Thread(target=serve)
            thread.start()
            try:
                result = exchange(listener.getsockname()[1], {'stream': False}, timeout=.05 if case == 'timeout' else 2)
                check(result['complete'] and not result['error'], 'invalid response detected')
            finally:
                thread.join(2)
    elif case == 'nonzero-resource':
        fake = Host.__new__(Host)
        fake.path = output / 'snapshots.jsonl'; fake.cursor = 0; fake.maxima = {}; fake.port = 1
        fake.config = gateway_config(1, True)
        fake.path.write_text('{"reserved":67108865,"capacity":0,"pending":0,"peak_reserved":67108865,"peak_capacity":0}\n')
        fake.refresh()
    elif case == 'rss':
        validate_rss(0, [{'rss': 33 * 1024**2}] * 5)
    else:
        raise ValueError(case)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('host')
    parser.add_argument('--case')
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.case:
        fail_case(args.case, args.host, pathlib.Path(args.output))
        return
    with tempfile.TemporaryDirectory() as directory:
        for case in ('missing-model','bad-hash','port-conflict','startup-exit','bad-http',
                     'short-body','timeout','nonzero-resource','rss'):
            output = pathlib.Path(directory) / case; output.mkdir()
            result = subprocess.run([sys.executable, __file__, args.host, '--case', case,
                                     '--output', str(output)], capture_output=True, text=True, timeout=10)
            print(case, 'exit', result.returncode, result.stderr, flush=True)
            check(result.returncode != 0, f'negative detector unexpectedly passed: {case}')
        print('9 negative detectors passed')


if __name__ == '__main__':
    main()
