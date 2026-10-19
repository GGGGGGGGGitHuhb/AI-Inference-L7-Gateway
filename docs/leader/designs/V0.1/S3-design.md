# V0.1/S3：有界上游顺序连接复用

## 1. 权威与授权

- 文档状态：`Approved`；阶段：`待实现`；日期/批准日期：2026-10-19。批准人：Leader (Zeus)。编排 `Ready for Builder`。
- 用户最新指令“开始s3的工作吧”，结合此前“你来决策吧”及显式 Olympus 委托，授权按已批准路线开展S3；Leader在该委托内采纳本技术基线，无新增重大PM决策。批准包为本设计、[审查计划](../../../reviewer/reviews/V0.1/S3-review.md)及[Leader001](../../reports/V0.1/S3-report-001.md)。技术选择不代表实现或验收。
- 前置提交 `3cb65244312d2feef563c2fd755ae8447d4589c5`（S2本地提交），工作分支 `codex/v0.1-s3-connection-reuse`。未核验该提交远端状态，不宣称推送/合并/发布。
- 继承S1协议及rework-001、S2单请求代理及[rework-002](../../reworks/rework-002.md)、S2 Reviewer002 PASS与Leader003收口。新阶段改动以本文件为准；旧阶段权威和报告保留原字节。
- S3累计返工 **0/2**；S1历史2/2、S2历史1/2保留。第三轮纠正开始前按Olympus硬停止，不以报告编号重置。

## 2. 目标、范围与取舍

在唯一静态上游上，多个下游会话依次使用同一HTTP/1.1连接；连接有总量、空闲量与空闲期限，失败连接不得污染下一请求。保持单Worker、完整有界非流式响应、无自动重试。交付正确性证据和初始直连/代理成本记录。

**本阶段顺序keep-alive指上游跨会话复用。下游仍每连接只接收一条请求并发送Connection: close，保留S2分阶段关闭。** 原路线S3输出明确是上游池，架构允许每连接同时一个请求，并未要求本阶段下游长连接；不新增下游请求重置、流水线或队列。第二下游请求仍有界丢弃且不派发，首响应完整性回归保持。

纳入：上游池、唯一租约、复用资格、空闲故障探测/到期、池满立即拒绝、停止禁止新派发、资源快照、模拟后端长连接与成本脚本。排除：多上游、模型选路、排队/等待池槽、重试、SSE、TLS、DNS、IPv6、多Worker、真实GPU、生产性能承诺、提交/推送/发布。无新增依赖或兄弟仓库修改。

## 3. 模块与所有权（REQ-01）

强制约束：

- `src/upstream/`承担连接池、连接身份/租约、空闲期限与传输存活检查；不判断文本JSON或选择模型。`GatewayRuntime`装配且拥有池，池寿命覆盖所有会话；销毁顺序先会话及租约、再池、再EventLoop。
- 每个上游Socket任一时刻只有一个所有者，每个租约只能归还/失效一次。连接状态至少区分connecting/leased/idle/retiring；slot在建连前预约，connecting也占容量。连接ID、租约generation及事件token不可混同fd，溢出失败不回绕。
- 推荐池持有稳定连接条目和Channel，会话持有move-only租约句柄。实际低层类型/文件由Builder决定，但不得引入双所有者或保留旧会话裸指针的空闲回调。可通过稳定session ID查Runtime表；从pool回调到session前重新核对租约代次。
- idle→leased、leased→idle重新注销/注册事件取得新token，使同批旧事件失效；关闭也先注销再close。不能仅替换一个仍在执行的std::function、销毁正在执行的Channel/条目、或让旧timer关闭新租约。退休对象延后到EventLoop回调后cleanup析构；该保留集须有数量上界，不能无限累积。
- 池只保留传输元数据，不保存请求/响应正文或解析器。请求解析/正文、响应解析/正文、deadline继续归ProxySession；归池前清空本次消息状态，下一会话新建/完整重置解析器。
- `SessionIo`或等价窄接缝可增加非阻塞peek与可控时钟；不变成产品故障开关。所有生产Socket非阻塞/CLOEXEC，MSG_NOSIGNAL和每回调公平预算沿S2。

推荐流程：校验完整请求→获取租约/新槽→连接或立即复用→发送完整请求并接收完整响应→写下游→成功写半关闭后决定归池→下游继续独立有界closing。没有在pool内部等待的请求。

## 4. 配置、额度与错误（REQ-02）

新增可选顶层对象 `upstream_pool`；既有配置合法且应用下列默认值。仍拒绝未知/重复键、错误类型、非整数、溢出/非法组合，启动前报错退出2；不放宽原64KiB/嵌套/IPv4规则。

