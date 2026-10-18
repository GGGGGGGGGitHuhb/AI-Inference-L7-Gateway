import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import sys
import tempfile

backend = Path(__file__).parent / "support" / "MockInferenceBackend.py"
parser = sys.argv[1]
fixture = b"GET /fixture HTTP/1.1\r\nHost: localhost\r\n\r\n"
with tempfile.TemporaryDirectory(prefix="mock-inference-", dir=os.environ["TMPDIR"]) as temporary:
    for scenario in ["fixed", "chunked", "delayed", "truncated", "malformed"]:
        record = Path(temporary) / (scenario + ".request")
        process = subprocess.Popen([sys.executable, str(backend), "--scenario", scenario, "--record", str(record)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(10):
                    raise RuntimeError("backend startup timeout")
            line = process.stdout.readline()
            if not line:
                raise RuntimeError(process.stderr.read())
            address = json.loads(line)
            assert address["host"] == "127.0.0.1"
            with socket.create_connection((address["host"], address["port"]), timeout=5) as connection:
                connection.sendall(fixture)
                wire = bytearray()
                while True:
                    fragment = connection.recv(13)
                    if not fragment:
                        break
                    wire.extend(fragment)
            assert process.wait(timeout=5) == 0, process.stderr.read()
            assert record.read_bytes() == fixture
            response = Path(temporary) / (scenario + ".response")
            response.write_bytes(wire)
            expected = "rejected" if scenario in ["truncated", "malformed"] else "complete"
            outcome = subprocess.run([parser, str(response), expected], check=True, capture_output=True, text=True, timeout=10)
            if expected == "complete":
                assert 'body={"result":"mock"}' in outcome.stdout
            try:
                unexpected = socket.create_connection((address["host"], address["port"]), timeout=0.2)
            except ConnectionRefusedError:
                pass
            else:
                unexpected.close()
                raise AssertionError("owned listener survived child exit")
            print(scenario, outcome.stdout.strip(), "child exited; listener closed")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            process.stdout.close()
            process.stderr.close()
