# V0.4/S1 实施拆解

Approved设计/审查/Leader001及rework001/Leader002授权，统一返工1/2。原生WSL/bash login=false，独立build-local/builder/v0.4-s1路径及显式tmp/cache；无项目Builder指南，沿plan-project-docs模板回退。保留Leader根文档规划和所有旧源/工具/报告。

| 阶段 | 范围/模块 | 依赖 | 验证 | 状态 |
| --- | --- | --- | --- | --- |
| B1 | Plan/Statistics/Budget固定57cell/7590ID、1GiB预算、互斥终态/时钟/SLO | Approved | 离线守恒及五类真实预算负控 | 完成 |
| B2 | Client/Worker/Backend/Infrastructure/RuntimeHost增量校验、有界IPC/只读观测 | B1 | 错协议/迟到/异常/清理/背压短控 | 完成 |
| B3 | CMake、三预设完整回归和规范冻结 | B2 | 各21/21；clang-format实际执行与人工检查；最终相关各1/1 | 完成 |
| B4 | RunExperiments/Analyze完整矩阵、独立复算、结果/身份 | B3 | run-001工具失败保留；Approved后置关联返工/130条离线/真实端口复用及17项拒绝控制；run-002完整57cell通过 | Builder完成，待Reviewer |

T机器漂移/发压敏感及CPU相关标记触发，结果只作受限描述性基线，因果收益/容量未证实。H20/H60/Q有效配对均3/3。239子进程回收；详细命令、失败与结果、SHA见Builder001和docs/performance/V0.4/S1-results.md。不提交、不推送，由协调者与Reviewer后续收口。

## 后续有限返工状态（2026-10-20）

当前累计4/4：Reviewer001旧Backpressure失败触发2/2；新增Runtime校验失败后用户授权3/3，资源断言失败后再授权4/4诊断优先。历史额度/Stop不改写。A一次分项诊断已证实活finished对象预约仍16MiB、流资源零、析构后全零；协调者确认B，两层生命周期断言已完成，产品/发压不变。三套定向各2/2通过，完整回归与最终交接以Builder002为准；独立Reviewer接受前阶段仍未关闭。无自动第五轮。
