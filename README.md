# AI Inference L7 Gateway

> 当前状态（2026-10-31）：**V0.6/S2前置诊断已独立接受，产品优化入口仍BLOCKED。** 双后端与CPU亲和性对照未稳定解决L4高档失败；下一步需直接记录接入拒绝与连接关闭来源。产品代码保持，未发布。见[诊断结果](docs/performance/V0.6/S2-preflight-results.md)与[收口报告](docs/leader/reports/V0.6/S2-preflight-report-002.md)。

面向在线文本推理服务的独立 C++ 七层网关项目，计划围绕流式代理、资源控制和请求调度建立可复现的工程实验。

**项目定位：独立项目、按需复用、最后联调。** Gateway 独立接收客户端请求；按需复用已有 HTTP Server、L4LB 的合适组件和工程经验；完成独立能力后，再验证与 L4LB 的组合部署。

## 当前状态

**V0.2流式可靠性开发验收已完成。** S1/S2/S3均已独立接受，累计返工分别1/2、0/2、2/2；S3唯一失败attempt取证发现已关闭，无剩余发现或债项，见[Reviewer002 PASS](docs/reviewer/reports/V0.2/S3-report-002.md)与[Leader002收口](docs/leader/reports/V0.2/S3-report-002.md)。V0.3/S1模型路由与健康、S2准入与有界排队亦已完成，S3已完成开发验收，尚未正式发布。

V0.1/S3与V0.1基础代理已完成开发验收。 S3经一次有限规范纠正后取得[Reviewer002 PASS](docs/reviewer/reports/V0.1/S3-report-002.md)，唯一空行规范发现关闭，无未解决发现或债项；收口见[Leader002](docs/leader/reports/V0.1/S3-report-002.md)。累计返工：S1 2/2、S2 1/2、S3 1/2，各阶段独立记录。

当前执行分支 `codex/v0.6-s2-preflight`，起点为c51af0e。V0.1～V0.5已完成开发验收；V0.6/S1及S2前置诊断已交付，S2产品优化因直接归因证据不足暂不进入，没有正式发布。

已验收：独立离线构建、最小复用组件、受限HTTP/1.1与文本JSON、单静态上游非流式代理、硬限额和分类deadline、信号停止，以及有界上游顺序复用与初始合成成本基线。下游继续每连接单请求；V0.2/S1新增SSE字节增量链路已独立验收；V0.3/S1多实例路由与健康、S2准入排队已验收，真实GPU收益仍未验证；L4LB联调与组合成本测量已完成V0.5验收，V0.6/S1容量诊断已交付。S1与S2历史验收见[Leader S1-004](docs/leader/reports/V0.1/S1-report-004.md)、[Leader S2-003](docs/leader/reports/V0.1/S2-report-003.md)。

## 构建与验证

环境：Linux、C++20 编译器、CMake >=3.24、Ninja、Python 3。Bash，工作目录为本仓库根目录。依赖已固定在 third_party，构建无需联网或同级项目。

```bash
mkdir -p build-local/builder/v0.2-s3/tmp build-local/builder/v0.2-s3/cache
export TMPDIR="$PWD/build-local/builder/v0.2-s3/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.2-s3/cache"
cmake --preset debug -B build-local/builder/v0.2-s3/debug
cmake --build build-local/builder/v0.2-s3/debug
ctest --test-dir build-local/builder/v0.2-s3/debug --output-on-failure
```

Release 与 AddressSanitizer/UndefinedBehaviorSanitizer：将上述三个命令的 `debug` 分别换为 `release`、`asan`。每个预设当前注册21项CTest；V0.4/S1独立Debug/Release/ASan+UBSan各21/21，详见当前收口报告；AssertionFailure 使用预期失败验证 Release 下检查仍有效。Pool、ReuseE2E、Runtime、GatewayE2E 和 MockBackend 需要本机 loopback socket 权限，会自动申请临时端口并回收自己的子进程；权限不足即失败，不跳过。

独立审查使用 `cmake --preset debug -B build-local/reviewer/v0.2-s3/debug`（其他预设同理），随后通过 `cmake --build <目录>` 和 `ctest --test-dir <目录>` 操作；同时将 TMPDIR/TMP/TEMP/cache 指向 reviewer 自有目录。

格式检查（仅自有和迁入 C++，不处理 third_party）：

```bash
find src tests -type f \( -name '*.h' -o -name '*.cpp' \) -print0 | xargs -0 clang-format-18 --dry-run --Werror
```

