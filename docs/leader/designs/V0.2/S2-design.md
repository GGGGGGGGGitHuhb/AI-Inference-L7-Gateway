# V0.2/S2：背压、取消与超时协同

## 1. 批准与前置

状态 `Approved`；阶段待实现；编排 Ready for Builder；2026-10-19。Leader (Zeus)依据用户“开始s2工作吧”、既有“你来决策吧”和Olympus授权采纳本阶段内选择；批准包为[本设计](S2-design.md)、[审查计划](../../../reviewer/reviews/V0.2/S2-review.md)、[Leader001](../../reports/V0.2/S2-report-001.md)。没有新PM待决策项。

起点 `2f7cf831a302fc87717afcae510e777187c7d0ef`，分支 `codex/v0.2-s2-backpressure`，初始干净；V0.2/S1已本地提交，远端本轮未核验。S1经[Reviewer002](../../../reviewer/reports/V0.2/S1-report-002.md)和[Leader002](../../reports/V0.2/S1-report-002.md)接受，旧Approved设计及历史报告保持原字节。本阶段返工0/2，各历史阶段计数独立保留；第三轮修正前按Olympus停止。完成后协调者本地提交、不推送，不扩大发布权限。

## 2. 目标、范围和兼容边界

为现有SSE字节代理建立可恢复的慢客户端背压：读入到高水位暂停对应上游，写出到低水位恢复；同时约束进程受控缓冲、流空闲、下游写无进展及总时长。正常允许的慢读完成必须逐字节完整；无限停读最终有界终止。取消、错误、完成和停止竞争只结算一次。

保持单Worker、单静态上游、下游单请求、opaque SSE、HTTP完整才生成零chunk、首个final字节被send接受才commit。stream=true包括非SSE回退仍不归池，非流式池资格/closing不变。固定流总body8MiB、wire16MiB和原解析限制不变。没有队列、重试、多后端、多Worker、GPU、SSE事件拼接/语义识别、新依赖或兄弟仓库修改。真实后端计算取消与稳定性留S3。

本阶段有意替换S1“满缓存结束”的正常慢读策略及流式连续非空批次写期限；原异常硬上限和response/total绝对期限仍有效。所有旧配置继续可解析；新增默认值自动生效。非流式/非SSE回退的写期限、错误排空窗口、closing及池策略不改变，不把流式策略强套到完整缓冲输出。

## 3. 模块与容量账本（REQ-01）

GatewayRuntime单线程拥有进程预算真值，会话只持有不可复制的预约/流容量凭证；可用小型gateway内部预算类型，不创建通用allocator框架。StreamOutput继续固定数组，ProxySession编排水位/计时；ConnectionLease提供窄暂停注册操作，EventLoop通用语义不重写。受控容量分两层，同时满足，**不是两个独立可相加的额度**：

| 对象 | 计费/硬边界 | 获取与释放 |
| --- | --- | --- |
| 所有活动会话协议缓冲 | 每会话保守预约16777216字节，总预约≤max_reserved_bytes，同时受max_connections限制 | accept后构造前取得；构造失败回滚；finished对象在回调后cleanup删除后释放，closing仍占全额 |
| 全进程SSE输出数组 | 每个活的StreamOutput数组固定262144字节；总容量≤stream_buffer.max_total_bytes，且包含在上述会话预约中 | beginStream分配前取得；内存销毁后释放；pending为0、暂停、HTTP完成但尚未排空均不退容量 |
| 每流pending | 头、chunk封装、正文、零chunk的当前线缆字节≤262144 | append前检查可用空间，consume只改逻辑长度不退数组容量 |
| parser片段/recv | 各16384字节；解析流body不得在HttpMessage.body累计 | 包含在会话预约，不再重复计入输出数组子预算 |
| 原请求/元数据/完整响应缓冲 | 原各字段/线缆/正文上限及16MiB同时存活保守capacity证明 | 保留S1上界，任何新增持久容器计入同一证明，禁止无界历史或按chunk建节点 |

