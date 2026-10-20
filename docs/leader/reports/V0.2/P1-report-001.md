# V0.2/P1 Leader 规划报告001

2026-10-19；Leader (Zeus)。独立性能基线专项Approved、待实现，Ready for Builder，返工0/2。V0.2开发验收保持完成，S3不重开。

## 第一部分：PM 决策摘要

**结论与健康状态：On Track，可以实施性能基线专项。** 用户已同意先测V0.2再开发V0.3，并明确“可以，别忘了文档，做吧”；范围内基线按既有技术委托批准，无需重复例行审批。

**计划与实际：** 已形成有限模拟成本/并发/慢读资源和固定真实CPU模型TTFT/E2E/完成率矩阵、独立审查与用户结果报告安排。尚未测量，不预设性能收益；不修改或优化产品、不启动V0.3/V0.4。已有模型资产直接复用，没有新下载或费用。

**已核验成果：** 起点S3本地提交555b65d、工作区初始干净。源码核查确认旧成本工具样本/计时口径需补强，S3工具包含EOF等待和快照补位门，不能直接当成本发压器。新方案把HTTP完成与EOF/校验分开，用正式Release程序测成本，资源host另列。

**重要取舍与风险：** 每种组合3次重复，合计69个短cell和3个有界发压控制，每角色运行护栏40分钟，预计10–20分钟但不保证；真实模型共720正式请求。闭环与Python工具可能限制观察，结果如实保留失败、波动和工具瓶颈，不追求容量极限。重大未解决偏差、债务或待接受风险：None。

**PM决策：None。** 预设性能收益门槛不存在；吞吐低/延迟高也可成为有效结果，计时/正确性/样本不可信则必须处理，不能靠局限声明通过。重大范围变化另报，不要求PM逐项阅读底层矩阵。

**下一步：** Builder实现有限测量工具及结果文档，Reviewer独立重跑/复算，Leader收口。结果将有面向用户的场景比较表、限制与后续参考。专项结束协调者按既有授权本地提交、不推送，之后仍需用户启动下一阶段。

## 第二部分：详细工作记录

本部分供PM按需查阅。

### 权威、身份与执行路线

[设计](../../designs/V0.2/P1-design.md)SHA256 `b65bf637c62463d5a7863c3e1fc988b9d27122e284c9d0cea4978e818fb45a2f`；[审查计划](../../../reviewer/reviews/V0.2/P1-review.md)SHA256 `ab535bb2e4ee4aaf39675478ef507a38cdecb17a4a998d3f0a8a6d23d465d397`。批准依据用户明确专项执行与技术委托，P1自有0/2；S3已关闭2/2和所有历史权威保持。无新技术债。

当前分支codex/v0.2-performance-baseline，HEAD `555b65d66a52d95791dba5445178e57a69b81d2c`，初始clean；S3已本地提交，不假定远端/发布。使用agent-execution-route、plan-project-docs/Olympus；项目无Leader指南，回退全局Leader模板PM/两层报告。涉及C++的设计责任按已读personal-cpp-standards规范正反例；当前不要求新增C++或改产品。

原生WSL /bin/bash login=false，cwd /home/power/projects/AI-Inference-L7-Gateway；Leader build-local/leader/v0.2-p1/{tmp,cache,evidence}，Python前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。Builder/Reviewer各自目录、进程、数据，顺序运行避免争抢；模型固定资产只读共享，无新依赖。socket等已知边界精确首次窄升级。Leader本轮只读取代码/文档、写规划，不运行性能/回归、不派代理、不commit/push。

### 源码审计与选择理由

读tests/ProxyBaseline.py、support/PersistentBackend.py、integration/Support.py/RealRun.py/SyntheticRun.py/WireResponse.py，结合V0.1/S3原成本设计及V0.2/S3独立接受链：

- 旧ProxyBaseline以200样本统计并把失败耗时混入同一分位，receive结束包含连接关闭；PersistentBackend每请求同步记录、线程列表累计。适合其已完成历史范围，不直接宣称为新基线。
- S3 exchange序列化在start后、finally整理在end前，WireResponse.finish等EOF；这些并非错误，只不等于精确HTTP终态耗时。新P1客户端另取t_http并继续严格EOF/终态校验，旧工具不变。
- S3 SyntheticRun以100ms快照确认closing退休再补位，解决准入正确性但会节流成本负载。P1正式成本用Release产品和普通闭环，不借snapshot门抬高/压低完成率；64会话固定实验额度为closing留余量，配置和默认区别明示。
- Python客户端/模拟服务可能限制链路；选择独立进程、移出同步每请求日志、有限样本、单/双发压进程控制和机器采样，不引入新框架或寻找最高极限。出现瓶颈仅缩小可解释范围，不伪装网关容量。

### 矩阵、统计和证据

A非流1KiB三路径×三并发×三重复27cell，每500；B有节奏64KiB流两路径×三并发×三重复18cell，每100；C慢读4MiB混合资源6cell，每20；真实R1单并发流/非流12cell和R2并发2流6cell，每40。共69cell；A/B/C/R正式13500/1800/120/720，另3个直连发压控制各500。3重复与路径/并发顺序预先轮换，预热独立，真实单slot等待与prompt缓存不归因Gateway。

计量保留connect/send/首wire/首解码body/首非空content/HTTP终态/EOF/校验/关闭，TTFT是内容事件观察，不冒称token精确时刻。模拟同一确定正文严格校验；真实不同请求内容/ID不做伪字节配对。所有已开始attempt包括连接和并发晚到失败恰一次保存，未开始单列，不编造0耗时或丢失败分母。

成功分位与失败耗时分开；A P99探索性约5尾样本，B仅正式p50/p95、R p50/p90、C快慢median/max。三重复给median/observed min–max，不冒充置信区间或统计显著。聚合分位差不是单请求额外开销分位，闭环完成率不是最大容量。token/s只有可靠后端计数时提供，event/字符数不能代替token。

产品性能无收益门槛；接受门槛是固定矩阵完整、正确分类、计时/样本/统计/瓶颈控制可审计，独立复验与用户结果文档齐备。明显产品契约错误或工具缺陷不得用“基线可差”掩盖。Builder和Reviewer分别执行同矩阵，不要求测值相等；局限/负面结果完整保留。

可复现命令和结构化schema在设计§8，目标报告docs/performance/V0.2/P1-results.md；当前不创建假结果文件。Release完整CTest加新增离线负控为纯Python实现的必要回归；若新增C++测试设施须三预设验证，原S3长期不无故重跑或冒称复跑。六组AC/RV对应身份、执行、计时、统计、瓶颈和用户报告。

### 文档与交接

本轮新增P1设计/审查/Leader001，更新README/ROADMAP/ARCHITECTURE的专项入口与S3已提交事实；不改旧Approved/报告、产品/测试或CHANGELOG已验收结果。P1是版本完成后的独立测量，不改V0.2完成或V0.3未开始状态。

保护快照build-local/leader/v0.2-p1/evidence/planning-protected.json共143项，结束逐项一致；planning-doc-check.log检查权威hash、相对链接/围栏、git diff --check，planning-identity.log列六文件SHA。无未解决方案冲突，交协调者核对后Builder实施；当前没有性能结果或新提交。
