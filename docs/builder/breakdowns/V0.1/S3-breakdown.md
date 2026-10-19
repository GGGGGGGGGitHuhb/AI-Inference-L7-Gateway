# V0.1/S3 Builder 实施拆解

依据 Approved S3-design/S3-review、Leader001；初次实现，S3返工0/2。原生WSL，分支codex/v0.1-s3-connection-reuse，S2基线3cb6524。无项目Builder指南，回退全局plan-project-docs Builder模板。仅修改设计§9范围，保留所有历史权威与来源清单。

| 子阶段 | 目标/模块 | 依赖 | 验证 | 状态 |
| --- | --- | --- | --- | --- |
| M1 | upstream池/唯一租约、配置、peek接缝 | Approved基线 | 容量、token/代次、异常/停止/退休上界 | 实现并自测完成 |
| M2 | ProxySession/Runtime安全归还/消息资格 | M1 | 完整首响应、慢下游、关闭握手、原测试 | 实现并自测完成 |
| M3 | 状态接缝/真实复用/停止测试 | M2 | 独立下游、污染/EOF、容量与故障 | 实现并自测完成 |
| M4 | 固定18cell成本脚本及全回归/文档 | M3 | 三预设CTest、格式化、来源hash | 实现并自测完成 |

临时/缓存/证据独立位于build-local/builder/s3；运行前显式设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME。本文件记录实现状态，不代表独立验收。

M1—M4初次实现与三预设/矩阵自测完成，原始ASan夹具失败已保留并修正；交接报告S3-report-001，待Reviewer独立验收及Leader收口。S3返工仍0/2，无Git发布。

2026-10-19 第1/2轮有限纠正：Reviewer001仅S3-F-001规范性Minor，GatewayConfig相邻函数间补一空行，相关Pool/Runtime 2/2和格式/增量构建通过，其他产品/测试/配置hash不变。详见Builder S3-report-002；当前累计1/2，待Reviewer复验，初次0/2为历史记录。