“全进程预算”明确指本单Worker进程全部活动会话的受控用户态协议存储预约及其动态SSE容量子预算；不等于RSS、allocator元数据、线程栈、llhttp库对象或内核Socket内存逐字节计费。固定数组真实存储容量是262144，sizeof对象另含有界字段，计入会话元数据余量。旧std::string capacity证明限当前Linux/libstdc++；Builder必须更新同时存活容量表和实际capacity探针，仍≤16MiB；不能仅引用size上限。若无法成立则停止交Leader调整，不能默默扩大预约或遗漏容量。新动态存储须在分配前获取可覆盖其实际容量上界的凭证，或采用已计费固定存储；禁止先分配再检查。

容量子预算默认4MiB可承载默认16会话，允许管理员比会话总预约设置更紧的SSE上限。未获得262144字节时，在首个final字节发送前清理候选并返回503 `buffer_capacity`、关闭上游，不等待、不淘汰其他会话、不把它算协议错误；未选择SSE的回退不占此子预算。分配bad_alloc须回滚已取凭证，尽力500/否则关闭。任何失败回调不得留下先增后漏减计数。

推荐凭证与存储在一个有明确销毁顺序的owner内；先销毁数组再释放凭证。prepareError、finish、析构、HTTP完成后排空、强制停止共享幂等释放路径。预算owner寿命长于所有session；Runtime析构显式清空session后才销毁预算。独立Session测试也须提供有明确寿命的预算owner，不能偷偷绕过预算。结束计数不可下溢；release不抛异常。

快照至少给出全局预约current/peak、SSE allocated capacity current/peak、当前pending总量/peak、当前暂停会话数、pause/resume累计、预算拒绝次数及有界终结原因计数。当前量从唯一所有者派生或同步维护并测试不变量；不记录正文或无界每请求历史。检测数据用于验证而非外部稳定管理API。

## 4. 配置与水位状态（REQ-02）

新增可选顶层对象 `stream_buffer`，内部键：

| 键 | 默认 | 合法范围/规则 |
| --- | --- | --- |
| high_water_bytes | 196608 | 整数32768..229376（硬容量减32768） |
| low_water_bytes | 65536 | 整数0..high_water_bytes-1 |
| max_total_bytes | 4194304 | 整数262144..67108864，可非整倍数；不足一数组的尾余量不可用 |

新增 `timeouts.stream_idle` 默认10000ms，范围10..300000，沿现有timeouts键风格和严格未知/重复/类型检查。默认流downstream_write仍10000ms，response30000ms、total60000ms不变。配置部分省略先补默认再做组合校验（例如仅high设低于默认low即拒绝）。负数、浮点、bool、溢出、未知键、重复键、低≥高均启动失败，不静默截断。config/example.json更新并增加配置测试；CLI错误退出约定保持。

暂停状态与Phase独立。一次读最多16KiB，解析调用结束后复制有界片段并追加，**每次recv后**检查pending；达到或超过high立即暂停，不等整个64KiB事件批次结束。每次recv前也检查当前暂停/finished/期限，旧batch事件不能绕过暂停。高水位不是硬上限：允许本次有界片段及封装越过high，但始终≤256KiB。最多64KiB最终头和首片的启动合并也须证明落在硬容量内；无法证明则拆分有界追加而不能扩大硬限。high最大预留32KiB，覆盖16KiB片段、chunk封装与零块；任何append仍做硬检查，触硬限沿S1 stream_buffer_limit异常，不作为正常背压方式。

仅在真实send>0后pending降到≤low时恢复；新流pending已低则不先pause再resume。恢复不得立即递归调用readUpstream或循环拉取；只重注册IN，由下一EventLoop批次调度。每次读写保持现有最多64调用/64KiB的公平批量上限，其他会话和timer仍获得调度；不宣称严格公平调度或带宽均分。HTTP已经完成无需恢复上游，尾块/下游排空仍受写和total期限。

## 5. 暂停事件、EOF与租约（REQ-03）

