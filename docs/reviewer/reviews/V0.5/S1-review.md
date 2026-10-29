# V0.5/S1 独立审查计划

Approved，2026-10-29；依据 [S1设计](../../../leader/designs/V0.5/S1-design.md) 及用户启动授权，随 Leader001 采纳。

- RV-01 → AC-01：检查 git diff 与源码身份，确认两仓产品、旧测试和历史报告不变；L4LB 当前工作树有用户改动，构建身份须包含实际文件 hash，不能仅写 HEAD。独立构建真实两个产品到 reviewer/v0.5-s1，检查例子与运行配置一致。
- RV-02 → AC-02：独立运行完整 RunTopology；逐案例查请求 ID、响应正文、L4 accepted 归属和 health 转换；核实 keep-alive 未新建连接，故障流不是超时伪成功，幸存流完整、无重试重放，全部不可选时没有 fallback。
- RV-03 → AC-03：核实两个网关各一个 in-flight、第三请求在目标网关被拒绝且后端无该 ID；模型 HTTP 故障仍不能触发 L4 应用摘除，另一模型可用。只接受单进程配额和 TCP 可达性结论。
- RV-04 → AC-04：独立运行检测器负控，并自写至少一个独立反例或证据审计，禁止只复述 Builder 的 PASS。核查有限等待、新输出目录、失败证据保留、自有 PID 清理和预期/意外退出区分。运行既有 Release CTest 或明确可复用的精确源码身份与 Builder 日志；不得冒称未执行检查。
- RV-05 → 全部：检查可复制操作说明、部署例子、结果边界和状态一致性。性能、XDP、真实模型收益均不在本阶段。

PASS 需要全部关键路径可验证且无 Major；发现实现缺陷记 FAIL 并交回协调者，不修改产品或 Builder 文件；环境无法执行关键路径记 BLOCKED。输出新 docs/reviewer/reports/V0.5/S1-report-001.md，附自有命令、结果、证据目录、逐项结论和剩余限制。仅在 PASS 后由 Leader 收口。