测试使用合成输入，不需要 GPU、真实推理服务或 Python 第三方包。`tests/ParseResponse.cpp` 是将模拟器原始响应输入解析库的测试工具，不是网关产品入口。

## 启动代理

```bash
build-local/builder/v0.2-s3/debug/ai-inference-gateway --config config/example.json
```

示例监听 `127.0.0.1:8080`，上游为 `127.0.0.1:8000`，需要自行启动符合文本接口的 HTTP 后端；无 GPU 的完整链路由 `GatewayE2E` 测试自动启动合成后端验证。成功输出 `READY 127.0.0.1:8080`；`listen_port: 0` 可获取临时端口。`--help` 退出 0，配置/参数错误退出 2，监听等运行错误退出 1。

配置只接受 IPv4 字面量、单个静态上游，拒绝未知键/重复键/错误类型和超过 64KiB 的文件；字段与范围见 [S2 设计 §4](docs/leader/designs/V0.1/S2-design.md)。接收 `POST /v1/chat/completions` 的受限文本 JSON，单连接处理一条请求；响应提交后先写半关闭，再有界读排空，EOF或固定截止后全关闭。正常关闭窗口最多1秒且受total约束，错误路径共享原错误排空窗口；closing期间仍占完整16MiB预约。默认最多 16 会话、每会话预约 16MiB。SIGINT/SIGTERM 先停止监听并排空，超出 shutdown deadline 或第二次信号强制收口。流式请求的具体支持边界见下节。

## 计划解决的问题

- 代理 HTTP 推理请求，及时转发 SSE 响应。
- 在慢客户端、后端故障、取消和超时下维持资源边界。
- 在有限后端容量下，通过模型路由、准入和有界排队控制请求行为。
- 分别测量代理开销、流式稳定性和调度效果，避免仅用 QPS 表达系统能力。

## 与已有项目的关系

独立运行是主要交付路径：

```text
Client → AI Inference L7 Gateway → Inference Backends
```

后续联调路径：

```text
Client → L4LB TCP Proxy → Multiple Gateways → Inference Backends
```

- **HTTP Server：** 网络基础组件的复用候选，不要求作为运行链路中的独立服务。
- **L4LB：** 前期提供双向转发、背压等设计参考；后期可承担多个 Gateway 实例之间的 TCP 连接分发。
- **Gateway：** 独立承担 HTTP 代理、推理请求路由、流式生命周期及准入排队。
- **推理后端：** 执行模型计算。一个后端实例不预设对应一张 GPU。

Gateway 的构建和启动不应依赖同级 Server、L4LB 仓库的本地路径。S1 已按固定源码快照迁入最小组件，来源和差异见复用记录。

## 文档入口

- [V0.2/S1设计](docs/leader/designs/V0.2/S1-design.md)、[审查计划](docs/reviewer/reviews/V0.2/S1-review.md)、[Leader001](docs/leader/reports/V0.2/S1-report-001.md)：SSE字节增量权威；当前已验收收口见[Leader002](docs/leader/reports/V0.2/S1-report-002.md)和[Reviewer002](docs/reviewer/reports/V0.2/S1-report-002.md)。

- [S3决策报告001](docs/leader/reports/V0.1/S3-report-001.md)：上游顺序复用、容量/租约与初始成本基线；Approved规划；当前收口见[Leader002](docs/leader/reports/V0.1/S3-report-002.md)，实现与有限纠正见[Builder002](docs/builder/reports/V0.1/S3-report-002.md)，独立接受见[Reviewer002](docs/reviewer/reports/V0.1/S3-report-002.md)。

- [S2收口003](docs/leader/reports/V0.1/S2-report-003.md)、[独立复验002](docs/reviewer/reports/V0.1/S2-report-002.md)：S2历史阶段结果与范围限制。

- [S2 设计](docs/leader/designs/V0.1/S2-design.md)、[审查计划](docs/reviewer/reviews/V0.1/S2-review.md)、[决策报告](docs/leader/reports/V0.1/S2-report-001.md)：独立单上游代理的 Approved 实现和审查基线。

