# V0.2/S3 显式集成验证

这里的工具只依赖Python标准库和同仓库构建产物。`IntegrationRuntimeHost`链接原有gateway_runtime，使用现有只读snapshot与pollOnce；输出每100ms一个账本快照，不增加产品管理API，不改产品socket或水位。正常程序另由RealRun执行真实协议和活动流SIGTERM冒烟。普通CTest只新增短时`IntegrationDetectors`，不会加载/下载模型或执行soak。

先读取[Approved设计](../../docs/leader/designs/V0.2/S3-design.md)与[审查计划](../../docs/reviewer/reviews/V0.2/S3-review.md)。固定CPU llama.cpp b7481和Qwen2.5-0.5B-Instruct Q4_K_M必须已经由环境准备者下载、校验和安全解压；本工具不会安装依赖或下载。缺资产/错hash直接失败。共享资产只读，Reviewer等待Builder全部模型进程回收后独立运行。

在仓库根目录使用本机原生路径；每角色先创建自己的目录并设置环境，例如Builder：

```bash
mkdir -p build-local/builder/v0.2-s3/{tmp,cache,evidence,release}
export TMPDIR="$PWD/build-local/builder/v0.2-s3/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.2-s3/cache"
cmake --preset release -B build-local/builder/v0.2-s3/release
cmake --build build-local/builder/v0.2-s3/release -j4
python3 tests/integration/DetectorTests.py "$PWD/build-local/builder/v0.2-s3/release/IntegrationRuntimeHost"
```

先运行短校准：下列命令各加`--calibration`并使用独立输出目录。校准报告只写`CALIBRATION_PASS`，真实校准涵盖协议/故障但不执行600秒soak，模拟校准只50请求；绝不能把这些结果作为长run验收。正式命令：

```bash
python3 tests/integration/RealRun.py \
  --assets build-local/integration/v0.2-s3 \
  --host "$PWD/build-local/builder/v0.2-s3/release/IntegrationRuntimeHost" \
  --gateway "$PWD/build-local/builder/v0.2-s3/release/ai-inference-gateway" \
  --output build-local/builder/v0.2-s3/evidence/real-new-run
python3 tests/integration/SyntheticRun.py \
  --host "$PWD/build-local/builder/v0.2-s3/release/IntegrationRuntimeHost" \
  --output build-local/builder/v0.2-s3/evidence/synthetic-new-run
```

输出目录必须不存在，重试换新名称保留旧失败。已知loopback/socket/LSan权限边界按agent-execution-route精确升级，不禁检查。工具通过本次专属PID/process group清理，不能使用pkill。SIGINT/SIGTERM、异常与正常结束均执行finally回收；模型TERM最多等5秒，再KILL并wait。故障重启保持原端口与参数；端口无监听但连接TIME_WAIT尚未释放时，最多等65秒，包含在总120秒启动护栏内。已有活listener立即拒绝，初次冲突不等待。

`Inputs.json`只含固定合成prompt，无个人数据。真实请求仅使用当前gateway字段；512-token长prompt、32-token短prompt、temperature0、alias gateway-qwen保持冻结。配置在每个run的host-config.json记录。真实soak单在途、每条间隔0.1s、strict stream/nonstream交替，每10条排空；同时满足600秒/60请求后在10条边界收尾，护栏1800秒。模拟seed20261019，每10条4快流/2慢流/2非流/1取消/1坏chunk或截断，最多4在途，每50条排空；同时满足300秒/300请求，护栏900秒。协议错误立即非零，不丢弃计划失败样本。

WireResponse增量消费HTTP chunk片段，不等待完整chunk。保留原始头、定界、每次正文片段时间/长度和正文SHA；终态后要求EOF且无尾随字节，从而检测第二零chunk/多余数据。真实客户端额外验证JSON、非空content、finish_reason与一次[DONE]，此逻辑仅在工具中，产品保持opaque。跨模型请求不做字节相等；模拟对固定同一正文做完整hash和长度/终态验证。

每个run有manifest（输入/源/二进制身份、固定时长/负载）、protocol/soak逐样本jsonl、processes.jsonl、各模型启动日志、host-snapshots.jsonl、每秒resources.jsonl、drains.jsonl与summary。账本每100ms采样，并检查产品累计容量峰值；采样不声称捕获每次瞬时状态。排空必须全部活跃账本为0、FD回启动基线。RSS以预热排空B为基准检查B+32MiB和末5点跨度8MiB。模型RSS独立采样，仅2GiB启动护栏及诊断；内核socket buffer不包含在用户态预约内。正式run不作吞吐、TTFT或GPU取消收益结论。

取消证据分层：记录首content回调时/slots和本地快照，RST后5秒内资源清零，再观察slot及短请求恢复。L1/L2据同负载账本、FD、租约和模型日志；L3只报告固定CPU后端slot观察，不等同GPU计算停止。`cancellation.jsonl`保留直接观测，不根据客户端RST推定后端计算状态。

工具负控覆盖缺资产/坏hash、端口冲突、进程启动失败、坏HTTP/CL少字节/超时、容量越界和RSS超限；每个子进程须非零。三预设普通回归、原18+18截止探针及20次关闭窗口仍按本阶段要求另外执行，不能用集成run替代。

F-001异常留存纠正：每个协议/soak尝试现在经recorded_exchange的finally唯一落盘，包含attempt_id、label或index、请求hash、起止、已知状态、partial bytes/hash和具体错误。连接/解析/回调/校验/中断保留原失败传播；预期取消不改为成功。IntegrationAttempts提供13类异常和首失败后4个晚到future的持久回归；快速运行可用`ctest --test-dir <角色release目录> -R '^Integration(Detectors|Attempts)$' --output-on-failure`。本轮短校准不替代长期证据，复用依据和精确新旧身份见[Builder003](../../docs/builder/reports/V0.2/S3-report-003.md)。
