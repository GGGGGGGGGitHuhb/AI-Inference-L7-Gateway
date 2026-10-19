# V0.1/S2：独立单上游非流式代理

## 1. 权威、状态和授权

- 状态：`Approved`；阶段：`待实现`；日期：2026-10-18；批准人：Leader (Zeus)，按用户技术委托采纳。
- 最新授权：用户“推送好了，开始s2吧”，结合此前“你来决策吧”和显式 Olympus 执行授权。本次为新阶段，累计返工 **0/2**；S1 历史累计 2/2 保留，不再修改其成果或历史权威。
- [Leader 决策报告](../../reports/V0.1/S2-report-001.md)、[独立审查计划](../../../reviewer/reviews/V0.1/S2-review.md)、[架构](../../../../ARCHITECTURE.md)、[路线](../../../../ROADMAP.md)。S2 当前没有返工文件；S1 rework-001 的协议修正已包含在前置代码中，不能回退。
- 基线提交 `bb318d8c55f5851d27cd52e6cd3367f450a5d8dd`，分支 `codex/v0.1-s2-proxy`；S1 Reviewer 002 PASS、Leader 004 完成。S1 已推送到同名阶段远端分支（协调者 ls-remote 验证），没有 main 合并或正式发布证据。
- 本文件和审查计划是实施要求，非已运行结果。Builder 仅在本基线范围实现；批准后改变行为/接口/范围/验收须新返工权威，不静默修改本文件。

## 2. 目标和非目标

交付 `ai-inference-gateway` 可执行程序：客户端向本机网关提交 S1 文本 API 请求，网关向一个静态 HTTP 上游新建连接，发送规范化请求，完整收取有界非流式响应并回传，随后关闭上下游连接。

纳入：单 Worker LT epoll、监听/接入、异步 connect、短读短写、协议校验、基础硬限额、分类绝对截止时间、取消清理、有限停止排空、可重复真实 Socket E2E 测试。无 GPU/Server/L4LB 运行依赖。

排除：S3 连接池与顺序 keep-alive、HTTP pipelining、多上游/模型路由、排队、自动重试、SSE、TLS、DNS、IPv6、多 Worker、真实 GPU 和性能提升承诺。一次下游连接最多派发一次上游请求；`model` 校验但不参与路由，所有合法模型名发往配置的唯一上游。

## 3. 复用决定与模块职责（REQ-01）

Server 固定来源 `2a93aa7f492640902386677c4d901b0fd193bb09`，迁入 `include/net/{EventLoop,Channel,Epoller}.h` 和 `src/net/{EventLoop,Channel,Epoller}.cpp` 六文件至 Gateway `src/net/`。使用 `git show` 固定源，不复制存在修改的 Server 工作区。直接闭包为已迁入 NonCopyable、TimerQueue，以及标准库/Linux epoll/eventfd；不需要 Server 的 TcpServer/TcpConnection/Acceptor、线程池、业务服务或配置系统。

来源已有：单调 token 注册表、fd 去重、回调后 cleanup、线程归属校验、事件与定时器分派、有限任务队列和停止控制。保留这些安全语义，按 personal-cpp-standards 调整命名空间、具名回调和 setter 分组，绑定现有 TimerQueue API。允许移除指向源项目测试/业务类的无效 friend、注释与未使用耦合；不以本阶段重写通用事件框架。保留的跨线程任务设施不用作新增业务 Worker。

- `src/net/`：Epoller/Channel/EventLoop；Socket 可增补受控 IPv4 bind/connect/读写帮助方法，但不得承载 HTTP/会话业务。FD 所有权保持 RAII。
- `src/app/`：main、启动参数/配置、信号及装配，不解析 HTTP。
- `src/gateway/`：运行时、有限会话注册表、代理会话状态与终结；复用既有 TextRequest 校验。
- `src/upstream/`：如有需要放异步连接辅助；仅一个目标，无池/健康调度。小型连接状态也可先放会话内部，Builder 决定低层文件划分。
- `src/http/`：沿用 S1 解析器与规范化；补受控 `Connection: close` 序列化策略，不通过字符串搜索任意正文插入头。保持原默认接口/测试兼容，可增加明确选项或辅助接口。
- `tests/`：事件组件和会话单元测试、Python 标准库进程/Socket E2E、扩展模拟后端。

