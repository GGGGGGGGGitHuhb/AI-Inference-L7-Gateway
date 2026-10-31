# V0.6/S2 直接归因取证 Leader 002：启动

## 第一部分：PM 决策摘要

2026-10-31，On Track。用户明确“那就按计划开始吧”，[取证设计](../../designs/V0.6/S2-trace-design.md)与[审查计划](../../../reviewer/reviews/V0.6/S2-trace-review.md)由Draft转为Approved，进入实现与验证。上一轮取证规划门槛保持，不代表已取得关闭来源或性能收益。

先实现默认关闭观察设施并验证正确性，冻结工具/构建/清单后，按既定低档开销门槛决定能否进入高档。单角色最多18项/1200秒/4GiB；首错和开销不通过均按设计停止，不重置历史预算。Builder实现，Reviewer独立审查，角色串行发压。L4原工作树保持只读，补丁仅用于本仓隔离副本。

PM额外决策：None，既有启动授权覆盖本轮工作。尚未开始S2产品优化；发现重大偏离时先记录影响，不擅自放宽门槛。完成后按既有指令提交推送，不合并或发布。

## 第二部分：详细工作记录

起点75460201474b6fdbf2af5ba2eee298c88d0d67b8，执行分支codex/v0.6-s2-trace。沿用原生WSL /home/power/projects/AI-Inference-L7-Gateway；各角色build-local/ROLE/v0.6-s2-trace/{tmp,cache,evidence,gateway,l4-source,l4-build}，显式临时/缓存变量。无包下载、系统参数修改或外部源码写入；回环测试与Git采用已知窄权限路线。

使用plan-project-docs、agent-execution-route及personal-cpp-standards；本仓无专用AGENTS/GUIDE，角色读取全局对应模板。既有S1/preflight证据和工具只读。实现前冻结事件布局/单连接记录上限与最坏预算，压力前由Leader核对实际回归和独立静态意见，不能仅凭设计已批准跳过前置条件。

准备阶段发现L4既有metrics TCP测试在未插桩构建同样失败，直接取证第一次accept为EAGAIN且所有创建计数为0；按[返工001](../../reworks/V0.6/S2-trace-rework-001.md)仅在隔离测试副本的真实connect后增加有界监听就绪等待，保留原断言与产品行为。此时仍未开始三项负控或性能采集，不把该测试修正计为产品提速。

随后独立U又暴露metrics真实后端尚在SYN_SENT时强行设connecting=false、以及shutdown将源耗尽平台误当双向背压的测试前提。直接send/计数证据保留，按[返工002](../../reworks/V0.6/S2-trace-rework-002.md)仅在隔离测试补后端可写等待及有界双向续供/差额谓词，原正send字节、双向pending、停止与回收断言全部保持。尚未性能采样，不据临时某次通过抹掉独立失败。

采集前双方Gateway U/O完整回归、L4 U/O TCP 13/13及Builder ASan+UBSan受影响7/7通过；Reviewer最终独立12+9+3项工具检查和完整源清单校验通过。Leader冻结Builder manifest-frozen-001.json（SHA256 502047b4ade0787b8a0da1b75f8778e0d55774dda9de0922f963ed8bdeaf83b0），授权三控制和九项低档；高六项仅由既定低档全门槛解锁。Builder先运行、Reviewer随后独立反序，首错不重试或续采。此为采集前放行，不是归因或阶段验收。