- [架构大纲](ARCHITECTURE.md)：模块职责、所有权、请求流程、协议与资源边界。
- [分阶段开发路线](ROADMAP.md)：版本目标、阶段输出、验收条件和 MVP 边界。
- [V0.1/S1 设计](docs/leader/designs/V0.1/S1-design.md)：已选技术、协议子集、最小复用与实现验收基线。
- [V0.1/S1 审查计划](docs/reviewer/reviews/V0.1/S1-review.md)：独立验证方法及需求追溯。
- [S1 收口报告](docs/leader/reports/V0.1/S1-report-004.md)：阶段结论、验收范围和后续边界。
- [初始决策报告](docs/leader/reports/V0.1/S1-report-001.md)：规划时的选型依据和历史状态。
- [已验收变更](CHANGELOG.md)：Unreleased 阶段成果，不代表正式发布。
- [Approved 返工 001](docs/leader/reworks/rework-001.md)：状态范围与合法 chunk 扩展的适配权威。
- [Reviewer 复验报告](docs/reviewer/reports/V0.1/S1-report-002.md)：独立 PASS 及原始证据入口。

- [复用记录](docs/references/V0.1-S1-reuse.md)：固定来源与适配差异。
- [依赖清单](docs/references/V0.1-S1-dependencies.md)：版本、文件散列与许可证。
- [Builder 初次实现报告](docs/builder/reports/V0.1/S1-report-001.md)：初次命令、结果与证据。
- [Builder 返工报告](docs/builder/reports/V0.1/S1-report-002.md)：严格状态范围与有界 chunk 大小行前置适配、最新回归证据。

chunk 扩展先按完整原始大小行校验，再仅将大小与 CRLF 交给 llhttp；原始线缆/行预算和消费量保持独立计量。初次复用记录中的后置扩展校验描述属于旧实现，当前以 Approved 返工 001、Builder 002 和 Reviewer 002 的实现及验收说明为准。原设计/审查/返工中的阶段状态保留为历史快照，S1收口状态见Leader004；项目当前阶段以本页、ROADMAP和V0.4/S1最新Leader报告为准。

尚未提供项目自身的 `LICENSE` 文件；third_party 内保留各依赖许可证。

## Runtime 使用边界

本阶段交付独立进程，停止接口为SIGINT/SIGTERM。内部GatewayRuntime不是嵌入式SDK：在事件回调外直接连续调用requestShutdown可能使已结束会话的对象和预约计数保留至Runtime析构，不能据此声称该调用方式立即清零。真实信号与定时停止路径已独立验证回收；若以后对外提供Runtime接口，须另行定义并验证事件外清理契约。

## S3 上游连接复用（已独立验收）

每条下游连接仍只处理一个请求并返回 `Connection: close`，上游按池配置独立复用。可选 `upstream_pool` 对象默认 `max_connections: 16`、`max_idle: 16`、`idle_timeout_ms: 5000`；范围分别1..256、0..max_connections、10..300000。省略字段仍用各自默认，因此将总量改为2时也需把max_idle设为0..2。`max_idle: 0`生成上游close请求，供每请求新建对照。示例配置已包含一致字段。

池满立即503 `upstream_capacity`；停止后尚未取得租约的合法请求返回503 `gateway_stopping`。没有等待队列或自动重试。只有完整写完请求、明确响应边界、无close/尾随/传输故障且成功向下游SHUT_WR之后才归池；慢下游占用租约。归还/租出前peek、idle读事件和固定空闲期限淘汰失效连接。已借出的连接仍可能随后失败，当前请求502/504，不重发。

`RuntimeSnapshot.activeUpstreams`为当前租用数（包括connecting和等待下游输出），不是所有上游FD。`snapshot.pool`提供total/leased/idle/retired/peakTotal及created/reused/discarded/capacityRejected；累计计数饱和不回绕。discarded包含策略关闭、正常max_idle=0、停止和故障的全部物理连接退休，不等同故障数。idle不持有正文；会话仍全额预约16MiB，closing保持预约。每个活动会话最多一个timer、每个idle最多一个timer，停止另一个；池条目和Channel含回调后退休对象最多2×池总量，业务/计时回调后cleanup清空退休集。

初始成本实验（Release、合成loopback、闭环，不代表真实推理或性能收益）：

```bash
python3 tests/ProxyBaseline.py --gateway build-local/builder/s3/release/ai-inference-gateway --output build-local/builder/s3/evidence/baseline.json
```

固定18cell：direct-close/proxy-close/proxy-reuse × 并发1/4 × 三重复，每cell20次预热、200次测量，保留预热池、原始样本、进程配置与来源散列、后端连接计数和10ms采样RSS/FD。分位数用nearest-rank，观测峰不是真实极值。通过条件是精确响应、零失败及连接/资源边界，不设置速度收益阈值。

