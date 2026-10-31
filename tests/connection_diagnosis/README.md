# S2-trace：有界直接连接取证

> 2026-10-31追加：用户允许的一次停止通知修复已实施，但验证入口参数冲突导致新测试未启动，已停止且不重跑；修复有效性未确认，见[修复记录](../../docs/leader/reports/V0.6/S2-trace-report-004.md)。

> 原冻结首轮未通过整轮验收：冻结首轮在第三项控制的reset-peer退出码-15处停止，15项性能全部未开始。`close_all`与`Owned.close`存在重复TERM通知路径，具体致命时序未取证。保留当前冻结工具用于审计，不重跑原清单或视为可用性能工具；修复与后续采集须单独记录，见[结果](../../docs/performance/V0.6/S2-trace-results.md)。

依据Approved S2-trace-design/review。此目录为新诊断工具，冻结capacity/capacity_diagnosis及旧证据不改。默认产品编译不含观察点；Gateway `GATEWAY_CONNECTION_TRACE=ON`、隔离L4 `L4LB_CONNECTION_TRACE=ON`才编译设施，且只有设置自有绝对/相对输出目录`CONNECTION_TRACE_DIR`才开启。U为未编译设施，O为编译但变量未设置，T为相同诊断二进制开启；三者使用完全相同Client/Backend端点适配器、请求与日志。

## 固定schema与内存

小端Linux ABI固定：Header256B，Record256B，C++static_assert/Python struct双检查；magic=0x314543415254374c，version1。每进程预分配131071条记录加Header恰32MiB，不扩容、不循环覆盖。单L4高档3840×(3+20)=88320业务accept，占21.5625MiB，尚可记录42751个健康/其他连接；单Gateway也按全88320算而非假定均分。满则drop计数，解析拒绝完整归因。所有记录在单reactor线程写；L4 health在同线程maintenance与backendSelector同步调用，不加锁。

Header为32个uint64：magic/version/recordBytes/capacity/count/dropped/accepts/duplicates/queries/queryFailures/active/closing/finished/pid/identityNs/exportBeginNs/exportEndNs，剩15项保留。process身份为(pid,identityNs)，另由cell目录及控制器processes.json绑定，不用FD关联。

Record：generation、productSession各uint64；12个uint64时间槽；4个Endpoint（uint32 IPv4主机数值、uint16端口、uint16保留）；sent[2] uint64；reservedBytes uint64；9个uint32（active/closing/finished/kind/outcome/reason/firstSide/error/flags）；32字节NUL结尾原因；20字节保留。generation独立于产品SessionID，拒绝不推进产品ID。Endpoint依次为入站local/peer、出站local/peer。flags低4bit标识端点实际取得或选定，bit8发布、bit9移除、bit10原因截断（截断不通过审计）。零端点/缺flag明确unknown。

时间槽0..9为accept/request-identified/upstream-connect-start/connected/request-sent/output-complete/closing/finished/removed/first-error-or-EOF-observation，10..11保留。观察用真实steady_clock纳秒，与本机Python monotonic_ns均Linux CLOCK_MONOTONIC域；不使用测试FakeSessionIo时刻跨进程匹配。未观察到的阶段为0，不把0当作实际发生。Gateway正常removed在map erase完成后，停止残留在原sessions.clear后补记录；不改变产品清理顺序。finish与remove分别计数，拒绝快照只读O(1)计数，不扫描sessions。

kind=1 Gateway accept，2 L4业务accept，3 L4显式健康出站连接。outcome=1 published、2连接额度、3预约失败、4构造失败、5其他；0 pending不能通过审计。Gateway reason为原FinishReason枚举，reasonText保留原outcomeCode；L4 reason保存关闭传入errno，firstSide=1入站/2上游/0未知，仅表示首次观察侧，不表示主动发起关闭侧。SO_ERROR只复用原读取结果，不再读取清除。L4 EINPROGRESS出站local用getsockname，remote使用已选定backend，getpeername失败保留queryFailure且字段有效性明确。

## 关联和失败边界

Client适配器沿用原负载/时钟/完整正文/终态，另写每计划ID的scheduled/dispatch/connect/closed与关闭前缓存的local/peer。Backend只在完整请求ID解析后写对端元数据，不能声称无完整ID就无包字节。两适配器对U/O/T一致开启。关联只用完整四元组及相交生命周期，process代数与cell边界保留；同tuple多候选、缺失、端口复用重叠均unknown，不按FD/序号/时间接近猜测。只有显式kind3健康记录能分类探针，短连接或无HTTP ID不能单独认定探针。

