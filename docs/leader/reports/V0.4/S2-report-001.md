# V0.4/S2 Leader 启动报告001

2026-10-21，Approved / 待实现，On Track；S2累计返工0/2。

## 第一部分：PM 决策摘要

**当前结论：On Track，可以进入实现。** 本阶段只研究一项改进：利用已有配置缩短过载时的排队等待，比较500ms实验基线与100ms候选。S1发现“更多请求最终成功，但达标请求反而更少”；现在检验缩短等待是否改善这一现象，不预设收益，不称100ms最优。

**计划与实际：** 已完成源码/前阶段证据核查和明确设计；尚未实现、测试或测量。交付三份可运行配置、一套有限对照实验、独立验收与结果说明。固定低负载5req/s和过载60req/s，三配置含无队列参照、三重复及发压控制，共21cell、2970个含预热ID；两个角色分别独立一次。无需下载模型或新增依赖。

**重大偏差与风险：** None（无新增产品范围或成本）。测量仍可能受发压能力影响；缩短等待可能增加504，故所有拒绝/超时留在分母，必须验证低负载与长短请求边界。保持产品默认1000ms和产品实现不变；500ms是S1实验值。即使结果无收益，只要验证有效也可完成，保留默认并明确不推荐替换基线，不继续调参直到“成功”。

**PM决策：None。** 用户已明确“开始s2工作”，持续委托“你来决策吧”；ROADMAP允许Leader在该范围内采纳阶段基线。本推荐落在现有请求等待成本方向，不引入新的对外协议、费用、依赖或发布边界。Leader据此批准下述精确基线，无需重复确认。独立验收通过后文档收口并本地提交、不推送；不启动V0.5。

**下一步：** Builder按冻结基线实现隔离实验与配置，自测后交Reviewer独立验收；Leader根据真实结果给出限定建议并收口。完成条件是有效比较、全部正确性/资源保障、独立PASS与文档同步，不是必须提升某个百分比。

## 第二部分：详细工作记录

供PM按需查阅。

### 输入、路线与授权

读取用户提供的跨项目AGENTS规则，当前仓库及其父路径未发现附加AGENTS；无项目Leader指南，使用plan-project-docs/references/role-guides/leader-guide-template.md回退，已读PM关系与双层报告契约。读取agent-execution-route、plan-project-docs及阶段设计/审查/根文档参考、personal-cpp-standards及规范正反例；本阶段未修改C++。TECH-DEBT-TRACKER.md不存在，无当前需接受债项，不制造空表。

当前分支`codex/v0.4-s2-evidence-driven-improvement`，HEAD `752987a0564e8a99c0833c7f2af7e65ad561e491`，进入时clean；S1已提交，远端本轮未核验。原生WSL bash login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`。Leader工作目录`build-local/leader/v0.4-s2/{tmp,cache,evidence}`，脚本显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；Builder、Reviewer各自同结构。loopback/LSan为已知窄权限边界；不装软件、调系统或下载资产。当前仅读取/文档/轻量校验，没有构建或benchmark。

输入为ROADMAP/ARCHITECTURE、S1最新Builder002、Reviewer002、Leader006及完整结果；原S1已关闭，4/4历史不重置。当前S2单独0/2，失败后按S2返工记录处理。没有派生第二技术方向。

### 选择依据与冻结权威

`tests/experiments/Plan.py`把Q固定queue timeout500ms；`Statistics.py`的Q SLO却是scheduled起算TTFT250ms/E2E500ms。S1独立Q队列8−0达标goodput三点−17/−13/−16.5req/s；这些观察支持“等待成本”假设，不能直接证明优化有效。产品`GatewayConfig.cpp`已支持10–300000ms，`ProxySession::nextDeadline/checkDeadline`与队列owner已实现期限及504清理，无需新状态机。

采用已有Cell/Host/Budget/Association而新增隔离runner，避免更改S1冻结计划。新计划只Q与T，无真实模型、NODELAY、路由策略、多Worker或协议变更。100ms为事先固定候选，5req/s预选低负载仍需用结果核验，无效则BLOCKED；不能临时降rate。新工具/静态完整配置由Builder交付，当前只定义CLI并未声称已可用。

| 基线 | SHA256 |
| --- | --- |
| [S2设计](../../designs/V0.4/S2-design.md) | `e26173c6cc5862d37f95cff96162be814a23018829eaa4cfe2cce50ae9bd0410` |
| [S2审查计划](../../../reviewer/reviews/V0.4/S2-review.md) | `20d0e143bdf7b2e6f8d34bcefa203d8a7880d269873b4c2cd2d45aa7d7207692` |

候选推荐门槛和阶段PASS分离：需要两角色独立有效比较，有限候选推荐另需预注册的过载收益、低负载/长短类不退化与工具控制均成立；否则如实记录负面或受限结果、保留默认。全部终态及分母保留，不只看成功请求尾延迟，queue_timeout不得已经派发。静态配置不等于真实推理建议。

### 修改、检查与交接

新设计/审查及本报告，根README/ROADMAP/ARCHITECTURE仅当前阶段入口和批准边界同步；将ROADMAP S1遗留“恢复诊断优先返工中”标为被最终验收取代的历史快照，而非覆盖旧角色报告。修正根当前分支与S1已提交事实，未改全局路线范围。CHANGELOG待实际交付/验收再记。

`build-local/leader/v0.4-s2/evidence/planning-protected.json`冻结HEAD全部既有src/tests/docs及CMake身份，供交接检查。轻量校验为git diff --check、本地链接/围栏、保护hash及新权威hash；不存在的新CLI/产物只在设计中列为要求，不当作已存在文件链接。未测性能、未代Builder实现或代Reviewer接受。

Builder下一步按设计M1–M2和AC01–05交付；Reviewer按RV01–05独立验证。完成后Leader新报告收口，协调者精确暂存并本地提交、不推送，继续保留S1及更早历史。遇到范围冲突、关键证据缺口或有限返工耗尽时报告实际原因，不擅自扩大实验或降低标准。
