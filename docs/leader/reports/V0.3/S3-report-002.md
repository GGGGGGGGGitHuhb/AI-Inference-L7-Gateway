# V0.3/S3 Leader 规划纠正报告002

2026-10-20，Approved / Ready for Builder，累计返工**1/2**。

## 第一部分：PM 决策摘要

**结论：On Track，规划纠正完成，可交Builder。** 已冻结包交接核对发现两处文档问题，按Olympus累计返工1/2；尚未实现或完成S3/MVP。

**计划与实际：** 修正大请求排队字节超限错误码为503 queue_bytes_exceeded，并把故障恢复组列成唯一八条请求ID。两个实例摘除期限检查是只读状态观察，不增加请求。原三件Approved包保留，以新增返工文件叠加生效。

**已验证：** 源码确认先count后byte检查及对应错误码；模拟总数仍29（19成功/2取消/2失败/1排队超时/5拒绝），真实总数仍28（26成功含2预热/2取消）。本次仅文档自查，未运行负载。

**风险与偏差：** 冷却及排队门槛保持原期限，时窗错过必须保留失败，不能补样本或扩时。重大范围变化、新依赖、债务及阻塞：None。

**PM决策：None。** 依据已有技术委托纠正方案。Builder按原包加返工001实施，Reviewer按同一叠加权威独立验收；通过后再收口、本地提交不推送。

## 第二部分：详细工作记录

供PM按需查阅。

生效顺序：[返工001](../../reworks/V0.3/S3-rework-001.md)优先覆盖原设计M2/M4指定文字，其余设计/审查/Leader001不变。返工SHA256 `993c9ae4ea64991803a9fbe49a1bf353c3d04f6df2a4854c131c161852dc99de`。

原[设计](../../designs/V0.3/S3-design.md) SHA256 `b0d9fd9a518436631ecfd189d3bb50488b4edb3c7d6fb7cde24c81520901e49d`；原[审查计划](../../../reviewer/reviews/V0.3/S3-review.md) SHA256 `2b3e3ce3d1a030c25b1b08800a942d41107ee0ebf04173b4f3d281ac30ae62f4`；原[Leader001](S3-report-001.md) SHA256 `f84692aff330a086d468234a9a2a1aa0b2c40720f107c7a89e7d6efcc5c97be5`，均保持原文。原0/2是交接前历史状态，当前1/2。

实际读取AdmissionController::enqueueRequest与ProxySession映射。F-001纠正测试期望，不改已接受S2行为；F-002明确01坏chunk、04连接错误、05唯一全不可用拒绝、06完整成功恢复、07/08新请求正常。06后重新启用a2模拟监听避免07因无关冷却候选失败；仅控制模拟后端，不写Router健康状态、不新增HTTP。M1/M2字节与count先后、M3取消推进、M5停止时窗及各组分母已逐项自查，完整表见返工。

本轮新增返工001和本报告，根README/ROADMAP/ARCHITECTURE仅同步叠加权威与当前1/2。沿原生WSL/bash login=false、Leader独立tmp/cache/evidence及显式环境，不改代码/测试/旧报告、不跑负载。检查记录见build-local/leader/v0.3-s3/evidence/rework-001-check.log，身份见rework-001-identity.json。

交Builder执行，独立Reviewer尚未接受；两项文档歧义已纠正不等于功能验收通过。保持原数量、期限、资源门槛、资产及发布边界，不增加第三轮自动返工。
