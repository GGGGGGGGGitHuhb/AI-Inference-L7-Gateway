# V0.4/S1 Leader 最后统一返工报告003

2026-10-20，Approved / Ready for Builder rework，累计**2/2**。

## 第一部分：PM 决策摘要

**结论：At Risk，进入最后允许的统一返工。** 独立Release回归20/21，Debug/ASan各21/21；正式Reviewer性能矩阵尚未启动，不能宣布阶段完成。

**计划与实际：** 原暂停断言同时要求token注销和当前pending仍高于高水。源码允许同轮下游写将pending降至高低水之间但保持暂停，旧观察要求可能过强；原日志未分拆，不能确定首次失败根因。已授权仅修测试契约/诊断并增加确定性迟滞验证，不改产品。

**保障：** 保留真实高水触发、token注销、暂停不读、低水恢复、新token、完整正文及停止清理。新用例通过实际收发/状态转换证明high→中间→low，不直接改状态模拟通过。

**风险与取舍：** 双方三套完整回归必须重新通过；Builder原性能证据可在产品/发压/测量产物身份不变时复用，Reviewer仍须完整57cell。未知失败或产品缺陷立即硬停，不能进入第三轮或循环复测洗绿。新增债务/PM决策：None。

**下一步：** Builder执行限定测试修复、定向及完整回归，Reviewer独立验收后才继续正式矩阵。本次整条交接同属2/2；最终本地提交不推送，不启动S2优化。

## 第二部分：详细工作记录

供PM按需查阅。

[Approved返工002](../../reworks/V0.4/S1-rework-002.md) SHA256 `455c6aceeda923b8f4c3c1acc1f866e1a815be4bd3e2b27678eb5d70dde3b868`。原设计/审查/返工001/Leader001–002与Builder历史均保持。触发[Reviewer001 FAIL](../../../reviewer/reports/V0.4/S1-report-001.md) SHA256 `01297ec01a22e62ea29599de220b51cc489387faf0d26737641c450a8e7f70fa`。

完整读取Reviewer报告与BackpressureTests原场景、ProxySession pauseUpstream/resumeUpstream/acceptStreamResult/writeStream，以及现有RuntimeTests FakeIo入口。首次失败在testSlowReader(1,false,stopMode=1)第一次pause后、SIGTERM前，联合断言无具体子值；一次授权同binary诊断979通过不是修复证据。源码迟滞允许low<pending<high且paused，是可验证机制解释，不能反推出首次现场token一定为0。

明确旧测试保护例外仅BackpressureTests必要观察/诊断与RuntimeTests现有FakeIo最小新增用例，可选择在Backpressure文件内建夹具；不放开旧测试任意重写。真实pause计数与本次high证据必须分离其他session/历史峰值，不能只降低pending门槛。确定性路径受控实际读写到中间水位、low+1、恰low，分别检验暂停和恢复，不改产品状态。非法快照负控补充而非替代真实方法调用。

Builder三个预设各一次定向后各一次完整CTest；Reviewer独立三套完整后完整57cell。出现未解释失败停止，不循环择优。产品、发压、计量host与性能binary不变才允许Builder正式run复用；受影响测试binary必须在新身份清单明确列出。若发现产品缺陷或范围扩大，交协调者硬停裁定。

原生WSL/bash login=false，角色v0.4-s1独立tmp/cache/evidence和显式临时/缓存变量；socket/LSan首次窄升级，C++规则/格式/人工检查保留。Leader仅只读裁定与文档，未跑测试/负载、未改实现。根当前权威同步最后返工2/2；检查/身份见build-local/leader/v0.4-s1/evidence/rework-002-check.log及rework-002-identity.json。交Builder后停止修改。
