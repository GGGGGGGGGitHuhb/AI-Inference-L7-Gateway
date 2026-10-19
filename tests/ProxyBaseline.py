"""S3 fixed closed-loop correctness/cost matrix. No inference or throughput claim."""
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import socket
import subprocess
import threading
import time
from support.PersistentBackend import PersistentBackend
from support.ReuseHarness import GatewayProcess, request_wire, receive

BODY = b'{"result":"' + b'x' * 1011 + b'"}'
assert len(BODY) == 1024
REQUEST = request_wire("x" * 256)


def process_resources(pid):
    try:
        text = Path(f"/proc/{pid}/status").read_text()
        rss = next(int(line.split()[1]) for line in text.splitlines() if line.startswith("VmRSS:"))
        return {"rss_kib": rss, "fds": len(list(Path(f"/proc/{pid}/fd").iterdir()))}
    except (OSError, StopIteration): return None


class Sampler:
    def __init__(self, processes):
        self.processes = processes
        self.samples = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run)

    def run(self):
        while not self.stop.is_set():
            self.samples.append({"time_ns": time.monotonic_ns(), "processes": {name: process_resources(pid) for name, pid in self.processes.items()}})
            self.stop.wait(.01)

    def finish(self):
        self.stop.set(); self.thread.join(2)
        assert not self.thread.is_alive()


def one_request(port, index):
    started = time.monotonic_ns()
    result = {"index": index, "ok": False, "rejected": False}
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
            connection.sendall(REQUEST)
            wire = receive(connection)
        headers, body = wire.split(b"\r\n\r\n", 1)
        result.update(response_wire_bytes=len(wire), response_body_bytes=len(body), response_sha256=hashlib.sha256(wire).hexdigest())
        result["rejected"] = not headers.startswith(b"HTTP/1.1 200 ")
        result["ok"] = not result["rejected"] and body == BODY and wire.count(b"HTTP/1.1 ") == 1
        if not result["ok"]: result["error"] = "response mismatch"
    except Exception as error:
        result["error"] = repr(error)
    result["elapsed_ns"] = time.monotonic_ns() - started
    return result


