# V0.3/S3 独立验收计划

**Approved**，2026-10-20。依据[S3设计](../../../leader/designs/V0.3/S3-design.md)与用户阶段启动/技术委托，初始返工0/2；本文件不是验收结论。Reviewer不复用Builder进程、二进制或可变输出。

| RV | 对应AC | 必须独立验证 |
| --- | --- | --- |
| RV01 | AC01 | 校验本地server/model/库身份和许可；自有端口/PID，两CPU实例；正式程序R0代理冒烟、独立启动说明无Server/L4LB依赖 |
| RV02 | AC02 | 原配置完整运行R0–R3，28attempt（26正常成功含2预热、2预期取消）；R2真实排队至少1，目标实例和RR可追溯；SHUT_WR不误取消，L1/L2必证、L3限定 |
| RV03 | AC03 | 独立门闩M1–M5，29attempt：19成功/2取消/2后端失败/1队列超时/5拒绝；模型隔离、FIFO、恢复试探、已提交截断与停止，正确精确错误码 |
| RV04 | AC04 | 从原始attempt独立重算分类与min/median/max；不可删除异常、预热独列；验证账本峰值/排空、FD及RSS，确认采样不冒充瞬时证据；负控必须非零 |
| RV05 | AC05 | 独立debug/release/asan全CTest；相关C++规范正反例与clang-format；旧Approved/报告/测试断言/工具保护，源与产物SHA；所有所属进程回收，文档命令可复现 |

工具源码重点检查finally逐尝试唯一留存、超时传播、不吞future错误、HTTP增量和合法终态、monotonic时钟、排队等待分母、子进程清理和不可覆盖run目录。额外独立负控至少包含一个部分响应失败被错判成功、一个漏样本和一个末态额度非零；不能只调用Builder summary证明正确。

正式真实/模拟各一次，失败保留再以新前缀复验；不改固定数量、期限或指标来通过。角色目录build-local/reviewer/v0.3-s3，自有tmp/cache与显式环境，原生WSL/bash login=false；socket/LSan首次精确升级。复用只读模型资产，等待Builder进程回收后启动。不得重跑P1长矩阵或把小样本当容量/性能收益。

全部AC满足才PASS。缺资产/运行受阻须如实Blocked；未满足排队、响应完整性、资源或分母则未通过，不以“历史通过”替代。发现统一交Leader，最多两轮，不私下扩产品或改Approved契约。报告保留初次失败、变更范围和复用依据，并明确V0.3尚需Leader收口；无债不建空清单。