当前EventLoop::updateChannel对已注册interest=0只执行MOD，不能屏蔽总会通知的ERR/HUP；因此新增ConnectionLease窄操作（如suspendEvents），经池验证generation后调用Channel::removeChannel，即DEL并失效旧token。暂停整个上游channel，无轮询timer；流头选择时上传已按S1停止，因此不保留上游OUT需求。恢复对有效同一租约重新setInterest(IN|RDHUP等原读标志)，创建新token；保留租约generation/所有权，不能伪造归池再借出。若注册失败，当前会话有界失败并归还所有资源。

暂停期间upstream数据/FIN/RST可能暂存在内核，**不承诺即时发现上游关闭**；直到低水恢复再观察，或由持续有效response/total/下游写期限收口。这样主动暂停不误判流空闲，也不因LT HUP忙转。暂停不影响下游观察/写事件和会话timer。恢复后先按原读取/解析规则处理可读字节和真实read=0/错误，不能仅凭RDHUP或HUP位宣告HTTP完成，也不能丢弃与FIN同批可读尾部；ERR按真实Socket错误分类。CL/chunked截断仍异常，EOF定界的正常read=0才允许HTTP完成。

旧token同批延迟事件被EventLoop屏蔽，入口仍检查finished/paused/lease有效性；回调内只移除注册、失效租约，实体按原回调后cleanup销毁。池的回调副本/退休对象策略保持。暂停中的租约仍占池容量，不返idle，不retry。首信号停止接入/新派发和idle，已有暂停流可在shutdown窗口内恢复排空；强制停止优先，不能因resume重新注册已终结channel。

## 6. 时间、取消和幂等终结（REQ-04）

所有时间使用SessionIo单调时钟，now>=deadline即到期。每次IO前、IO/parse返回后修改期限或HTTP完成状态之前，检查旧仍有效期限；有效进展不能抹掉刚跨过的超时。S1 response完成修复与原total同刻优先必须保持。先判断finished/强制终结，再判断旧有效deadline，才允许进展/完成/恢复；同刻多个期限固定分类顺序：total、downstream_write、response、stream_idle，其他原阶段期限保持。

| 期限 | 起点/刷新/暂停语义 |
| --- | --- |
| request/connect/upstream_write | 沿原阶段约定，早期SSE头停止上传后撤除上传期限 |
| response | 连接可用时起算的绝对上限；暂停不冻结；HTTP完成转换检查通过后才撤除 |
| total | accept起算，所有阶段/暂停/closing有效，永不刷新 |
| stream_idle | 验证SSE头并进入Streaming时开始；随后只有实际解码body>0刷新，不因头/chunk元数据/EAGAIN刷新；仅HTTP未完成、上游未暂停时计时 |
| downstream_write（仅SSE） | pending从空变非空时起算，只有send>0刷新；pending清空时撤除；新非空episode重新开始。EINTR/EAGAIN/就绪事件不刷新；HTTP完成后的尾部仍受此限 |
| shutdown/error/closing | 原固定窗口不延长，强制停止无成功尾块；closing≤1秒且受total约束 |

暂停stream_idle时先查期限，再保存剩余时长（或等价的暂停时长补偿）；恢复时先查response/total/write和强制停止，再恢复原剩余预算，不能每次resume获得完整idle窗口。如果本次有效body使pending越high，先在旧期限有效条件下刷新idle再冻结新余量；若无body只因header暂停，保留自进入流后的余量。HTTP完成后撤销idle但仍保留写/total。下游持续小额有效写可延长无进展期限，绝对response/total仍防无限流；不把这种改变称为延长整体请求寿命。

stream_idle到期：未commit可回504 `stream_idle_timeout`，已commit仅截断；response/total按原分类。下游写期限、RST/硬写错直接有界终结。错误输出仍遵循S1未send候选可撤回、首字节send后不能第二状态行/补正常零块的规则。增加类型化终结原因或现有有界分类扩展，避免用多个bool表示相互冲突的终态。