| 字段 | 默认 | 范围/语义 |
| --- | --- | --- |
| max_connections | 16 | 整数1..256，connecting+leased+idle的硬总量 |
| max_idle | 16 | 整数0..max_connections；0禁用归池，形成每请求新建对照 |
| idle_timeout_ms | 5000 | 整数10..300000；从归池时刻起算的固定空闲期限 |

嵌套配置省略字段使用上述默认；因此只把max_connections改小而未同步max_idle时，默认组合非法，应明确报错，README提供一致示例。池容量和下游max_connections独立，各自≤256；改变池额度不改变每会话16MiB预约或原进程max_reserved_bytes。

租用时先清理已到期/已明确失效的空闲项，选择可用idle（推荐最近使用优先）；无idle且总量未满时创建一个新连接，已满立即503 `upstream_capacity`，不发送请求、不等待、不重试、不借用其他目标。idle满时归还的连接直接关闭，不驱逐正在租出的连接；max_idle=0生成上游Connection: close并每次结束关闭。

全连接/内核FD边界：上游FD≤池max_connections，下游FD≤max_connections，临时accept FD最多1，另有固定监听/epoll/eventfd/signalfd。活动会话预约仍16MiB，含其解析器/输出全部S2存储；idle不分配协议正文，pool条目/回调/定时元数据由256硬上限及有界退休集约束。Builder必须给出最大同时存活条目/Channel/timer数量，禁止另设无界退役列表。最迟每业务事件/计时回调后cleanup清理退休项；允许本次回调内临时保留，不能保留到任意未来流量。

可测试快照增加poolTotal、poolLeased（含connecting和响应后待下游发送）、poolIdle、peakPoolTotal和新建/复用/丢弃/池满累计计数；计数须有定义，累计可饱和不回绕。activeUpstreams在README明确为当前leased，与poolTotal区别。idle定时器≤idle连接数（或单个最近期限timer），总timer≤activeSessions+poolIdle+1停止timer，固定基础设施另列。无HTTP管理端点或正文日志。

## 5. 复用资格与污染边界（REQ-03）

上游规范化请求在max_idle>0时不强制close；Hop-by-hop处理仍使用S1规范化接口，不沿用客户端Connection指令决定另一跳连接策略。下游Connection: close不要求上游close。上游是否可复用在**原始解析消息及传输状态**上判定，不能在去掉Connection头后猜测。

只有以下全部满足才可归池：

1. 当前请求所有规范化字节已成功写入上游，显式requestWriteComplete记录，不能因清空output/offset归零误判。完整响应在请求尚未写完时到达，允许按S2返回该响应但必须关闭上游。
2. 合法完整最终HTTP/1.1响应（包括合法204/304及有完整最终响应的1xx序列），CL/chunked/无正文可明确定界；非EOF-delimited；任何大小写或重复Connection字段内的close token均禁止复用。协议拒绝、超限、101、截断等沿S1/S2错误映射。
3. 当前read块的consumedBytes等于该块长度，无尾随字节；同块第二响应或任意未解释字节令连接不可归池。首个完整合法响应仍按S2返回，不把尾随内容当第二响应或追加正文。
4. 未观察到EOF/RDHUP/HUP、RST、SO_ERROR、读写失败、超时、取消或本地错误；不能因读到完整消息而忽略同轮关闭事件。正常状态码4xx/5xx本身不是禁止复用理由，只要其他条件满足；本地生成的网关错误一定失效租约。
5. 完整下游输出已经提交并成功SHUT_WR，释放时没有stopping；归池前非阻塞peek+SO_ERROR检查干净（见§6）。这是保守持有：慢下游仍占上游槽，避免响应完成后取消却已复用的生命周期歧义。

完整上游响应后、下游发送期间仍持有租约并监控上游读/关闭；任何迟到字节/EOF/错误都关闭上游，但不破坏已缓冲且合法的首响应。此阶段不得再喂终态parser或生成第二状态行。归池前下游RST、写失败、total/下游写timeout使租约失效。

成功SHUT_WR并归还后，下游进入S2 closing；后续closing EOF/RST/截止只作用于下游，旧会话必须已清空租约，不能关闭已经借给新会话的连接。这定义了正常请求完成/租约提交边界，不承诺客户端应用已读完。S2 rework-002的closing deadline、全额预约、EAGAIN不提前close和强制停止优先级保持。

## 6. 空闲、陈旧与无重试（REQ-04）

