# V0.6/S2 前置诊断审查计划

Approved，2026-10-31，依据[前置设计](../../../leader/designs/V0.6/S2-preflight-design.md)。不授权产品改动。

- AC1：独立检查新包装器预算、全矩阵预留、防覆盖、进程清理、工具/源码hash、绑核实际生效；自写抽样/全量计数核对客户端结果与后端，S1历史取证无写入。
- AC2：使用Reviewer自有S1 Release二进制，经当前源和hash核验；本轮自有新目录，Builder结束后反序12cell，无并发压力。审查全部结果，不按方向选点。
- AC3：复核无响应失败的phase、errno及L4生命周期，明确无HTTP ID关联时的证据限制；不以成功分位代替完整分母，不以双后端收益宣称同资源加速。
- AC4：工具完整性或预算失守FAIL；实验失败保留并停止，相关归因BLOCKED；有效负面诊断可接受，但S2产品入口需可行动代码热点与对照基线，不能自动PASS。

报告写入docs/reviewer/reports/V0.6/S2-preflight-report-001.md；未实测项明确标记，历史证据不得冒称重跑。
