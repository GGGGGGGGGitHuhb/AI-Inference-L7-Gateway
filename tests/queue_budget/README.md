# V0.4/S2 queue budget experiment

Compare existing admission settings: Z disables queueing, B allows eight queued requests for 500 ms, C allows eight for 100 ms. Product defaults remain unchanged (1000 ms). These are synthetic experiment starting points, not production tuning recommendations.

`configs/no-queue.json`, `baseline-500ms.json`, and `candidate-100ms.json` are complete gateway configuration files. They bind loopback port 8080 and use backend-0/1 on 18081/18082 with model `gateway-qwen`. Adjust listen/backend ports and model to your actual environment before using a configuration with `gateway --config PATH`. Roll back the experiment by selecting `baseline-500ms.json`; preserve your actual addresses/model settings. No live configuration reload or production deployment is performed here.

Use native WSL paths and separate Builder/Reviewer directories. Set TMPDIR, TMP, TEMP to the role's `tmp`, XDG_CACHE_HOME to `cache`, and PYTHONPYCACHEPREFIX to `cache/pycache`. Build the existing Release `ExperimentRuntimeHost` first. Execute the new controls separately from CTest:

```bash
python3 tests/queue_budget/DetectorTests.py --host build-local/builder/v0.4-s2/release/ExperimentRuntimeHost --output build-local/builder/v0.4-s2/evidence/controls-001
python3 tests/queue_budget/RunQueueBudget.py --host build-local/builder/v0.4-s2/release/ExperimentRuntimeHost --output build-local/builder/v0.4-s2/evidence/run-001
```

Output directories must not exist. Reviewer substitutes their own role paths and builds. The runner starts owned loopback synthetic backend/host/client processes; no model download is needed. Only the approved role runs a load experiment at a time. Preserve any failed output and obtain a Leader decision before corrective reruns.

QueuePlan freezes 21 cells including three repeats: 18 Q cells at 5/60 requests/s, three configurations, and three T generator controls. There are 2760 formal and 210 warmup IDs. Each repetition orders configurations Z/B/C, C/B/Z, B/Z/C, first at 5 then 60. Q uses S1's two heterogeneous backends (20/100 ms, every fourth request four times longer), legal 1024-byte SSE, unchanged client scheduling and payload validation. QueueCell changes only configuration construction; all subprocess, transport, storage, sampling and connection association mechanisms import S1 unchanged.

Formal Q goodput is the count of successful responses satisfying scheduled-origin TTFT<=250ms and E2E<=500ms divided by 120/rate. Every planned ID stays in the denominator, including 503, 504 and not_sent. Short/long classes use the same full window. `queue-audit.json` separates warmup/formal enqueue-to-dispatch and enqueue-to-timeout observations; timeout checks include no dispatch and no backend request. Timer observations may be late. No cross-repeat pooling is used.

At least two valid Z/B/C triplets per rate and no low-rate B/C rejection are required for valid comparison. The analysis distinguishes experiment validity, numerical candidate thresholds, and generator restrictions; even positive observed numbers cannot become a recommendation when T/CPU controls trigger. A negative result can pass stage acceptance and must retain the baseline. Independent Reviewer agreement is required for any limited recommendation; no causal, capacity, real-model or GPU claim is supported by this tool.

The run has a 900 s deadline, 60 s per cell and the inherited 1 GiB cumulative partitioned output budget. First failure preserves current attempts plus remaining not_started IDs, and owned processes are reaped. `manifest.json`, raw ID files, transitions, backend records, drain/resource/process ledgers, `analysis.json` and `result.json` are the evidence. New controls include true held-slot 100 ms queue timeout, statistics counterexamples, process exit and budget exhaustion; they are not formal performance samples or additions to the existing 21 CTest cases.
