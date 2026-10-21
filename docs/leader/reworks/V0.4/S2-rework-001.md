# V0.4/S2 返工001：控制后端HTTP头与失败取证

**Approved**，2026-10-21，Leader在用户阶段启动/技术委托及既有有限返工范围内采纳。累计S2 **1/2**，S1历史不变。依据[原设计](../../designs/V0.4/S2-design.md)、[审查计划](../../../reviewer/reviews/V0.4/S2-review.md)、[Builder001](../../../builder/reports/V0.4/S2-report-001.md)（SHA256 `bd90d6135e6eca9ced74990acedd6280067bd4d40b7e754e6a2f2ba622f98658`）；决策见[Leader002](../../reports/V0.4/S2-report-002.md)。无更早S2返工。

## 触发与界限

`build-local/builder/v0.4-s2/evidence/controls-001.log`记录占位gate超时；real-timeout/transitions.jsonl显示两个会话已dispatch随后约1ms内upstream_error。新DetectorTests用大小写敏感bytes dict查找`X-Experiment-Id`，不兼容产品正常转发的小写`x-experiment-id`。静态不兼容与观测一致，但首次线程异常字符串未持久化，**不能声称首次日志捕获了KeyError**。四Host均已回收，236保护文件未变，正式矩阵尚未启动。

本返工是本流程要求的失败路径统一纠正权威，**不改变原设计任何REQ/AC或审查门槛**。只细化REQ03/04/06、AC02/03/05的控制后端和失败留存实现；21cell、2970ID、5/60rate、100/500ms、全部SLO/分母/推荐条件不变。禁止改产品、旧测试、S1工具/历史或扩大工作负载。

## Builder修正与验证

- RW01：仅修改新增`tests/queue_budget/DetectorTests.py`的控制后端头解析，使字段名按HTTP语义大小写无关；Content-Length和实验ID均一致处理，保留原请求内容、占位与结束时序。增加小写和混合大小写的有限控制，真实代理路径仍必须执行。
- RW02：控制失败及正常退出均在finally有界持久化后端接收记录/异常、客户端结果、已到达gate阶段与可用host状态；保留原异常传播，不能用空记录或清理成功冒充占位证据。先回收线程/连接再保存稳定快照；仍在原预算内，取证写入失败不能掩盖原始失败。
- RW03：保留controls-001及原报告，使用新controls-002运行一次完整控制。必须仍证明两真实占位→第三入队→504 queue_timeout且未派发→释放占位→drain全零，不延长或放宽gate掩盖失败。控制通过后继续原M2三套完整CTest各一次和唯一正式run-001；本轮不额外跑S1矩阵。若再失败保存证据交Leader，不自行追加修复。

除该Python文件外的实现源保持本次失败快照；允许更新新增README/实施拆解并写新Builder002反映实际结果，不覆盖Builder001。无接口、默认配置、数据迁移、外部依赖或隐私边界变化。

## Reviewer与关闭

RW01→RV02/03：独立检查大小写控制及真实代理100ms超时，不能只依赖纯函数反例。RW02→RV03：检查失败取证与异常传播、线程/PID回收和原失败保留。RW03→RV01/05：核对保护hash、原门槛及三套/完整正式矩阵证据；独立执行原计划，不能提前宣布PASS。Builder新报告记录精确差异和命令，Reviewer使用下一未占用S2编号；原AC01–05全部满足且独立接受后才收口。
