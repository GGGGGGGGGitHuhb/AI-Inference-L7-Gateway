# AI Inference L7 Gateway

面向在线文本推理服务的独立 C++ 七层网关项目，计划围绕流式代理、资源控制和请求调度建立可复现的工程实验。

**项目定位：独立项目、按需复用、最后联调。** Gateway 独立接收客户端请求；按需复用已有 HTTP Server、L4LB 的合适组件和工程经验；完成独立能力后，再验证与 L4LB 的组合部署。

## 当前状态

**V0.2流式可靠性开发验收已完成。** S1/S2/S3均已独立接受，累计返工分别1/2、0/2、2/2；S3唯一失败attempt取证发现已关闭，无剩余发现或债项，见[Reviewer002 PASS](docs/reviewer/reports/V0.2/S3-report-002.md)与[Leader002收口](docs/leader/reports/V0.2/S3-report-002.md)。V0.3未开始，尚未正式发布。

V0.1/S3与V0.1基础代理已完成开发验收。 S3经一次有限规范纠正后取得[Reviewer002 PASS](docs/reviewer/reports/V0.1/S3-report-002.md)，唯一空行规范发现关闭，无未解决发现或债项；收口见[Leader002](docs/leader/reports/V0.1/S3-report-002.md)。累计返工：S1 2/2、S2 1/2、S3 1/2，各阶段独立记录。

当前开发分支 `codex/v0.2-s3-integration`，起点为V0.2/S2本地提交 `d933e8892033a600b68ff5ac0db950dec5abea90`，远端状态本轮未核验。V0.1提交d653e9c已推送阶段分支（协调者此前核验）。S2已本地提交；S3已验收收口、待协调者按既有授权本地提交，不推送。没有正式发布，开发验收完成不等于发布。

已验收：独立离线构建、最小复用组件、受限HTTP/1.1与文本JSON、单静态上游非流式代理、硬限额和分类deadline、信号停止，以及有界上游顺序复用与初始合成成本基线。下游继续每连接单请求；V0.2/S1新增SSE字节增量链路已独立验收；多后端、路由/队列、真实GPU和L4LB联调仍属后续阶段。S1与S2历史验收见[Leader S1-004](docs/leader/reports/V0.1/S1-report-004.md)、[Leader S2-003](docs/leader/reports/V0.1/S2-report-003.md)。

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

Release 与 AddressSanitizer/UndefinedBehaviorSanitizer：将上述三个命令的 `debug` 分别换为 `release`、`asan`。每个预设当前注册14项CTest（含StreamingParser/StreamingE2E/Backpressure及IntegrationDetectors/IntegrationAttempts）；S3实际验证范围见文末，注册数量不等于本轮全量执行结果；AssertionFailure 使用预期失败验证 Release 下检查仍有效。Pool、ReuseE2E、Runtime、GatewayE2E 和 MockBackend 需要本机 loopback socket 权限，会自动申请临时端口并回收自己的子进程；权限不足即失败，不跳过。

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

chunk 扩展先按完整原始大小行校验，再仅将大小与 CRLF 交给 llhttp；原始线缆/行预算和消费量保持独立计量。初次复用记录中的后置扩展校验描述属于旧实现，当前以 Approved 返工 001、Builder 002 和 Reviewer 002 的实现及验收说明为准。原设计/审查/返工中的阶段状态保留为历史快照，S1收口状态见Leader004；项目当前阶段以本页、ROADMAP和V0.2/S2最新Leader报告为准。

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

按用户最新指令“以后每次工作完成都提交，不推送”，每次工作验收/收口后由协调者完成本地提交，禁止自动推送；历史报告中的未提交/禁止提交仅描述当时授权与快照。V0.2/S1已本地提交2f7cf8；S2已本地提交d933e88；当前S3已验收收口、待协调者本地提交，不推送；不推断S1远端状态或发布。

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

最终验收明确复用初审独立真实601.662秒/1270请求、模拟310.192秒/650请求、三构建各13/13以及原期限18+18、关闭窗口20/20。最后一轮只修异常attempt记录与必要包装，新增独立快测2/2、真实完整短校准87条、模拟50正式请求及13类异常/4个晚到失败对照；当前CTest注册14项，未作当前14/14全量执行声明。复用身份和边界见[Reviewer002](docs/reviewer/reports/V0.2/S3-report-002.md)，初审FAIL及原丢失反例保持。

两次返工分别为二进制清单33→36计数文档纠正和异常attempt取证修复，累计2/2，无债。取消证据覆盖网关资源、连接和固定CPU后端slot观察，不保证GPU内核停止；容量账本不等于RSS/内核内存，固定负载结果不推导严格公平或性能收益。

[运行说明](tests/integration/README.md)、[来源变化](docs/references/V0.2-S3-changes.md)与[Leader002](docs/leader/reports/V0.2/S3-report-002.md)提供复现及审计入口。自有模型/host/gateway均已回收。V0.2开发验收完成、待本地提交，未推送或正式发布，不启动V0.3。
