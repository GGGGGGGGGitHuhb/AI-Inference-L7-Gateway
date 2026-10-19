# V0.1/S2 实施拆解

依据 Approved S2-design / S2-review，初次实现，返工 0/2。S1 历史不变。

| 子阶段 | 范围 | 依赖 | 验证 | 状态 |
| --- | --- | --- | --- | --- |
| B1 | 固定事件组件、配置和规范化策略 | S1 | 来源、事件token、配置边界 | Builder 实现/自测完成 |
| B2 | 会话、运行时、main、信号、限额和deadline | B1 | 可控IO/时钟、计数回归 | Builder 实现/自测完成 |
| B3 | 真实Client→Gateway→Mock | B2 | 协议、短IO、半关闭、坏请求、限额、停止 | Builder 实现/自测完成 |
| B4 | 三构建全回归与交接 | B1—3 | CTest、sanitizer、format、来源与内存核算 | Builder 实现/自测完成 |

交接证据见 [Builder S2-report-001](../../reports/V0.1/S2-report-001.md)。所有子阶段均待 Reviewer 独立审查；未提交、未发布。

## 第1轮统一返工（1/2）

依据 Approved rework-002，RW-01/02：显式closing、一次SHUT_WR、固定正常/错误截止；RW-03：全额占槽至cleanup与停止优先级；RW-04：S2函数边界/职责分组、真实格式化与人工复核。Builder修正和自测完成，待独立复验，见 [S2-report-002](../../reports/V0.1/S2-report-002.md)。此前初次实现/失败记录保留。
