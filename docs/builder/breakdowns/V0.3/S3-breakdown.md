# V0.3/S3 实施拆解

Approved S3设计/审查/Leader001叠加rework001和Leader002，当前累计返工1/2；本轮为Builder初次实现，不重置计数。原生WSL /bin/bash login=false，独立build-local/builder/v0.3-s3临时、缓存、构建、证据目录。无项目Builder指南，沿全局模板回退。保护旧产品与工具；缺陷报告协调者。

| 子阶段 | 范围 | 依赖 | 验证 | 状态 |
| --- | --- | --- | --- | --- |
| B1 | 只读host、唯一attempt/检测器、资产身份 | 无 | 11类独立子进程负控、许可证/固定SHA | 完成 |
| B2 | 固定29模拟门闩矩阵 | B1 | 精确错误、隔离/恢复、资源和事件门槛 | 首次正式run通过，29条完整 |
| B3 | 固定28真实矩阵 | B1 | 双CPU实例、R2排队、取消L1/L2、RSS/FD | 首次正式run通过，28条完整 |
| B4 | 三预设、文档、身份交付 | B2/B3 | 全CTest、格式/人工、原始复算与保护 | 三套20/20；Builder001交付，待独立Reviewer |

未修改产品/旧测试与工具。完整证据见[Builder001](../../reports/V0.3/S3-report-001.md)与[实测结果](../../../acceptance/V0.3/S3-results.md)。累计返工仍1/2，Builder自测不替代独立验收。

## 最后允许返工：F-001

Reviewer001 FAIL后累计2/2。B4补充运行期间128MiB总量预算，BudgetTests七个非零负控＋正常短控通过，三套MvpDetectors各1/1；原功能矩阵/三套完整结果按精确SHA复用。Builder002交付后停止，等待独立Reviewer；如再需第三轮必须硬停交协调者。