idle注册只读/错误/半关闭兴趣，无EPOLLOUT；任何可读数据、EOF、HUP/RDHUP或SO_ERROR都将其逐出，不解析、不缓存 unsolicited 数据。空闲期限在归池时设定，读事件/EINTR不刷新；到期先失效，归还不继承上一租约timer。归还检查和租出检查均需非阻塞 `recv(MSG_PEEK | MSG_DONTWAIT)`（至多1字节）+SO_ERROR：EAGAIN且error=0为当前干净，数据/EOF/硬错误关闭；EINTR在固定次数预算内重试，用尽保守关闭，不能阻塞。

租出前已发现脏/陈旧候选可丢弃，并在没有发送本请求任何字节时选择另一个idle或创建一次新连接。这是派发前获取连接，非重试；最多检查当前池容量个候选，禁止无界扫描。选择租约后，即使首次write失败或尚未发出字节，也**不自动换连接再发**，当前请求按502结束。请求写入/响应超时按S2的504分类；相应连接关闭。

清洁检查不能保证TCP连接未来存活，也不能识别恶意后端恰在新请求后发送、语法上与新响应无异的延迟报文。契约保证已观察/可探测残留不被重新派发及正常遵守HTTP的后端顺序隔离，不声称任意恶意后端的因果鉴别。此边界不能豁免同块尾随、持有期间迟到、idle可读或租出前peek已可见的数据；上述均必须有确定性反例测试。

复用成功时connectedAt/本请求发送与response期限从新租约启用时起算，不能沿用老连接创建时刻；total仍从本次下游accept起算。新连接connect deadline只用于建连；idle期限不代替活动请求deadline。超时竞争按单调时钟检查，任何阶段转换不刷新total。

## 7. 停止、清理与恢复（REQ-05）

首次SIGINT/SIGTERM在同一owner事件线程先标记stopping、关闭监听及所有idle、禁止获取新租约。已取得租约（包括connecting）的请求允许按原deadline继续，归还一律关闭；已接入但还在读请求、尚未取得租约的会话，在完成校验/尝试派发时返回503 `gateway_stopping`，不得新建或租出。现有不完整接收仍受原请求/total及shutdown deadline，不引入停止等待队列。

第二信号或shutdown期限立即finish全部会话、失效全部租约、关闭pool剩余FD、取消timer，cleanup后对象/预约/pool计数回归0再结束循环。首次停止且无会话时也清理idle/timer，不能因session map为空而跳过池析构工作。错误窗口/closing受shutdown截止优先约束，不能重排延长。

S2内部requestShutdown事件外连续调用的使用限制保持，本阶段不交付Runtime SDK。池集成不能依赖这种未经验证的方式来回收；所有产品信号/定时停止、回调后cleanup与析构必须验证。必要的内部清理调整仅为本阶段池生命周期服务，不声称原事件外接口已修复，除非另有明确实现与验证证据。

失败恢复：错误连接先从容量与事件注册中失效，退休对象安全析构；后续独立请求可获取新槽。租约返回/异常/析构/停止竞态仅释放一次；构造、注册或timer分配失败不遗留槽/FD。保留S2内部500（无法分配则关闭）与运行时致命退出1边界。不得为恢复重发旧请求。

## 8. 初始正确性与成本基线（REQ-06）

实现可重复Python标准库测试脚本 `tests/ProxyBaseline.py`，命令接口 `python3 tests/ProxyBaseline.py --gateway <Release二进制> --output <角色证据目录>/baseline.json`，只用合成loopback后端，自有临时端口/进程有界回收；不写默认全局目录。报告记录源码/二进制hash、系统/编译器、配置、模式和所有原始样本，不输出真实prompt。

预先固定矩阵：三种模式 direct-close、proxy-close（max_idle=0）、proxy-reuse（max_idle=16）；客户端均每次新建TCP连接，HTTP/1.1固定CL请求，合成请求正文包含256个ASCII字符content，固定JSON响应正文1024字节，后端无人工延迟；后端尊重Connection: close，否则支持顺序持久连接。并发1和4、闭环完成后发下一条，每cell预热20次后测200次，三次重复，单次请求超时5秒，单cell总上限60秒；顺序每重复轮换三种模式避免固定先后偏差。记录准确最终字节数和配置，禁止称固定到达率或真实推理负载。

统计每cell完成/失败/拒绝、总时长、完成QPS、客户端单调时钟端到端p50/p95/p99（明确nearest-rank）、后端accept/请求数及复用次数；采样网关/proxy-backend进程RSS峰值和FD峰值（说明采样间隔≤20ms、观测峰不等于真实极值，direct无网关）。连接计数区分预热与测量差量，proxy-reuse测量前保留预热池，不重启进程。成本仅并列报告分布和比值，禁止称两组p99相减为额外延迟p99。