def batch(port, count, concurrency, deadline):
    # 每个worker完成一个请求后才发送下一个，始终至多concurrency个在途。
    def worker(worker_index):
        samples = []
        for index in range(worker_index, count, concurrency):
            if time.monotonic() >= deadline:
                samples.append({"index": index, "ok": False, "rejected": False, "elapsed_ns": 0, "error": "cell deadline"})
            else: samples.append(one_request(port, index))
        return samples
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        groups = list(executor.map(worker, range(concurrency)))
    return sorted([sample for group in groups for sample in group], key=lambda sample: sample["index"])


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def run_cell(executable, root, mode, concurrency, repeat):
    directory = root / f"{repeat}-{concurrency}-{mode}"
    directory.mkdir()
    backend = PersistentBackend(directory, body=BODY)
    gateway = None
    sampler = None
    result = {"mode": mode, "concurrency": concurrency, "repeat": repeat, "request_wire_bytes": len(REQUEST), "response_body_bytes": 1024}
    try:
        if mode != "direct-close":
            gateway = GatewayProcess(executable, directory, backend, upstream_pool={"max_connections": 16, "max_idle": 16 if mode == "proxy-reuse" else 0, "idle_timeout_ms": 300000})
            result["config"] = gateway.config
        port = gateway.port if gateway else backend.port
        processes = {"backend": backend.process.pid}
        if gateway: processes["gateway"] = gateway.process.pid
        result["resources_initial"] = {name: process_resources(pid) for name, pid in processes.items()}
        sampler = Sampler(processes); sampler.thread.start()
        deadline = time.monotonic() + 60
        result["warmup"] = batch(port, 20, concurrency, deadline)
        before = backend.counts()
        result["before_counts"] = before
        result["resources_before"] = {name: process_resources(pid) for name, pid in processes.items()}
        started = time.monotonic_ns()
        result["samples"] = batch(port, 200, concurrency, deadline)
        duration = time.monotonic_ns() - started
        after = backend.counts()
        result["after_counts"] = after
        result["measurement_counts"] = {key: after[key] - before[key] for key in after}
        result["resources_after"] = {name: process_resources(pid) for name, pid in processes.items()}
        durations = [sample["elapsed_ns"] / 1e6 for sample in result["samples"]]
        completed = sum(sample["ok"] for sample in result["samples"])
        result.update(completed=completed, failures=200-completed, rejected=sum(sample["rejected"] for sample in result["samples"]), duration_seconds=duration/1e9, completed_qps=completed/(duration/1e9), p50_ms=percentile(durations,.50), p95_ms=percentile(durations,.95), p99_ms=percentile(durations,.99))
        assert all(sample["ok"] for sample in result["warmup"] + result["samples"]), "request failure"
        assert after["requests"] == 220, after
        if mode == "proxy-reuse": assert after["accepts"] <= concurrency and (concurrency != 1 or after["accepts"] == 1), after
        else: assert after["accepts"] == after["requests"], after
        result["reuse_count_total"] = after["requests"] - after["accepts"]
        result["passed"] = True
    except Exception as error:
        result.update(passed=False, error=repr(error))
    finally:
        if sampler:
            sampler.finish()
            result["resource_samples"] = sampler.samples
            result["observed_peaks"] = {name: {metric: max((sample["processes"][name] or {}).get(metric, 0) for sample in sampler.samples) for metric in ("rss_kib", "fds")} for name in sampler.processes}
        try:
            if gateway: gateway.close()
            result["gateway_cleaned"] = True
        except Exception as error: result.update(passed=False, cleanup_error=repr(error))
        try:
            backend.close(); result["backend_cleaned"] = True
        except Exception as error: result.update(passed=False, cleanup_error=repr(error))
        if gateway and sampler:
            result["gateway_fd_bound"] = result["resources_initial"]["gateway"]["fds"] + 16 + 16 + 1
            if result["observed_peaks"]["gateway"]["fds"] > result["gateway_fd_bound"]:
                result.update(passed=False, resource_error="gateway FD bound")
        result["backend_record"] = str(backend.record_path)
        (directory / "result.json").write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", required=True)
    parser.add_argument("--output", required=True)
    options = parser.parse_args()
    output = Path(options.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    root = output.parent / (output.stem + "-cells-" + str(time.monotonic_ns()))
    root.mkdir()
    executable = str(Path(options.gateway).resolve())
    sources = sorted([Path("CMakeLists.txt"), Path("CMakePresets.json"), *Path("src").rglob("*.cpp"), *Path("src").rglob("*.h"), Path(__file__), Path("tests/support/PersistentBackend.py"), Path("tests/support/ReuseHarness.py")])
    report = {"binary": executable, "binary_sha256": hashlib.sha256(Path(executable).read_bytes()).hexdigest(), "source_sha256": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}, "platform": platform.platform(), "compiler": subprocess.check_output(["c++", "--version"], text=True).splitlines()[0], "percentile_method": "nearest-rank", "clock": "monotonic_ns", "resource_sampling_seconds": .01, "resource_limit": "observed sampled peaks are not true maxima; direct has no gateway", "load": "closed-loop synthetic loopback, no artificial backend delay", "cells": []}
    modes = ["direct-close", "proxy-close", "proxy-reuse"]
    for repeat in range(3):
        for concurrency in (1, 4):
            for mode in modes[repeat:] + modes[:repeat]:
                cell = run_cell(executable, root, mode, concurrency, repeat)
                report["cells"].append(cell)
                output.write_text(json.dumps(report, indent=2))
                print(mode, concurrency, repeat, "PASS" if cell["passed"] else "FAIL", cell.get("p99_ms"), flush=True)
    assert len(report["cells"]) == 18 and all(cell["passed"] for cell in report["cells"]), "matrix failed; all original results preserved"


if __name__ == "__main__": main()