新增 `docs/references/V0.1-S2-reuse.md/.json` 保存六文件源/目标散列和语义差异；S1 来源清单及第三方快照不改。若修改 S1 Socket/规范化等目标文件，S2 记录基线散列及差异，不能覆盖 S1 历史来源记录。按来源固定版本审查迁入事件代码，不把旧仓库既有测试通过作为新项目验收。

## 4. 启动与配置（REQ-02）

命令接口：`ai-inference-gateway --config <path>`；`--help` 退出 0。无配置/未知或重复 CLI 参数为错误；读取一次 JSON 文件（最大 64 KiB），不写回。重复键、未知字段、错误类型、非有限数字、无效组合在监听前拒绝，退出 2；运行时启动/系统致命失败退出 1；受控 SIGINT/SIGTERM 停止退出 0。

JSON 顶层对象，嵌套对象仅 `timeouts_ms`；必填 `upstream_address`、`upstream_port`，其余缺省如下。地址只接受 IPv4 数字字符串，无 DNS；端口必须整数，禁止 bool/浮点冒充。使用不同于推理请求的受限配置解析，64 KiB 上限允许有界 DOM，但必须检测重复键。

| 配置 | 缺省及有效范围 |
| --- | --- |
| listen_address | `127.0.0.1`，合法 IPv4；用户可显式指定 `0.0.0.0` |
| listen_port | 8080，0—65535；0 用于系统分配测试端口 |
| upstream_address / upstream_port | 必填，IPv4 目标；拒绝 `0.0.0.0`，port 1—65535；拒绝明确指向自身监听端点的配置 |
| max_connections | 16，1—256，含接收中、转发中和下游排空中的会话 |
| max_reserved_bytes | 268435456，16777216—4294967296，64 位无溢出整数；按 §7 固定每会话预约 |
| timeouts_ms.request | 10000，10—300000，从 accept 到完整合法请求 |
| timeouts_ms.connect | 3000，同范围，从开始 connect 到确认成功 |
| timeouts_ms.upstream_write | 5000，同范围，从 connect 成功到请求完整发送 |
| timeouts_ms.response | 30000，同范围，从 connect 成功到完整最终响应 |
| timeouts_ms.downstream_write | 10000，同范围，从首次待写响应到全部送入下游内核 |
| timeouts_ms.total | 60000，同范围，从 accept 到会话完成，不随进展重置 |
| timeouts_ms.shutdown | 3000，同范围，从首次停止信号到强制终结 |

各阶段受自身 deadline 与总 deadline 最早者约束，允许测试配置短 total，不要求各阶段时长求和。协议大小预算保持 S1 常量，不扩大兼容性或增加调参面。

成功 bind/listen 后 stdout 单行 `READY <IPv4>:<实际端口>` 并 flush，先完成必要回调/信号注册；失败不输出 READY。启动摘要及有限错误可写 stderr，不输出 prompt、请求体、响应体或认证字段；不为每片数据打印日志。提供 `config/example.json` 合成示例，README 说明安全默认 loopback 与实际启动方式。无外部服务、费用或持久数据变更。

## 5. 请求路径与协议（REQ-03）

