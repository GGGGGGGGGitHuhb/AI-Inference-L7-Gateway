# V0.6/S1 Builder 实施拆解

依据 Approved S1-design、version-plan、S1-review。项目无专用 Builder GUIDE，使用全局 plan-project-docs Builder 参考；执行 agent-execution-route 原生 WSL 路线。只新增容量设施和 Builder 文档，不改产品、旧工具、L4 源码或 Leader 权威。

| 子阶段 | 目标/模块 | 依赖 | 验证 | 状态 |
|---|---|---|---|---|
| B1 | tests/capacity 有界后端、开环客户端、控制器、审计 | 已批准设计 | 逐 ID/时钟/正文/预算负控 | 完成，冻结工具 |
| B2 | E0 身份/Release构建/环境/空闲基线 | B1 | 两仓工作树哈希、相关CTest、采样开销 | 完成 |
| B3 | E1 B/G × A/S × 最多7档 | B2 | 最多28 cells，失真/连续失败停止 | 完成，27个E1 |
| B4 | E2 控制与清单冻结交接 | B3、Leader确认 | 最多8 cells；配置变化重校准 | 完成，7个E2；清单已冻结 |
| B5 | 正式矩阵和诊断 | Leader冻结manifest | 最多72+12 cells、独立复算 | 完成72/72正式与12诊断；Reviewer已收口，最终交接完成 |

实现采用 Python 标准库 asyncio，后端/客户端独立进程，紧凑流式记录和1MiB分片。控制器捕获轮转产品日志，不丢逐连接事件；采样包含捕获线程所在控制器与所有子进程。累计账本在启动cell前预留证据与活动时间，失败不重置额度；资源不足停止并保留终态与未来计划。逐请求绝对5秒，迟到50毫秒/无槽记not_sent；SLO从scheduled计算，计划窗口末尾的排空成功仍计入goodput。

角色输出根：build-local/builder/v0.6-s1，tmp/cache/evidence及两仓Release构建均位于此；显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX。不安装依赖、不改全局配置、不改其他PID。L4源只读dirty树，前后核对实际hash。单次run累计120cells/90分钟/2GiB，全部自有进程1GiB RSS/2048 FD；每cell45秒上限，清理TERM一次、5秒后KILL/wait。

2026-10-29：E0首次中断失败保留，修复后负控通过；9组无网络自测及21/21 Release回归通过。Builder累计44cells后，Leader冻结正式manifest 81877a406c767b66fb90422a79b805f53c3c77a13869219b4f967ee5116358f4 并授权72cell。工具py已封口，正式阶段不改工具/速率/配置，故障首停不重跑。

正式首停定位见Builder002：L4多词reason被旧正则漏解析；原始事件/字节完整，py未改，未重跑。

Approved返工001完成，11组自测/7项派生审计通过。Reviewer独立7项审计及门槛核对通过，Leader授权v2续采65个新ID；原failed状态与首错保留。

第二次首停仅r0共18项，返工002完成后15组自测/18项独立派生核对通过；v3续采余54，保持两原failed，禁止追加未知错误恢复。

第三次首停见Builder005：已定位generator-0 /proc/fd读取PermissionError且立即poll仍null，按规则fatal；33项及39项未来计划、来源/预算/全部PID回收已交接。当前没有三重复容量声明，未自行扩大恢复。

Approved返工003经Reviewer核对17组负控和固定33前缀后，v4续采39项完成；未重发前33项。累计118cell，425个自有PID均回收，最终源/二进制及冻结工具hash一致。当前以Builder006与formal-summary-builder-complete.json为准，前述第三次首停为历史状态；独立验收及S2入口判断仍由Reviewer/Leader负责。

最终交接：返工004按批准范围统一三类退出读取异常并增加Reviewer唯一前缀，v5封口；Builder与Reviewer各19/19工具自测通过，无新增Builder发压。Leader通知Reviewer83cell已收口、工具/诊断PASS、S2入口BLOCKED。参见Builder007；Builder原测量/额度仍引用006，历史过程与工具版本边界保留。
