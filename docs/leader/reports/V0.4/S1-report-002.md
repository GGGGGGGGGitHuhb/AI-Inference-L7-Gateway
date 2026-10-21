# V0.4/S1 Leader 统一返工报告002

2026-10-20，Approved / Ready for Builder rework，累计返工**1/2**。

## 第一部分：PM 决策摘要

**结论：At Risk，已定位工具关联缺陷，可按限定方案返工。** 首次正式run在第14cell收尾失败，13cell完成，尚未完成阶段。失败不涉及已知产品故障或样本丢失。

**计划与实际：** TCP源端口约7.16秒后被另一连接复用，父审计把端口当唯一身份而拒绝。修复限于收尾审计，按同四元组连接顺序逐一关联，严查数量、非重叠和唯一消费；补真实端口复用及歧义拒绝短控。产品、host、发压和固定参数不改。

**已验证：** 失败cell的130attempt/130host完整；全计划2192已执行+5398未开始=7590唯一ID，55个子进程均回收。相关源和产物身份未变，原run保持FAIL。

**取舍与风险：** 原57cell及前后工具控制未闭合，短控通过后需完整新run-002，不能拼接旧13cell与新后半。这增加一次完整测量时间，仍沿原60分钟硬限；不择优、不扩负载或放宽SLO。新增债务/重大范围变化：None。

**PM决策：None。** 范围内技术委托授权本次纠正，Leader→Builder交接属于同一轮1/2。Builder修复/短控后完整重测，Reviewer按原规模独立验收；最终本地提交、不推送。

## 第二部分：详细工作记录

供PM按需查阅。

新[Approved返工001](../../reworks/V0.4/S1-rework-001.md) SHA256 `c3f9beb16539e7e7f3799a5771e6d14326cf543096b263e069b21d6ee28fcd66`。原[设计](../../designs/V0.4/S1-design.md)、[审查计划](../../../reviewer/reviews/V0.4/S1-review.md)、[Leader001](S1-report-001.md)字节保持；其0/2为历史规划状态，本次统一推进1/2。

读取RunExperiments.py父端client_port唯一匹配、RuntimeHost.cpp的accepted/finished/id/client_port与Client.py connect/closed记录，以及run-001/result.json和失败cell原始两attempt/host-final-records。warmup-000和formal-118均40074，对应Session1/129；端口只在同一连接生命周期内参与四元组身份，不能跨全cell视为永久唯一。修复不按phase切分，避免正式内部复用再次触发；双侧各自时间顺序和非重叠验证，无跨进程时钟差用于性能指标。

证据根build-local/builder/v0.4-s1/evidence：association-failure-001.json、failure-readonly-audit-001.json、failure-live-process-audit-001.json、run-001-failure-raw-sha256.json。只读核查记录116源与51产物、212历史保护项无差异，7590 ID完整闭合，55start/reaped全部退出且实际PID不存在。原第14cell虽130请求完成，但未通过收尾审计，不写作14cell成功。

最小修复范围是父进程后置关联函数/新短检测器/说明，不改产品、host、Client、发压负载/时序、连接模式或端口策略。必须真实复用端口验证跨阶段及同formal，负控拒绝重叠、缺失、相等排序、数量差与重复消费。原失败可另目录离线复算，原目录和FAIL不变。由于T前后控制缺失及全矩阵机器时段不一致，接受所需正式证据为修后完整新run-002，原run不能拼接填补。

沿原生WSL、bash login=false、角色独立v0.4-s1目录与显式临时/缓存环境。当前只规划和只读核对，未改工具或跑负载；原权威/报告/失败证据保护及链接/diff记录见build-local/leader/v0.4-s1/evidence/rework-001-check.log，文件身份见rework-001-identity.json。根文首同步1/2与返工状态。交Builder执行，停止修改；不能把同轮交接算成2/2，也不能默默另起重测或优化。