1. accept4 或等价非阻塞 CLOEXEC 接入，先预约会话容量，再注册读取。同步 recv/send/connect 都使用非阻塞 FD。
2. 分片进入 S1 request parser，沿用原头/正文/wire/chunk/JSON 上限。完整后调用 validateTextRequest，失败映射原 HTTP 状态，且绝不访问上游。Expect 在头部已知时立即返回 417，不等待正文。
3. 合法请求规范化，Host 重建为配置 IPv4:port，移除原逐跳/客户端认证头，加入 `Connection: close` 和原 Via。原始解码 JSON 保持不变；完整请求未通过校验之前不建连、不发送。
4. 每会话新建一个非阻塞上游 TCP Socket。connect=0 或 EINPROGRESS 按状态处理；事件就绪后检查 SO_ERROR，不能把可写直接视为成功；失败不重试。
5. 分段发送请求，同时从 connect 成功后监听上游读取，以接受早期最终错误响应；不能因请求尚未全部发送而死锁。完整合法最终响应提前到达时允许停止剩余上传、关闭上游并回传；不重发剩余请求。所有 1xx/EOF/chunked/204/304 依 S1 契约。
6. 完整收取且验证响应之后才向下游发送最终头/正文。协议错误、超限或截断时可返回 502，不泄露部分上游正文。合法最终状态含 4xx/5xx 保留。响应规范化与错误响应均含 `Connection: close`；无正文状态不添加错误正文/不伪造 CL。
7. 处理短写，全部输出进入 Socket 后关闭连接并释放会话。这只证明提交内核，E2E 客户端另验证完整收到，不能称为应用层确认。

不支持第二条请求：同次读取中的第一条消息尾部只用于丢弃，不能交给上游或解析成第二条。后续下游额外数据可有界读取并丢弃以观察 RST/EOF，不累计保存，不取消已完整合法的第一条；每个事件有处理预算（§7），总 deadline 不重置。完整响应尾随数据同样不解析为第二响应，上游不归池。

## 6. 所有权、事件安全与取消（REQ-04）

单一线程拥有 EventLoop、注册表和所有会话；监听与信号亦由此线程处理。运行时持有会话所有权；会话持有两端 Socket、Channel、解析器/输出缓冲与定时器 ID。Channel 仅观察 FD，先注销再 close；销毁顺序先会话/监听/信号 Channel，再 EventLoop。不能捕获悬空 this；延迟任务用稳定 session ID 查表，或保证外部所有者直到回调返回才释放。

所有注册事件使用单调唯一 token 而非 fd 或裸指针作为 epoll 标识；同批旧事件若对应对象已移除，则忽略。禁止回调执行期间销毁该回调所在 Channel/std::function；终结仅置位并注销/取消，EventLoop 的回调后清理点才删除会话。定时器与事件路径均须清理，且后续事件不得再次释放预约。token/ID 耗尽明确失败，不回绕。

EPOLLERR/HUP/RDHUP 与 IN/OUT 可以同时出现，不能先 close 而漏掉缓冲中的完整消息；按当前连接状态 drain/read 并判断 SO_ERROR/EOF。EINTR 重试但重算时钟，EAGAIN 保留偏移/兴趣；无待写数据时禁用 EPOLLOUT，避免忙循环。发送使用 MSG_NOSIGNAL 或等价受控 SIGPIPE 策略。

下游 FIN/`shutdown(SHUT_WR)` 不等于取消：完整请求后继续回响应；未完整请求 EOF 返回 400（若还能写），然后关闭。RST、不可恢复下游读写错误终结会话并关闭上游；上游连接终止不宣称 GPU 计算停止。TCP 无法仅凭 FIN 区分完整 close 与半关闭，保留截止时间限制；不以“所有客户端退出均立即可检测”验收。可检测取消须在下次事件处理时释放资源。

状态职责至少区分接收、建连、上游写入/响应接收（可重叠）、下游排空和终结；终结原因与状态分开。恰好一次释放 FD/定时器/会话计数/预算。局部 Socket/解析异常不终止其他会话；epoll 核心失败等不可恢复运行时故障关闭全部资源后退出 1。bad_alloc 可无法生成错误响应，允许关闭受影响连接，但不得继续泄漏/重复计数。

## 7. 容量与公平处理（REQ-05）

沿用 S1：请求解码正文 1 MiB、wire 4 MiB；响应正文 4 MiB、wire 8 MiB，其余解析上限不变。规范化输出分别最大 `1 MiB + 64 KiB` 和 `4 MiB + 64 KiB`（覆盖原头部和重建头）；错误响应不超过 4 KiB。任何检查都在追加/分配前作溢出安全比较。

