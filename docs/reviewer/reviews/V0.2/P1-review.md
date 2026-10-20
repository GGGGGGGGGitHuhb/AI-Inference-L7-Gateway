# V0.2/P1 性能基线独立审查计划

2026-10-19；`Approved`，专项待实现、0/2。Leader依据用户同意先测V0.2基线并明确“可以，别忘了文档，做吧”及技术委托批准；[设计](../../../leader/designs/V0.2/P1-design.md)是行为/负载权威，[Leader001](../../../leader/reports/V0.2/P1-report-001.md)是批准包。P1独立于已完成S3，不重开旧阶段。

## 1. 身份与路线

分支codex/v0.2-performance-baseline，起点555b65d66a52d95791dba5445178e57a69b81d2c。读取Builder报告/来源/测量工具与结果、Approved矩阵、S3最终接受及现有工具。无项目Reviewer指南则回退plan-project-docs全局模板，遵守agent-execution-route及涉及C++时personal-cpp-standards正反例。

原生WSL、bash login=false、仓库/home/power/projects/AI-Inference-L7-Gateway。Reviewer自己的build-local/reviewer/v0.2-p1/{tmp,cache,evidence,release}，脚本前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME；模型资产只读共享。等Builder全部停服后独立运行，不能共用可变后台。Socket/LSan已知边界首次精确窄升级；无下载/全局系统变更。完整矩阵每角色护栏2400秒；不要用阻塞睡眠妨碍进展沟通。

## 2. 审查矩阵

| RV/AC | 独立检查与结果要求 | 建议证据 |
| --- | --- | --- |
| RV01/AC01 | 产品src/旧S3工具/输入/Approved与起点相同；实际Release binary与asset SHA、CPU CLI/配置、模型真实加载、进程清理可追溯；新工具依赖只标准库 | identity.json、environment.json、processes.jsonl |
| RV02/AC02 | 独立执行固定69cell和3控制，预先schedule与实际顺序一致；A/B/C/R正式计数13500/1800/120/720，按每cell预热独立；连接accept/request差量证明PC/PR而非只信配置；后端slot1、真实C2不称网关队列 | cells.json、attempts.jsonl、backend-counts.json、schedule.json |
| RV03/AC03 | 检测HTTP完成与EOF分离、计时点顺序、TTFT非role-only/头/空content；首字节与首body区分；相同recv多event不伪造token时钟；校验所有确定正文与终态，异常attempt恰一次留存且清理 | detector.log、timing-control.jsonl、attempt-audit.json |
| RV04/AC04 | 从原始数据独立重算成功/失败/拒绝/not_started、nearest-rank、批次吞吐、重复median/min–max、资源单位和CPU差量；低样本尾分位与缺token计数正确null，禁止跨分布差值命名额外开销P99 | independent-summary.json、summary-diff.json |
| RV05/AC05 | 3发压控制/机器采样/worker周转间隙齐全；阈值触发如实限结论，不隐藏失败或选优；Release完整回归和新负控通过；新增C++如有则三套验证 | generator-controls.json、machine-samples.jsonl、release-test.log |
| RV06/AC06 | docs/performance/V0.2/P1-results.md区分Builder/Reviewer结果、模式/负载/重复、观察与推断、失败/局限/后续参考；根状态与历史、权限无冲突 | report-audit.log、protected-sha256.json |

## 3. 测量有效性重点

实际运行不能调用S3的100ms快照退休门作为成本补位。成本进程为正式Release gateway，C资源诊断host单列；直接与代理路径客户端新建连接策略、请求字节和校验相同。PR非流式预热池必须在测量前保留，warmup与正式计数差量不能混淆。流式即使配置idle也不宣称上游复用。

客户端不得逐请求同步日志/无界收集所有历史；每cell有限内存、结束/异常finally完整落盘，包括首失败后晚到worker。校验调度所花时间在闭环批次周转中如实计入，不能只算成功服务时间来抬高吞吐。线程创建/模型启动/预热/落盘不混入正式批次。后端1ms目标间隔与实际间隔区分，不用sleep参数假装精确服务时间。