独立成本矩阵18cell全部正确、零失败/拒绝；close模式每cell220次后端连接，reuse并发1为1次、并发4为4次（含预热）。原始分布包含direct并发4一次17.827ms P99，未选择性重跑；仅为合成WSL回环初始观察，不能代表真实推理或生产收益。完整数据及验证身份复用边界见[Reviewer001](docs/reviewer/reports/V0.1/S3-report-001.md)与[Reviewer002](docs/reviewer/reports/V0.1/S3-report-002.md)。

## 当前提交规则

按用户2026-10-29最新指令“以后完成每次任务了提交并推送”，每次任务完成并验证/验收通过后，由协调者提交本次改动并推送当前工作分支到origin，再核对本地与远端提交一致；无需逐次提醒。若认证或网络导致推送失败，保留本地提交并明确报告失败，不宣称已同步。此规则不自动授权合并分支或发布版本。

历史报告中的“本地提交、不推送”仅描述当时授权，保留原文，不再作为当前提交规则。V0.5/S1提交92fcf3d、S2提交8c9d51f均已推送各自阶段分支；开发验收完成不等于正式发布。

## V0.2/S1 流式链路（已独立验收）

`stream`省略或false保持原有完整响应代理；true仅在最终HTTP/1.1 200且唯一Content-Type为text/event-stream（可带单个UTF-8 charset）时转入字节增量转发。先验证完整最终头，再发送下游chunked头；SSE正文不解释event、UTF-8或[DONE]，也不等待完整event或上游chunk。非SSE响应沿旧4MiB正文/8MiB线缆预算完整回退。重复Content-Type、非法SSE参数或非200 SSE在提交前502。

流请求可借用idle上游，但强制Connection: close，任何结果均不归池；无自动重试。早期SSE最终头停止剩余上传。只有HTTP正文完整才发送零终止块；send接受任意首字节后即视为已提交，后续错误/超时仅截断，不追加第二状态行、零块或[DONE]。

固定pending容量256KiB（含响应头/chunk封装），解析片段16KiB、recv scratch16KiB，流累计正文8MiB、线缆16MiB，沿用16MiB会话预约和既有头/chunk数量限制。S1历史策略为慢读导致pending超限时有限中断；当前S2已验收高低水位暂停/恢复，见下节。response期限覆盖整个HTTP响应，total绝对期限保留；S1历史非空批次写期限不随部分写成功刷新；当前S2流式路径改为正数send刷新无进展期限，非流式不变。暂时无数据不代表结束。

验证入口StreamingParser、Runtime、StreamingE2E覆盖真实CL/chunked/EOF头/前缀门控、坏帧与断连、超过4MiB流、慢客户端与混合请求及停止回收。记录见[Builder返工报告002](docs/builder/reports/V0.2/S1-report-002.md)、[Reviewer002 PASS](docs/reviewer/reports/V0.2/S1-report-002.md)和[当前来源变化](docs/references/V0.2-S1-changes.md)。本阶段不重跑历史18cell成本矩阵，不作TTFT或吞吐收益承诺。

完成转换在撤除response期限、追加零chunk前重新检查当前时钟；恰等于或超过期限，未提交仅504、已提交截断。S1独立复验三套11/11、原response与total矩阵各18/18，新81组合覆盖CL/chunked/EOF及未提交/首字节/前缀状态。S1验收范围不含高低水位暂停恢复；S2已验收能力见下节。没有真实GPU或性能收益结论。

## V0.2/S2 设计依据

[设计](docs/leader/designs/V0.2/S2-design.md)、[审查计划](docs/reviewer/reviews/V0.2/S2-review.md)与[Leader001](docs/leader/reports/V0.2/S2-report-001.md)明确：固定256KiB流输出上默认192/64KiB高低水位，暂停移除上游事件注册、恢复新token；每会话16MiB保守预约内，另以默认4MiB的全进程SSE数组容量子预算约束流输出。流写期限改为有效send进展计时，新增主动暂停冻结余量的stream_idle，response/total保持绝对期限；非流式写期限保持。上述能力及旧配置补默认已获独立PASS，由Leader002收口。

## V0.2/S2 背压与预算（已独立验收）