每会话保守预约 **16 MiB 协议存储额度**，接收前要求 `active < max_connections` 且 `reserved + 16 MiB <= max_reserved_bytes`。默认最多 16 个活动会话，无等待队列；额度不足时 accept 得到的 FD 立即关闭，不创建解析器/输出缓存，也不承诺容量外必然返回 HTTP 503。临时 accept FD 最多一个。监听 backlog 固定 128，不把内核 backlog 算作用户态请求队列。

必须说明并验证每会话有界存储上界：两个解析器有界头/正文、请求和响应输出、至多 64 KiB IO scratch、至多 4 KiB 错误输出、规范化临时副本/头处理和有界 JSON 元数据。请求输出发送完即释放；响应规范化后释放旧响应状态，避免长期重复持有。Builder 在报告列实际最大同时存在的**逻辑字节**及副本，须落在 16 MiB 内；不能另设隐藏无界缓冲。此额度不是分配器 capacity、元数据或进程 RSS 的精确承诺；metadata/会话数量另由字段/JSON/连接上限约束。若实现需要超过该额度，应调整内部所有权，不能静默提高预约数值。

维持可测试 `activeSessions`、`reservedBytes`、活动 upstream/定时器等内部快照，高水位与终结回归用于测试，不增加 HTTP 管理接口。拒绝/异常后保留其他会话继续服务。每次监听分派最多 accept 32 次；每方向一次回调最多处理 64 KiB（或更小），剩余由 LT 后续唤醒，避免一个热连接饿死定时器/停止。定时器处理前后都按单调时钟核对，不依赖每次有流量延长绝对截止时间。

## 8. 超时、错误和停止（REQ-06）

`steady_clock` 计时，每会话可用一个最早截止时间定时器，状态变化重排；不能重置 accept 时刻。计时器到期与 IO 同轮按重新检查的当前时间确定，不让过期请求因事件先处理成功而无限延长。短超时测试容许系统调度误差，但不能持续增长。

| 原因 | 下游行为（尚未发送最终响应时） |
| --- | --- |
| S1 请求/API 错误 | 原状态和稳定 code；405 有 Allow；不联系上游 |
| 请求接收 deadline | 408，`request_timeout` |
| connect 失败、上游 IO 错误/协议错误/截断 | 502，`upstream_error` |
| connect deadline | 504，`connect_timeout` |
| 上游发送 deadline | 504，`upstream_write_timeout` |
| 响应完整性 deadline | 504，`response_timeout` |
| total 到期 | 接收阶段 408，其余 504，`total_timeout` |
| 内部可恢复资源失败 | 尽可能 500，`internal_error`，无法生成则关闭 |

下游写 deadline 到期或最终响应已开始后出现错误，只关闭，绝不发送第二个状态行。错误正文沿用 S1 JSON 结构，不回显原文。错误响应发送允许最多 `min(downstream_write, 1000 ms)` 的独立终结排空窗口，即使原 deadline 已到；这唯一附加窗口不能再次刷新，超过即关闭。shutdown 强制截止优先于这个窗口。

进程启动时阻塞 SIGINT/SIGTERM 并用非阻塞 CLOEXEC signalfd 纳入 EventLoop，不在异步信号 handler 内分配/操作 C++ 对象。首次停止关闭监听、不再接入，已有会话按原截止时间继续，最多 shutdown 时长；第二次停止信号立即强制结束。排空完成或强制时终结所有会话、取消定时器、注销 Channel、关闭 FD，然后停 EventLoop。退出不保留子进程/端口。没有单独健康服务或跨线程池。

## 9. 实施与证据（REQ-07）

顺序建议：固定六文件来源和事件组件回归 → 配置/监听/信号 → 单会话完整请求/异步上游/响应 → 限额/截止/终结 → 进程 E2E 和故障回归。Builder 创建 S2-breakdown 仅安排实施，不改本权威。