完整请求后的客户端SHUT_WR/read=0是正常读半关闭，仍应返回完整流；RST/SO_ERROR/不可恢复send错误才触发取消并关闭租约。不能因readEOF禁用所有下游OUT或错误停止流。取消证据分三级：网关timer/FD/预算已释放；模拟上游观察连接结束（可在其缓冲耗尽后才观察）；真实模型停止计算本阶段不验证、不宣称。客户端完全close与SHUT_WR在部分TCP观察上不可立即区分，写/total期限提供有界兜底，不声称瞬时准确识别所有close。

finish必须幂等：标finished、撤timer/注册、invalidate上游、销毁流存储后退容量、清暂停状态、关闭下游；重复timer/旧token/resume/finish无重新注册/重复计数。会话总预约在cleanup删除后释放。正常HTTP完成先关流上游，待输出排空后释放数组，再按原SHUT_WR/closing收口。事件外连续调用requestShutdown的既有内部SDK限制不扩展；验收实际signalfd/计时回调→cleanup路径和析构兜底，不能把事件外即时snapshot承诺补写成事实。

## 7. 实施顺序和风险

M1：配置校验、固定容量凭证和快照；证明申请/失败/释放及capacity界。M2：租约暂停/新token恢复、水位与真实慢读；保持有限事件批次。M3：流idle与write进展期限、取消/停止竞争及S1边界回归。M4：独立验证、来源变化记录、规范检查和Leader收口。

主要风险是暂停HUP忙转、旧token恢复、释放顺序、刷新期限掩盖过期及只计size不控capacity。选择固定数组+保守全会话预约，牺牲按pending精细回收内存，换取可验证真实容量；不选可增长缓冲/共享等待队列以避免新allocator和调度范围。整channel暂停牺牲即时上游断连观察，换取LT无忙转，由既有绝对deadline兜底。新增idle默认会更早结束实际无body的SSE（仅元数据或心跳语义仍按字节判定），属于本阶段明确慢流保护；有效SSE注释正文也是body并算进展，不识别event/token。没有重大新依赖/成本/范围冲突或接受债务。

## 8. 验收与证据（AC）

| 编号 | 必须满足的结果 | 对应审查 |
| --- | --- | --- |
| AC01 | 旧配置兼容、新值边界严格；所有会话预约和实际固定容量申请前受限，释放后归零，bad_alloc/注册失败不漏，实际capacity证明≤预约 | RV01 |
| AC02 | 真实受控慢读明确经历高水→暂停无recv→低水→恢复，最终解码全文相等且唯一正常尾块，硬容量始终≤256KiB | RV02 |
| AC03 | 暂停FIN/RST/HUP/ERR不忙转，恢复尾数据/EOF正确，旧token不串扰，无丢数据/重入/流归池 | RV03 |
| AC04 | 预算跨会话总额受限，空pending仍占容量、耗尽503无队列，释放后新请求可用，慢会话不阻塞快会话与timer | RV04 |
| AC05 | idle冻结余量/恢复、有效send刷新、所有边界前/等于/后及完成转换正确，已commit错误无第二状态行/成功尾块 | RV05 |
| AC06 | SHUT_WR正常、RST取消、暂停/完成/timeout/停止竞争恰好一次释放；活动/容量/注册/timer/租约最终归基线 | RV06 |
| AC07 | 三预设全回归、旧关闭窗口及S1期限反例通过，规范/来源/权威保护完整，独立证据不以自测替代 | RV07 |

路线：原生WSL `/bin/bash` login=false、仓库 `/home/power/projects/AI-Inference-L7-Gateway`；各角色 `build-local/<role>/v0.2-s2/{tmp,cache,evidence,debug,release,asan}`。脚本/构建前mkdir并显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。沿CMake presets，源码vendor无安装/网络。Socket/loopback及LSan是已知边界，精确测试首次窄升级，不试错重跑或禁检测。Leader规划不运行产品回归。具体矩阵/日志见审查计划；不得为通过慢读改大所有timeout、放宽预算或删除旧断言。