`stream_buffer`可省略；默认`high_water_bytes: 196608`、`low_water_bytes: 65536`、`max_total_bytes: 4194304`。范围分别32768..229376、0..high-1、262144..67108864；先补默认再验证组合，未知/重复/负数/非整数/越界拒绝。`timeouts_ms.stream_idle`默认10000ms，范围10..300000。

每次上游recv解析后pending达high，网关从epoll移除该租约的channel；每次正数send后降至low才以新token恢复注册，由下一事件批次读上游。暂停仍持有租约，FIN/RST可能延后到恢复或绝对期限时观察。所有流仍不归池，没有重试或等待队列；硬256KiB检查保留为异常防线。

Runtime拥有唯一预算账本：所有会话构造前取16MiB预约，删除对象后归还；每个StreamOutput分配前另取固定256KiB子预算，销毁数组后归还。子预算包含在会话预约内，不是额外可用额度；pending空和暂停时不退数组容量。子预算不足返回503 `buffer_capacity`，不等待、不淘汰别的流。内部snapshot提供current/peak预约、数组容量、pending、pause/resume和有界终结计数；无外部管理接口。

stream_idle只由实际解码正文刷新，暂停保存剩余时长，恢复不会重新给完整窗口；流式写无进展期限仅实际send>0刷新。IO/解析返回后先检查旧期限，再允许进展或HTTP完成，等于截止也算过期。response/total仍绝对计时，暂停不冻结。SHUT_WR继续接收响应，RST/硬写错取消本地链路；这里只验证网关释放和模拟后端连接结束，不宣称真实GPU计算已停止。

Backpressure测试通过真实控制门观察三种定界各至少两轮暂停/恢复、暂停无recv、DEL/新token、暂停FIN/RST/信号和精确正文；正常请求及超时会话可在慢流仍暂停时完成。RSS与Socket buffer仅诊断，不能替代容量账本或作为内存收益承诺。见[Builder001](docs/builder/reports/V0.2/S2-report-001.md)和[变化记录](docs/references/V0.2-S2-changes.md)。

独立Debug/Release/ASan+UBSan各12/12，原response/total探针各18/18、关闭窗口20/20、解析/容量16项及分配/期限/水位附加探针通过，见[Reviewer001](docs/reviewer/reports/V0.2/S2-report-001.md)与[Leader002](docs/leader/reports/V0.2/S2-report-002.md)。本阶段初审通过、返工0/2；不承诺严格公平、RSS上限或真实GPU停止，S3真实CPU后端验证亦已完成，见下节。

## V0.2/S3 真实集成（已独立验收）

固定CPU llama-server b7481与Qwen2.5-0.5B-Instruct Q4_K_M完成真实直接/代理、长流/慢读、取消与故障恢复验证。资产隔离于build-local，不成为网关产品依赖；普通CTest离线、无模型要求，长run显式执行。产品src、固定输入及原HTTP/SSE子集保持，测试host没有成为产品管理API。

最终验收明确复用初审独立真实601.662秒/1270请求、模拟310.192秒/650请求、三构建各13/13以及原期限18+18、关闭窗口20/20。最后一轮只修异常attempt记录与必要包装，新增独立快测2/2、真实完整短校准87条、模拟50正式请求及13类异常/4个晚到失败对照；当时CTest注册14项，未作当时14/14全量执行声明。复用身份和边界见[Reviewer002](docs/reviewer/reports/V0.2/S3-report-002.md)，初审FAIL及原丢失反例保持。

两次返工分别为二进制清单33→36计数文档纠正和异常attempt取证修复，累计2/2，无债。取消证据覆盖网关资源、连接和固定CPU后端slot观察，不保证GPU内核停止；容量账本不等于RSS/内核内存，固定负载结果不推导严格公平或性能收益。

[运行说明](tests/integration/README.md)、[来源变化](docs/references/V0.2-S3-changes.md)与[Leader002](docs/leader/reports/V0.2/S3-report-002.md)提供复现及审计入口。自有模型/host/gateway均已回收。V0.2开发验收成果已本地提交555b65d，远端本轮未核验，未正式发布；不启动V0.3。

## V0.2/P1 性能基线专项（已独立验收）

用户确认在开发V0.3前先测性能基线；P1独立于已关闭S3，返工从0/2开始。[设计](docs/leader/designs/V0.2/P1-design.md)、[审查计划](docs/reviewer/reviews/V0.2/P1-review.md)和[Leader001](docs/leader/reports/V0.2/P1-report-001.md)冻结有限模拟成本/并发/慢读资源与真实CPU模型TTFT/E2E/闭环完成率对照。现已获[Reviewer001 PASS](docs/reviewer/reports/V0.2/P1-report-001.md)和[Leader002收口](docs/leader/reports/V0.2/P1-report-002.md)，累计0/2，无债；未修改产品/优化，未启动V0.3/V0.4。

