# V0.5/S2 独立审查计划

Approved，2026-10-29，依据用户启动授权、Leader001及[S2设计](../../../leader/designs/V0.5/S2-design.md)。

- RV01→AC01：独立核对source hashes/dirty diff、保护范围、运行配置同workload仅拓扑和每实例额度差异，总额度32，关闭两侧复用；独立Release构建和一次完整18cell，逐ID4536完整，不复用Builder样本。
- RV02→AC02：检查scheduled origin、first-wire/first-body/framing/EOF区别，复算每cell分位/延迟/CPU ticks到秒与实际窗口，检查量化警告、完整分母和arrival标记。负控伪成功、时钟倒置、缺/重ID必须失败。
- RV03→AC03：自写审计（不调用Builder汇总函数）核对client tx/rx、backend counted bytes和L4正式session closed字节；预热隔离，无重复计边，CL/chunk完整，backend accepts与ID一致。字节破坏负控必须失败；结论不得声称TCP包/物理NIC总开销。
- RV04→AC04：独立偏斜案例由实际session日志验证8连接4:4而在途4:0，长流结束不重放。逐重复M↔L和D↔M差值与测量标记保留，固定rate不证明容量，受限结果不包装成横向扩展收益。
- RV05→AC05：独立负控失败取证/重复目录/预算门槛；检查绝对deadline、所有PID退出、FD有限回归、源身份前后一致与64MiB硬分配边界；独立ReleaseCTest21项。产品未改不强制重复Debug/ASan或旧性能矩阵。报告所有未测范围。

结论PASS要求全部关键证据成立且无Major；测量质量标记触发只允许明确受限描述性结果，不降低正确性门槛。代码或数据错误FAIL；关键环境/权限缺失BLOCKED。Reviewer只写新的docs/reviewer/reports/V0.5/S2-report-xxx.md，不修改Builder实现或替Leader批准设计。由Leader按独立结论收口。
