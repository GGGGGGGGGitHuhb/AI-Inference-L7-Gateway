# V0.2/P1 显式性能基线

以 [Approved 设计](../../docs/leader/designs/V0.2/P1-design.md)为权威。只用 Python 标准库和现有固定 CPU 模型。默认 CTest 只跑离线本机回环负控；完整矩阵必须显式运行。产品和旧 S3 工具不变。

```bash
mkdir -p build-local/builder/v0.2-p1/{tmp,cache,evidence,release}
export TMPDIR="$PWD/build-local/builder/v0.2-p1/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.2-p1/cache"
cmake --preset release -B build-local/builder/v0.2-p1/release
cmake --build build-local/builder/v0.2-p1/release -j4
ctest --test-dir build-local/builder/v0.2-p1/release --output-on-failure
python3 tests/performance/RunBaseline.py --check
python3 tests/performance/RunBaseline.py --gateway "$PWD/build-local/builder/v0.2-p1/release/ai-inference-gateway" --host "$PWD/build-local/builder/v0.2-p1/release/IntegrationRuntimeHost" --assets "$PWD/build-local/integration/v0.2-s3" --output build-local/builder/v0.2-p1/evidence/run-001
python3 tests/performance/Summarize.py --input build-local/builder/v0.2-p1/evidence/run-001 --output build-local/builder/v0.2-p1/evidence/summary-001
```

输出目录必须不存在；Reviewer使用自己的角色目录，等待其他测量结束再开始。固定69cell加3个工具控制。每个模拟cell独立后端/网关，真实配对block独立模型；同一时刻一个模型、一个cell。stdout按cell报告进度。无校准缩小矩阵或自动选优功能。

`Client.py` 只读继承 S3 WireResponse 的严格解帧，独立在 CL 最后字节/chunked 零块确认时取 `t_http`，继续等 EOF 验证无尾随污染；EOF 定界以 EOF 为完成。所有观测时间来自同一客户端 monotonic_ns，首非空内容事件 TTFT 使用包含完整事件的 recv 返回时刻；时间分辨率不等于测量精度。序列化在 t0 之前，校验/关闭在 t_http 之后但包含在闭环批次墙钟中。

`Backend.py` 是独立进程；不在请求热路径写磁盘，B 保存实际发送间隔。`Measure.py` 线程准备后统一屏障放行，常规闭环无退休快照门；C 是四请求波次闭环。双发压控制使用两个独立进程各八线程。每个有界cell结束/finally写样本，连接/协议/校验/晚到失败保留为失败结果；完整矩阵可报告失败率，工具或矩阵不完整则非零并保存 run-status。

根输出含 manifest/schedule/cells/summary/run-status。每cell有 warmup、formal 各自 attempts.jsonl、resources.jsonl、cell.json。模拟后端 backend-counts.json 和 warmup 快照用于正式 accept/request 差量，真实block保留模型完整启动/计时日志与 process start/reaped。C使用 IntegrationRuntimeHost，额外保存快照/排空与峰值。所有自有进程用 PID/process group 清理，不按名称杀进程。

汇总以成功样本计算 nearest-rank；失败单列，零成功为 null。A p99 仅探索性（500次约五个尾样本）；B p50/p95，R p50/p90，C快/慢median/max。三重复只报 median 和观察 min–max，不混池、不选最好、不称置信区间。完成/s为闭环链路观察，存在 coordinated omission；不是最大容量。token/s只接受后端 usage.completion_tokens，缺失时null。差值不是单请求额外延迟的分位数；CPU单slot排队、cache和Python发压限制均需保留解释。
