# V0.6/S2-trace 返工001：隔离副本TCP测试就绪前置条件

Approved，2026-10-31。依据用户已授权“按计划开始”的实现/验证范围，由Leader采纳本次测试可靠性修正；Reviewer已确认不改变产品决策或原断言。仅补充[S2-trace设计](../../designs/V0.6/S2-trace-design.md)§2隔离补丁范围与§6 TCP回归执行方式，其余条件、预算和AC1–AC4不变。

## 触发证据

Builder L4 O TCP回归12/13，v03_metrics_tcp_events失败“real created point”；Reviewer独立L4 U也复现。Builder在本轮tmp复制未应用诊断补丁的实际原始TcpReactor.cpp和metrics_tcp_test.cpp，Release -O3同样失败。只加返回值/计数打印的取证显示第一次acceptCall调用1次，返回−1/errno11，created/active/errors/closed/rejected/internal_sessions均0，见build-local/builder/v0.6-s2-trace/evidence/l4-metrics-original-accept-debug.log。旧失败和该临时取证保留，不作性能样本。

测试在client connect后直接调用非阻塞accept，没有等待监听可读。当前失败现场证明该前置条件尚未成立；不据此认定产品创建计数错误，不降低原生命周期/字节断言。

## 修正要求

- RW01：只改本仓L4隔离副本的tests/metrics_tcp_test.cpp，并纳入版本化L4ConnectionTrace.patch。对该测试五处真实新client connect成功后、对应acceptClientSessions之前，增加监听fd的有界poll(POLLIN)等待；最多1秒，EINTR按剩余单调时间处理，超时/错误明确失败。不能对刻意注入accept错误的调用套等待，不能循环accept直到计数符合预期。
- RW02：原metrics、字节、关闭幂等、拒绝、超时、停止断言全部保持。L4产品accept循环、Socket和callback控制流不得为通过该测试而修改。外部L4原文件/工作树保持，只对隔离测试补前置条件。临时调试打印不进入最终补丁。
- RW03：保留002候选和全部失败，更新补丁/实际隔离源身份。Builder与Reviewer各自重建受影响U/O测试，然后完成此前暂停的TCP相关回归。Gateway源未变则不重复已经通过的独立回归；共享诊断实现若变动，另按实际影响重新核验。

## 收口与边界

Reviewer独立确认有界等待只建立真实事件就绪前提、原断言未删改、产品二进制/源保护保持，再判定TCP回归。此文不提前宣布测试或阶段PASS。失败仍需保留并定位，不通过就禁止采样。18cell/1200秒/4GiB及低档/高档门槛不变；本次准备阶段定向回归不是性能矩阵，也不授权额外发压。

Builder/Reviewer在本阶段各自S2-trace-report报告中引用本返工与实际证据；Leader最终收口披露唯一测试副本例外，不把它描述成产品优化或原始测试首次通过。