新计量区分HTTP终态、EOF和校验结束，使用正式Release程序测成本；测试host仅单列资源诊断。保留失败及全部重复，分位数差不称单请求额外开销，闭环完成率不称容量极限。完整结果见[性能结果报告](docs/performance/V0.2/P1-results.md)，普通CTest不自动执行完整性能矩阵。

- 2026-10-20：接续2026-10-19的P1独立初审PASS，由Leader002收口，0/2、无债。两角色72单元各19,380含预热attempt均无失败；PR约44ms及工具控制限制保留，不声明容量/优化收益。待协调者本地提交、不推送，V0.3/V0.4未启动。

## V0.3/S1 收口历史快照（2026-10-20）

当前分支 `codex/v0.3-s1-routing-health`，起点为P1本地提交 `e231fda25879060fcd730f562982f06448f2ba11`，未推送。P1已本地提交；S1现已通过[Reviewer002 PASS](docs/reviewer/reports/V0.3/S1-report-002.md)，由[Leader002](docs/leader/reports/V0.3/S1-report-002.md)收口，**已完成**，累计返工1/2、无债。待协调者本地提交、不推送；V0.3整体/MVP未完成，S2尚未启动。

[设计](docs/leader/designs/V0.3/S1-design.md)、[审查计划](docs/reviewer/reviews/V0.3/S1-review.md)与[Leader001](docs/leader/reports/V0.3/S1-report-001.md)固定静态模型映射、RR/Least Inflight、每实例隔离池和被动健康：失败阈值摘除、冷却后单真实请求试探，无自动重试。请求inflight在上游终结释放；旧单上游配置行为保留。

Available初始仅为配置许可，恢复需完整HTTP成功，TCP可达不等于模型请求服务可用；不验证生成语义/GPU，空闲时不主动探测。S2排队/推理容量、S3综合验收及V0.4性能优化未开始，P1约44ms现象不在本阶段修复。完成后按用户规则本地提交、不推送。

## V0.3/S1 模型路由配置与被动健康

新配置见 [routing-example.json](config/routing-example.json)，使用原 `--config` 启动入口；示例端口需对应你自己的推理实例，静态 `model` 名必须与后端实际服务能力一致。`models` 与旧 `upstream_address`/`upstream_port` 互斥。旧JSON和程序内只填旧地址的配置继续单上游透传任意合法model，不启用摘除；原默认样例不变。

`models` 为1..32组，总实例1..64，每组至少一个。组名为1..256个UTF-8字节，无ASCII控制字符；精确匹配请求model（不折叠大小写或空格、不重写别名），组名唯一。实例 `id` 组内唯一，为1..64字节ASCII字母/数字/`_.-`；`address` 是非0.0.0.0的数值IPv4，`port` 为1..65535，禁止自指（包括实际绑定端口复查）。组内地址端口不能重复，跨组可重复，但各组池和健康独立，不代表物理服务器容量隔离。

`policy` 默认 `round_robin`，也可为 `least_inflight`。RR按配置顺序轮转；LI取尚未完成上游请求数最少的实例，平局轮转。请求数包括连接/上传/等待/未完成流，不包含idle连接，也不包含上游已完成后的下游排空。未知model返回404/`model_not_found`，无可选实例返回503/`no_available_backend`，均不访问后端。选中实例的连接池满返回503/`upstream_capacity`；本阶段无改选、重试、请求排队或推理准入额度。

`health` 仅用于新模式，默认 `failure_threshold=2`（1..16）、`cooldown_ms=1000`（10..300000）。Available仅表示配置允许运行，启动时未验证模型加载。当前epoch完整合法HTTP 2xx清失败计数；3xx、401/403/404、5xx及明确上游传输/协议/上游deadline失败计数；其他4xx（含400/429）、客户端取消、本地预算/输出上限、池满、总deadline及背压暂停时response deadline中立。状态码只在完整HTTP终结后观察，不把TCP连接、响应头或流首片当成功。