原始TCP请求失败仍留在全计划分母。T关联记录输出采用≤256B紧凑索引行，细节可从唯一process+generation回原始binary；每项未知ID显式保留。drop、重复接入分类、缺终态、PID不符、缺客户端端点行均工具错误首停。

## 导出与预算

热路径固定字段/O(1)计数，无格式化、文件写、动态扩容或等待。仅停止且有界排空后导出≤1MiB分片，进程内独立SIGALRM十秒硬限可中断阻塞write；控制器从TRACE_EXPORT_BEGIN记录复核十秒及整个cell60秒，异常非零退出/缺header都失败。导出头最后写，header时间和drop可核验，不静默恢复。

每性能cell最坏：88320×(512客户端+192后端+256 L4原日志+256客户端端点+192后端端点+256关联) + 三进程32MiB + 固定余量，≤256MiB；负控≤64合成请求/16MiB，另128MiB全轮清单/收口。15×256+3×16+128=4016MiB≤4GiB，最多18cell/1200秒、分片1MiB、采样RSS1GiB/FD2048/单child AS128MiB；失败不重置或补跑。

本轮L4版本化补丁相对本机实际dirty源码，不含外部dirty diff。附加测试副本例外见Approved S2-trace-rework-001：仅五个真实connect→accept之间等待监听可读≤1s，原断言/产品循环不变，刻意accept错误注入不等待。原始失败/debug在本机证据保留，debug不进入补丁。

返工002只修隔离测试前提：metrics 首条真实后端在原7/11字节断言前等POLLOUT≤1秒并验SO_ERROR=0；deadline/forced 用固定块持续有界补两方向，正send撤销旧blocked，必须两份相同有效periodic且两向未转发差额正、当前EAGAIN；接受前再次校验16秒/每方向16MiB。原all(pending)、二次信号、deadline与回收断言保留。源耗尽平台的纯谓词负控见FixtureTest，`TRACE_L4_SOURCE`可指向各自副本。

## 冻结与执行

准备阶段只运行 `SelfTest.py`、`MatrixTest.py`、`FixtureTest.py`，均不启动负载或网络。`Prepare.py --role builder --root build-local/builder/v0.6-s2-trace --source-snapshot <本角色实际源快照> --manifest <新的候选JSON>` 仅生成Draft；含U/trace二进制及CMakeCache、全部新Python/冻结capacity依赖hash、源码、固定CPU亲和性、18项顺序和预算。Leader/Reviewer核对后才能把候选标记Frozen并固定SHA；Draft不能运行。

`Matrix.py --manifest <冻结JSON> --sha256 <SHA> --verify-only`仅校验；去掉`--verify-only`才执行。CLI不能覆盖速率、槽数、预算、CPU或二进制。全轮仅新空目录，原始错误首停、无resume、不补跑。每cell唯一checkpoint，最终summary一次写；attempted/verified/not_started分别列出，失败已执行cell不算未执行。

三负控顺序是连接上限（cap1、预约16MiB、第一条部分HTTP占位，第二条完整合成请求必须tuple关联outcome2）、预约不足（cap2、预约16MiB，同形请求必须outcome3）、L4对端reset（显式kind3健康出站隔离；后端收到唯一完整合成ID后SO_LINGER零触发RST，tuple及首次观察上游errno104须一致）。各只有2/2/1条客户端连接，均≤64，不计入性能曲线。三负控均受同一18cell/60秒/16MiB账本；这些功能cell仍须冻结后授权才运行。

低档按repeat轮转UOT/OTU/TUO，Reviewer反序；低档9项全部完成后按预定门槛判定，失败则保留6项未开始。高档UT/TU/UT（Reviewer反序）固定6项。CPU成本为正式窗口所有七角色（含控制器）采样ticks差/HZ/计划请求；逐角色采样窗口须≥19秒，分母不剔失败。成功HTTP P95/P99样本不足不能算通过。good绝对百分点、CPU与延迟比值按每repeat全配对，无平均掩盖个别失败。

整轮monotonic入口覆盖预检、每cell及汇总；每次启动前保留完整60秒，收口必须≤1200秒。4GiB预算先预留全矩阵4016MiB，加已存在准备证据不得超限；磁盘同时保留双角色8GiB。性能各最多256MiB，固定字节上界88320×1664+3×33554432=247627776，尚有20807680字节容纳writer固定头、资源、日志非请求行、config/spec/result；客户端分片按worker实际请求数而非每worker全count。原始片≤1MiB，root摘要≤1MiB，资源采样/异常均使用既有有界writer。测量停止后同一绝对60秒清理期限共享给全部child；通知异常不跳后续reap，导出从进程标记起独立10秒。超过期限即失败，不能靠清理延长宣称通过。