修改范围：根 CMakeLists/预设必要入口、`src/net` 的受控迁入、`src/app`、`src/gateway`、可选 `src/upstream`、必要 HTTP 输出策略、`config/example.json`、tests/support 与集成测试、S2 来源/Builder 文档和 README。新行为不能改坏 S1 协议；完整保留 S1 测试。第三方、旧项目和 S1 历史权威/报告/来源清单只读。没有安装全局包、Git commit/push/tag 或进入 S3 的授权。

新增 CTest 至少具有事件组件与网关进程集成入口；具体名称由 Builder 实现后报告，三套既有预设继续可用。构建时不联网、不依赖兄弟路径。实际运行 clang-format 18 于所有自有受影响 C++，命名/回调与正反例人工复核并留证。

## 10. 验收追溯

| 需求 | 验收标准 | 独立验证 |
| --- | --- | --- |
| REQ-01 / AC-01 | 六文件固定来源与适配可复核；事件token失效、注销/同批复用、回调后销毁、定时器截止/取消正确；S1 回归通过 | RV-01 来源审计及事件单元测试 |
| REQ-02 / AC-02 | 配置正负/重复键/大小/数值边界；READY端口真实；非法配置不监听、不访问上游；退出码符合约定 | RV-02 CLI和独立子进程测试 |
| REQ-03 / AC-03 | 真正 Client→Gateway→Mock 单次完整非流式往返；JSON与输出正文不变，头规范化，CL/chunked/EOF/1xx/无正文和早期响应正确；坏请求不派发 | RV-03 E2E+协议回归 |
| REQ-04 / AC-04 | 短读短写/EAGAIN/半关闭/RST/同批旧事件/异常竞态不丢字节、不重复关闭、不悬空；失败会话不妨碍正常会话 | RV-04 单元故障注入及真实 Socket |
| REQ-05 / AC-05 | N−1/N/N+1并发与预约边界成立，无额外队列；最大有界副本核算≤16MiB；取消/完成后计数归零、FD/定时器恢复，热连接不饿死其他连接 | RV-05 低限额和慢收发实验 |
| REQ-06 / AC-06 | 六类deadline及错误排空窗口/已发头关闭正确；信号一次排空、二次强制、到期退出；无监听/自有进程/资源残留 | RV-06 确定性时钟/IO与真实进程验证 |
| REQ-07 / AC-07 | 三套独立CTest、Release负断言、ASan/UBSan、格式和来源证据；README实际启动命令；没有把S2写成整个V0.1或发布 | RV-07 全回归及证据/范围审查 |

客户端慢写、上游慢读、响应迟滞、客户端慢读、断连、坏报文和容量拒绝须分别覆盖；不能以解析库测试替代真实代理链路。connect 超时不得依赖公网黑洞偶然性：用窄测试接缝注入 connect/EINPROGRESS/SO_ERROR/时钟，另保留真实 connect 成功/拒绝测试。短写也用 socketpair/小发送缓冲或确定性系统调用接缝保证触发；故障注入不成为产品 CLI/配置。检查次数不等于覆盖证明，Reviewer 必须独立补充关键反例。

## 11. 执行路线与交接

WSL2 `/bin/bash`、login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`；角色目录 `build-local/<role>/s2/{tmp,cache,evidence,debug,release,asan}`。脚本前创建并设置 TMPDIR/TMP/TEMP/XDG_CACHE_HOME；Builder/Reviewer 不共享可变构建、端口或进程。现有 preset 默认 Builder 目录，S2 使用 `-B` 显式覆盖，避免覆盖 S1 证据。Socket/loopback 是已知权限边界，必要时对精确测试作窄范围升级，不重复 EPERM、不跳过为PASS。

当前已有执行路线不需要重新探索 Windows/UNC。同级固定源只读；数据全为合成夹具。历史 S1 2/2 保留；本新阶段 0/2，后续纠正按 Olympus 累计，第三轮前停止。