达到阈值后实例Ejected并清idle，旧在途请求可自然完成但不能恢复新epoch或重新归池。冷却到期且旧请求归零后，下一次普通请求可占唯一Trial资格；成功恢复Available，失败或中立（含取消/停止）重新冷却。没有后台探针/健康定时器，无流量就不恢复；试探请求自身可能失败，也不会自动重试。**健康只验证既有HTTP协议，不验证生成内容或SSE业务错误、模型权重、GPU/模型质量；完整2xx中的应用错误不在S1识别范围。**

每实例沿用 `upstream_pool`：max_connections 1..256、max_idle 0..256且不超过前者；总实例数×max_connections≤1024。全局Session/内存预算不随实例数放大。配置≤65536字节、最大解析深度6；重复键、未知键、类型/范围错误和缺必填字段拒绝启动。Runtime内部测试快照含逐实例inflight/健康epoch及pool计数，无管理HTTP端点；聚合peakTotal为各池峰值之和的上界，不是同时峰值。

新增快速测试 `Routing`（确定性时钟、租约和Session门控）及 `RoutingE2E`（受控四实例、配置负控、三轮恢复与停止）；普通CTest仍无真实模型或下载依赖。阶段最终验收以Leader/Reviewer报告为准。

## V0.3/S2 准入与有界等待

模型模式可使用 [admission-example.json](config/admission-example.json)。只有显式提供 `admission` 对象才启用；省略保持 S1 即时路由行为，legacy 单上游配置不接受该对象。对象中的字段均可省略：

| 字段 | 默认值 | 范围与含义 |
| --- | --- | --- |
| `max_inflight` | 16 | 1..256，全进程未完成上游请求之和 |
| `max_inflight_per_backend` | 4 | 1..max_inflight，每个模型实例独立限额 |
| `max_queue_requests_per_model` | 16 | 0..256，每模型 FIFO 条数；0 禁止等待 |
| `max_queue_bytes_per_model` | 4194304 | 0..268435456，每模型逻辑请求字节；0 禁止等待 |
| `queue_timeout_ms` | 1000 | 10..300000，入队起等待期限 |

`inflight` 在上游 HTTP 完成时释放；下游仍在排空的连接可能继续占用连接池。它与 `upstream_pool.max_connections`、客户端 `max_connections` 是三个不同限制。等待请求没有上游请求/连接租约，也不占 streamCapacity，仍保有原来的每会话 16MiB 内存预约。

队列逻辑字节是已解析 method、target、body 的字节数，加各 header 的 name/value 字节数与4，再加固定1024；不是 RSS，不是新申请的一份正文预算，不与16MiB相加。队列按条数、字节顺序拒绝，分别返回503/queue_full、503/queue_bytes_exceeded。只有需要等待的请求受队列字节阈值限制，可立即派发时不会因该阈值过小被拒。

所有模型队列非空时，新请求也先入本模型尾部；调度按模型游标逐个查看队头，单次至多处理32个，阻塞模型不会阻止其他有容量的模型。未知模型404/model_not_found，无健康候选503/no_available_backend；这是容量等待，不等待故障恢复。出队重新选当前健康实例，取连接池失败则503/upstream_capacity并中立释放请求租约，不重排、不改投、不重试。

Waiting截止为 `min(accept + total, enqueue + queue_timeout)`，total从接收连接起不重置；相同时504/total_timeout优先，否则504/queue_timeout。RST/明确读写错误会取消，完整请求后的 `SHUT_WR` 保留等待并允许响应；TCP FIN不能证明用户完全离开。停止时等待者收到503/gateway_stopping并退出队列，活动请求按原停机期限收口。

健康仍是 HTTP 协议级被动观察，不验证生成语义。没有优先级、后台健康探针或长期公平/SLO承诺。本阶段新增 Admission、AdmissionE2E（总计19项CTest），固定24条长短混合观察由 `tests/admission/RunAdmission.py <AdmissionRuntimeHost> --mixed <raw.json>` 显式运行；测试host记录实际入队和派发时间而非将线程编号当FIFO，并带原始样本/取消负控。它含观察写盘开销，不是性能基准；有限成功样本不能证明长期无饥饿或公平收益。

## V0.3/S2 已验收边界

显式admission配置控制global/perbackend未完成上游请求和每模型count/逻辑byte FIFO；省略保持S1/legacy。Waiting仅保留原请求及Session预约，无上游租约；出队重查健康/容量/原total期限。Runtime在回调结束后32步有界轮转、合并续轮，RST退账而完整请求SHUT_WR保留响应。