新增计时适配必须在完整CL或zero chunk+空trailer确认时取t_http，再等待EOF/校验；原WireResponse.finish等待EOF的实现不能原样作为唯一end。独立用受控后端在HTTP终态后延迟200ms才关闭，验证t_eof−t_http反映该延迟、主E2E不吃进关闭延迟；另一例role-only立即、非空content延后100ms，TTFT必须对应后者。控制只核对时序与宽容差区间，不作纳秒精度承诺。计时中收到最终一片后JSON校验失败必须从成功分位剔除、仍保留耗时/partial。

失败率为attempted分母，not_started单列，不伪造0耗时；成功分位和失败耗时分别统计。输出requested/attempted/success/failed/not_started守恒。相同重复/worker的request ID唯一，不能丢并发后发异常。零成功统计为null。模拟正文hash必须来自固定预生成payload；不能只检查200或总长度。真实请求与支持字段一致，不为token计数增加stream_options。

## 4. 统计与瓶颈边界

独立汇总脚本不得导入Builder同一Summarize函数再宣称独立复算，使用小型独立计算并核验每cell样本。n=500的P99仍探索性；B只正式报p50/p95，R正式p50/p90，C快/慢median/max；缺失/失败样本导致n减少时重新标记尾分位依据，不能沿配置n充数。3重复的区间只是observed range，不是95%CI或显著性。

不能合并不同C/模式/重复来美化P99，不能选择三次最好一次。直接/代理统计差值和比率仅聚合观察，不对应单请求因果开销；并发闭环不是固定到达率，饱和曲线/最大容量/生产QPS不在范围。真实R2后端单slot可能排队，TTFT差不能全归因Gateway。

单进程/两进程×8/最后单进程控制共3个500样本，固定总并发16；核对CPU核数等价、周转间隙、实际在途和前后漂移。超过设计阈值需明确可能工具限制，不能机械认定GIL是唯一原因。性能不佳可以成为有效基线；无法保证输入/计时/样本或声明错误才阻塞验收。不要为了获得更好曲线擅自换框架/提高额度/无界加并发。

资源按gateway/backend/client分列，CPU100%为一逻辑核；RSS/FD采样峰不是真实极值，短cell可能只有边界样本须标明覆盖。C host快照包括实际pause/resume，若没有触高水如实写“该条件未触发”；不得将S2旧测试混作本cell测量。PR闲置连接和自然排空/主动停止清理要分别解释。

## 5. 独立执行、结果报告与门槛

Reviewer沿设计命令将builder路径换成reviewer，独立Release构建/完整CTest、--check、69cell+3控制及独立summary。不需要因为纯Python新工具重跑S3长期实验；若新增C++测试组件则对应三预设验证。保留所有原始run，失败/无效/被外部中断也单列，不能覆盖run-001。负控失败子进程非零和顶层预期通过分开记录。

最终报告不要求Reviewer和Builder数值相等；并列环境/时间/计量模式解释波动。用户可读报告至少有四部分：实验条件与范围、模拟成本/并发/慢读资源表、真实TTFT/E2E/完成率表、局限与对下一阶段参考。精简摘要不能隐去工具瓶颈/失败或说出数据不支持的收益。完整每cell数据与SHA可在附表/结构化结果中追溯，图片必须有轴单位、n、路径/并发/重复说明。

PASS要求完整固定矩阵/控制、独立正确性分类/统计、权限/清理/历史保护及用户报告齐备，无未接受发现。低吞吐/高延迟本身不导致FAIL；有失败但被完整准确分类的性能cell也可作为结果，不过明确产品契约故障或工具错误必须解决/按授权处理，不能以“这是基线”绕过。矩阵未完整或计量不可证则BLOCKED/FAIL，不以样本不足的部分表关闭专项；无授权不接受债。只有未接受Minor也不能PASS。新P1最多两轮，不重开S3计数。Reviewer不commit/push；最终交Leader收口与协调者本地提交，不进入V0.3/V0.4。
