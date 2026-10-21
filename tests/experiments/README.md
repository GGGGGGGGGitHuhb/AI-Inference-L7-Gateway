# V0.4/S1 固定性能基线

只新增实验工具，不改变产品/旧P1或MVP。权威为docs/leader/designs/V0.4/S1-design.md。一次正式run包含57cell（已含三重复）、7104正式+486预热=7590唯一ID；不自适应rate/阈值、不补样本。先短控与三套完整CTest，再显式矩阵。机器上Builder/Reviewer不能同时发压；Reviewer使用自己的目录与产物。

```bash
mkdir -p build-local/builder/v0.4-s1/{tmp,cache,evidence}
export TMPDIR="$PWD/build-local/builder/v0.4-s1/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.4-s1/cache"
export PYTHONPYCACHEPREFIX="$XDG_CACHE_HOME/pycache"
cmake --preset release -B build-local/builder/v0.4-s1/release
cmake --build build-local/builder/v0.4-s1/release -j4
ctest --test-dir build-local/builder/v0.4-s1/release --output-on-failure
python3 tests/experiments/RunExperiments.py \
  --host build-local/builder/v0.4-s1/release/ExperimentRuntimeHost \
  --gateway build-local/builder/v0.4-s1/release/ai-inference-gateway \
  --assets build-local/integration/v0.2-s3 \
  --output build-local/builder/v0.4-s1/evidence/run-001
```

debug/asan同样完整构建/CTest。普通CTest的ExperimentDetectors仅有限短控，不启动模型或矩阵。持久负控证据可加`--output <不存在目录>`运行DetectorTests.py，第一位置参数是host路径。socket/LSan需宿主允许，不能关闭检测器。

## 固定方法与观察开销

Plan.py在第一个cell前输出完整plan、请求hash、SLO和配置模板；每cell端口只由自有监听确定。A/T/N用正式网关；B/H/Q用链接同库只读host，R用正式程序。所有客户端新TCP/Connection close。合成后端默认NODELAY关闭且逐请求保存getsockopt，N仅改变后端NODELAY。A冻结P1的1024byte JSON；B冻结P1的4MiB SSE，H/Q固定同1024byte合法SSE，异质延迟为20/100ms、每四ID第四长乘4。

单/双发压子进程只通过有界stdin/stdout IPC交还摘要，只有父进程写受管目录。每进程最多128发压线程，IPC帧≤8KiB、队列≤256；每cell最多210attempt，缓冲后finally各ID唯一写出；错误/中断后已派发与未派发分别闭合，未开始cell另有unstarted.json。正常摘要只存增量校验所得长度/hash/时刻及有限错误片段，不存4MiB正文。host每ID≤16条≤1KiB转换、采样≤4KiB；stdout管道有限，父线程每256事件批写，原始状态目标100ms、资源目标1s，存在调度/写盘开销，不能称硬实时或瞬时真峰。

开环H/Q均匀scheduled时钟、128在途上限，迟到>50ms或无槽记not_sent、不补发；SLO起点为scheduled，发送后时延另列。闭环从屏障至最后关闭计吞吐，SLO从connect开始；成功SLO是success子集，拒绝、HTTP超时、客户端deadline、传输/协议失败、未发/未开始互斥。分位数nearest-rank：n≥20仅p50、≥100加p95、≥1000才p99，各重复分开不混池。Analyze.py重新读取每条原始attempt复核统计；Reviewer仍须独立审计。

R只读复用b7481/Qwen固定资产，双CPU各2线程共享机器，无下载。按Leader实施澄清，P不宣称逐ID后端目标；用每实例日志唯一generation task的new prompt/release/print_timing集合在预热前、预热后、正式后三次排空边界核对0→1→7，附metrics原文并确认GET不新增generation。每实例/区间timing在原日志，不把HTTP访问/slot/token当生成请求数，不按实例归因客户端延迟。

## 运行期预算与失败

1GiB严格分区512MiB直接预留＋448MiB受管累计写入＋64MiB错误池。每个直接路径启动前预留512KiB，子进程prlimit软硬RLIMIT_FSIZE512KiB/core0；包含stderr、后端summary及warmup快照，host不写独立快照文件。最多每cell9个直接路径（设计允许上限12），真实5、B6、A/N6、T双进程7，全部远低于716路径规划上界。覆盖受管文件不退账，锁内先计序列化bytes；读取旧资产/源码不算run输出。达到边界失败且kill/wait，不靠最终合计。

全run3600s、合成cell60s、真实cell240s；客户端绝对16/155s。所有子进程属于自有process group，TERM5s后KILL/wait；父finally保存当前cell至多256条≤8KiB摘要，64MiB硬计费错误池保留失败/未开始索引，不标伪成功。目录必须不存在，失败保留，新编号重测需Leader决定，不能自行择优。

T漂移/发压敏感/CPU限制如实标注；H至少一个速率和Q各需三对中至少两对非arrival_limited，否则BLOCKED。B必须pause/resume且快流在慢流结束前进展；资源/协议错误不属于可接受负面性能。结果不承诺生产SLO、GPU收益、普遍性能提升或长期公平。
