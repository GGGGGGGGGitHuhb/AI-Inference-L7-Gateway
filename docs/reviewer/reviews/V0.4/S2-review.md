# V0.4/S2 独立审查计划

**Approved**，2026-10-21，按用户阶段启动及技术委托由Leader采纳；[设计](../../../leader/designs/V0.4/S2-design.md)为行为/范围/验收权威，[Leader001](../../../leader/reports/V0.4/S2-report-001.md)为决策包。本计划仅细化验证。S2返工0/2。

## 输入与执行

读取用户AGENTS、agent-execution-route、plan-project-docs Reviewer模板；无项目角色指南，明确回退。读取S2设计、全部后续S2返工和最新Builder报告，以及S1结果/Reviewer002的限制。不得替Builder修改实现。自有`build-local/reviewer/v0.4-s2`的tmp/cache/evidence和三套build，显式环境变量，原生WSL bash login=false；网络socket/LSan已知窄权限，不禁用检测。Builder测量终止后独立开始，资产无需模型或网络。

执行设计列明的三预设全量CTest各一次；新DetectorTests和完整RunQueueBudget各一次（将路径builder换reviewer）。记录实际版本/命令/退出码/时间/源与产物hash；不复用Builder样本、不补样本、不跑S1大矩阵。不要求新CTest总数变更。

## 审查矩阵

| 项目 | 对应 | 检查、风险与PASS证据 |
| --- | --- | --- |
| RV01 | AC01 | 检查相对752987a diff及保护hash：src、旧tests、CMake和S1权威/报告不变。三配置通过实际Host加载；除端口映射外与实测模板一致；B/C只有queue_timeout_ms差异，Z只count差异；没有新默认/依赖/算法 |
| RV02 | AC02 | 自写独立复算不调用项目summarize/analyze，21cell/2970计划ID闭合，2760正式与210预热分离；scheduled双SLO、固定窗口、终态互斥、原始时钟顺序、分位最小n、长/短类分母和后台实际请求集合一致；运行设计全部新负控 |
| RV03 | AC03 | 真实100ms超时控制证明504、入队未派发、后端无该ID，排空全零；正式run逐ID核对超时/派发、唯一4tuple顺序关联及等待来源；预算/进程退出负控保留失败与未开始ID。核对原始峰、drain、FD、RSS、PID回收、实际采样间隔、运行期预算记录 |
| RV04 | AC04 | 按固定rate/config/repeat三元组检查≥2/3有效，5req/s B/C有效重复无queue_full/queue_timeout；否则BLOCKED。独立复算C−B每对及比率中位，含长/短类与零基线规则；T敏感/漂移/CPU限制不隐去。负收益合法、协议/资源失败不合法；不得以有效arrival消除T限制 |
| RV05 | AC05 | 自有三套全量21/21、新负控及一次21cell证据与身份完整；报告区分计划/观察/未知；候选不可先称优化成功或真实推理收益，文档CLI可用；旧数据/失败/权威不覆盖 |

真实超时控制应有可判定的后端占位/排队时点；不能仅sleep后检查504。反证超时被dispatch必须由detector拒绝，不能宽松统计把其当正常派发。独立Reviewer至少追加一条不调用Builder判定器的分母或SLO反例与一条候选推荐门槛反例。

## 结论与交接

PASS：AC01–05全部验证，接受有效正/零/负实验结论，不以性能提升为阶段门槛。BLOCKED：环境、有效到达/不过载对照或关键证据不足。FAIL：功能/资源/隔离/分母/历史保护/重大声明等缺陷需要返工。PASS WITH DEBT仅限非核心问题且已明确接受；不得把缺失关键实验当债务自行接受。

写新`docs/reviewer/reports/V0.4/S2-report-001.md`，后续编号递增；记录各RV、原始路径/身份/命令、所有发现严重度及最终结论。独立PASS后交Leader关闭，协调者本地提交不推送；Reviewer不宣布代码已提交、不启动下阶段。