独立三预设各19/19、追加122断言与7条charge检查、FD4→4；Release固定24请求一次全部成功，22排队/2直派，FIFO一致，global峰2/perbackend峰1，终态全账归零。有限等待观察不证明长期无饥饿或性能收益；无真实模型/GPU新验收，不处理P1约44ms。见[Reviewer001](docs/reviewer/reports/V0.3/S2-report-001.md)及[Leader002](docs/leader/reports/V0.3/S2-report-002.md)。

## V0.3/S3 最终开发验收

独立Reviewer002 PASS，累计2/2：第1轮纠正文档歧义，第2轮修复新验收工具运行期128MiB存储预算。复用修复前独立debug/release/asan各20/20及真实28条（26成功含2预热、2取消）、模拟29条（19成功、2取消、2后端失败、1队列超时、5拒绝）作为产品/矩阵功能证据。新预算经7类负控、正常host、三套MvpDetectors及Reviewer自写3负控验证；没有在新预算下重跑正式矩阵。

账本100ms、资源1s为采样目标周期，含调度/轮询/写盘开销，非硬实时“至少每100ms”；峰值观察不独立证明瞬时上界。真实慢读未触高水，CPU双实例共享资源，小样本不证明容量/SLO/长期公平或性能收益；P1约44ms现象未修。见[验收记录](docs/acceptance/V0.3/S3-results.md)和[操作说明](tests/mvp/README.md)。V0.3/MVP开发验收完成、未发布，后续阶段未启动。

## V0.4/S1 公平性能基线（已独立验收）

新增独立实验工具覆盖连接成本、慢读背压、RR/Least Inflight、准入排队及固定CPU真实后端。每角色57cell已包含三重复，7104正式与486预热分别统计；正常CTest只执行短检测器，完整矩阵需显式运行，资产与命令见[实验操作说明](tests/experiments/README.md)。

[结果与双角色比较](docs/performance/V0.4/S1-results.md)、[独立验收](docs/reviewer/reports/V0.4/S1-report-002.md)、[Leader收口](docs/leader/reports/V0.4/S1-report-006.md)保存全部分母、负面结果及工具限制。LI在固定异质合成负载下的达标goodput较高，增加队列在固定SLO下反而降低goodput；发压敏感/客户端CPU标记触发，不能外推策略因果收益、生产容量或真实GPU效果。N仅调整合成后端NODELAY作诊断，产品未优化。

测试修复区分high触发与合法迟滞观察，并分别验证finished活对象仍保留16MiB预约、正常析构后全归零；仅改测试，产品生命周期不变。原Release联合断言的现场子值未知，历史FAIL/Stop保留，不能追溯宣称根因已复现。S1累计4/4、无债，S2未启动。

## V0.4 已验收配置实验

S1公平基线与S2单一等待预算实验均完成；[操作与三份完整配置](tests/queue_budget/README.md)、[双角色结果](docs/performance/V0.4/S2-results.md)。配置区分无队列、500ms实验基线和100ms候选，均非生产通用推荐；产品默认1000ms保持。唯一旧测试改动是停止请求幂等清理，产品源码未变。原独立run001外层143中断原因仍未知；新run002完整通过，不回填旧根因。

## V0.5/S1 L4LB 组合联调

[运行说明、完整配置与故障矩阵](tests/l4lb/README.md)使用真实用户态TCP L4LB、两个Gateway和可控HTTP/SSE后端。下游每连接单请求关闭；L4按连接绑定，故障流不迁移，TCP握手不代表模型可用；准入额度仍为每Gateway独立。当前验收状态见页首。

## V0.5/S2 拓扑成本与长流边界

[固定矩阵与复现说明](tests/l4lb_cost/README.md)比较直连单Gateway、客户端均分双Gateway及L4接入双Gateway的延迟、CPU和各段用户态TCP载荷字节；单列长流连接数均衡但在途偏斜的构造反例。固定60req/s本机合成观察不证明横向扩展容量或真实推理收益。当前验收状态见页首。

## V0.6 性能优化规划

功能验收后继续进行容量摸底和性能优化，不将V0.5固定60req/s视为容量上限。[版本计划](docs/leader/designs/V0.6/version-plan.md)分为S1容量摸底与归因、S2针对性优化、S3组合复验；当前已启动[S1](docs/leader/designs/V0.6/S1-design.md)测量设施实现与校准。S2/S3详细方案根据证据确定，不提前承诺QPS或指定优化技术。