预定通过边界：所有样本正文/状态精确且0失败/拒绝，close模式后端接受连接数=请求数；并发1持续复用模式预热+测量只需1个后端连接（空闲期限使用300000ms避免测试调度空闲过期），并发4≤4；测量前后FD/池计数与配置上限一致，停止后进程/端口无残留。**不设吞吐或时延收益阈值**：首次观测可慢于直连，不据此放宽正确性或虚构收益；异常成本明确保留待后续证据驱动分析，不自动引入优化阶段。Reviewer独立完整跑相同矩阵，允许数值不同，不允许丢弃失败重跑成成功记录。

## 9. 实施、测试与边界（REQ-07）

推荐M1：配置/池对象与租约单元测试；M2：ProxySession资格/移交与迟到事件；M3：容量/停止/独立真实Socket序列；M4：成本脚本、全回归与证据。Builder编写S3-breakdown，可决定具体类名及测试拆分，不改语义。预计改src/upstream、新接缝、ProxySession/Runtime、GatewayConfig、必要HTTP元数据/规范化、config/example、CMakeLists、tests/support、新增测试/README。net仅必要安全集成；不得顺手全框架重构。

S1/S2全部原测试及关闭窗口/握手回归保留；允许为新API装配改测试适配，不能删除行为断言或用max_idle=0遮盖全部新行为。涉及旧来源清单文件时新建 `docs/references/V0.1-S3-changes.md` 记录基线hash/当前hash/原因，历史复用manifest不改，third_party不改；Manifest当前只检查固定第三方，不要求篡改历史迁入目标hash。

新增CTest覆盖池状态和真实上游复用，可扩展Runtime或新目标；实际名称/命令在Builder报告明确。Debug/Release/ASan+UBSan完整CTest，Release负控exit1，实际clang-format18 -i和--dry-run --Werror覆盖修改的C++并人工复核分组/回调规范。不安装依赖。Builder报告001含每项AC证据、存储/对象上界、真实Socket与接缝区分、完整失败日志、当前源码hash；Reviewer独立报告001后Leader才可关闭S3和评估V0.1。

| 需求/验收 | 可观察通过条件 | 验证 |
| --- | --- | --- |
| REQ/AC-01 | 单一所有者、代次/token防旧事件、回调后析构、异常恰好释放；借还多轮无UAF/槽泄漏 | RV-01 状态接缝+Socket+sanitizer |
| REQ/AC-02 | 配置新旧兼容/非法拒绝，N−1/N/N+1总量及idle上限，满池503即时且零派发；计数/预算上界成立 | RV-02 配置/资源测试 |
| REQ/AC-03 | 多条下游分别得到自己精确响应；全部资格谓词和不得归池反例生效；S2首响应/closing保护不回退 | RV-03 分片/异常及真实E2E |
| REQ/AC-04 | idle到期/错误/污染与借出前探测关闭；借出后失败502无重试；本请求deadline重新起算而total不刷新 | RV-04 控时/短IO+真实故障 |
| REQ/AC-05 | 首次停止阻新派发且关闭idle，已有租约有限完成，强制/析构全清零；热事件下停止推进 | RV-05 信号/定时/故障与资源 |
| REQ/AC-06 | 固定18cell成本矩阵全部正确，有原始分布、连接模式/资源证据，无未经测量收益声明 | RV-06 独立Release成本基线 |
| REQ/AC-07 | 三预设全回归、格式/来源/文档与实现一致，范围无扩张，后续独立验收 | RV-07 全量回归与证据审计 |

## 10. 执行路线与恢复

WSL2原生 `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`。各角色专属 `build-local/<role>/s3/{tmp,cache,evidence,debug,release,asan}`；脚本/构建前创建目录并设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME，Reviewer不共享Builder可变产物。使用 `cmake --preset debug -B build-local/builder/s3/debug`，build/ctest显式目录；其余预设同理。已知Socket/loopback及LSan ptrace边界对精确验证命令窄升级，不重复已知失败，不跳过验收。记录命令/exit/权限限制，失败日志不覆盖。

没有项目AGENTS/角色指南/债台账；使用用户全局规则和plan-project-docs角色模板，当前无已接受债项，不为未来功能创建空债条目。若需要改变资格、池满策略、下游协议或成本验收，先回Leader出新编号返工；当前批准不覆盖静默扩大范围。不得因分支已存在推断提交/推送/阶段完成。
