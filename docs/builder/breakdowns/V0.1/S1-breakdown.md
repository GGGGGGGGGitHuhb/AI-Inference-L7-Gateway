# V0.1/S1 实施拆解

依据 Approved S1-design.md 与 S1-review.md；初次实现，返工累计 0。

| 子阶段 | 范围 | 依赖 | 验证 | 状态 |
| --- | --- | --- | --- | --- |
| B1 | 固定依赖、构建、组件迁入与来源记录 | Approved 基线 | hash、组件契约、离线构建 | 已实现并自测 |
| B2 | HTTP、JSON、规范化 | B1 | 支持矩阵、分片、容量、异常 | 已实现并自测 |
| B3 | 模拟后端与联动 | B2 | 五种场景、进程回收 | 已实现并自测 |
| B4 | Debug/Release/sanitizer 与交接 | B1—B3 | 完整 CTest、格式化、报告 | 已实现并自测 |

不修改原 Server/L4LB，不实现 S2 代理，不提交或推送。

2026-10-18：初次实现完成，三套 CTest 各 5/5；等待独立 Reviewer，非阶段验收。详见 S1-report-001.md。

## 返工 001（累计 1/2）

依据 Approved rework-001：RW-01 状态范围、RW-02 chunk 大小行前置语法、RW-03 原始计量和异常回归均已实现；RW-04 证据收集完成，Builder report002 已交付，等待独立 Reviewer 复验。原初次实现记录保留，不重置返工计数。
