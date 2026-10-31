# V0.6/S2 前置诊断 Leader 001：启动与证据边界

## 第一部分：PM 决策摘要

2026-10-31，On Track。用户在明确下一步先做归因、再进入S2产品优化后授权“做吧”。本轮已形成有限四条件对照计划，先Builder、后Reviewer独立反序执行；不修改产品代码，不重跑S1整矩阵，完成后提交推送。

已只读复核S1双方24个JSON对照cell。L4高档六次正式窗口的传输失败请求均未出现在模拟后端收件中，连接后关闭中位时间约5ms；这支持优先排查后端之前的链路，但不证明Gateway连接限额或某个L4代码路径是唯一根因。历史数据、工具和源代码均保持。

计划将增加后端进程和分开CPU亲和性作为对照，区分工具/调度敏感性；各角色最多12cell/540秒活动/1.5GiB证据，错误首停。主要限制是同机WSL没有专属CPU，增加后端不是同资源优化，绑定CPU也不能隔离宿主争用。S2入口目前仍BLOCKED。PM额外决策：None；现有授权覆盖本轮诊断。

## 第二部分：详细工作记录

起点c51af0e0d410cafab1b7e73f17bb90c01481f23c，新分支codex/v0.6-s2-preflight。依据[前置设计](../../designs/V0.6/S2-preflight-design.md)及[审查计划](../../../reviewer/reviews/V0.6/S2-preflight-review.md)。沿用原生WSL路径/home/power/projects/AI-Inference-L7-Gateway，各角色build-local/ROLE/v0.6-s2-preflight/{tmp,cache,evidence}；网络仅本机回环与授权Git推送，无依赖安装。TECH-DEBT-TRACKER和本仓AGENTS/GUIDE不存在，使用已读取的全局角色模板；L4外部源只读。

阶段设计由用户已批准的诊断目标细化。采集前按Reviewer建议明确：L2/LP分别与同角色同repeat的L1配对，两角色六配对每对改善≥5个百分点才称稳定正向敏感性。该澄清在任何新压力采集之前完成，不改S1数值口径。固定条件及预算由新包装器冻结并核验；先交Builder实现、自测与样本，再交Reviewer核验和独立样本，Leader不代替最终独立审查。

新增History.py为只读历史取证，流式拼接跨分片L4行，保留多词关闭理由和errno，按HTTP ID对客户端终态与后端收件做集合比较；不会将无HTTP ID的L4日志硬关联到某请求。HistoryTest六项合成检查通过，覆盖跨片、多词、重复、缺关闭、截断、外来收件和历史零字节EOF显式归类。24cell摘要见[S2-preflight-history.json](../../../performance/V0.6/S2-preflight-history.json)，内含逐文件SHA、正式/预热分别计数与逐秒终态。L4理由统计覆盖所有阶段，不能冒称正式窗口逐请求归因。

历史正式失败中位连接寿命为Builder4.884/4.688/4.946ms、Reviewer5.152/5.002/5.254ms。源码GatewayRuntime.cpp接受连接后若sessions_.size达到maxConnections会直接析构socket；这是与表现相符的候选，当前缺直接拒绝计数。L4全阶段常见shutdown SHUT_WR errno107与SO_ERROR errno104/32，错误可由对端关闭传导，不能仅由日志确定故障起点。新对照结果待采集，未提前声称优化或诊断成功。

采集前核对：候选manifest-001未运行，静态审查发现Common.write以xb写同名summary导致第二cell必失败，已改为逐项唯一checkpoint与末次summary，并补两cell连续执行检查；同时补全流程540秒门禁、正式窗各角色affinity覆盖、controller/monitor/capture线程取证及320KiB/cell元数据预留。Builder与Reviewer无负载自测各11/11后冻结Builder002，SHA256 `33b12566ea1c4cc467c2a3f4a74b372e63fe445779f234b45470ccd18bace3a9`；Reviewer反序001为 `aea4ef005f78e35d0e740125b3f67ef324ac22c88bb171e40b8da7117e317ae9`。全矩阵最坏1,042,169,856B，另留16MiB收口。未消耗或重跑压力样本。
