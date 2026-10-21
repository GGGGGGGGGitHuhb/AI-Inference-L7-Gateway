# V0.4/S1 返工001：连接实例关联

2026-10-20，**Approved / 待实现**，累计返工**1/2**。用户阶段启动与既有技术委托授权本范围内纠正。原[设计](../../designs/V0.4/S1-design.md)、[审查计划](../../../reviewer/reviews/V0.4/S1-review.md)、[Leader001](../../reports/V0.4/S1-report-001.md)原字节保持；本文件仅限定工具关联修复及验证范围，不改固定矩阵/到达/SLO/预算/产品。本次Leader→Builder→Reviewer为同一轮1/2，非另起一轮。

## 1. 触发与证据

正式run-001在第14个cell `13-H-0-LI`收尾审计失败：`client/host association ambiguous`，完成13cell，T前后控制尚未闭合。`RunExperiments.py`对每个client_port要求全cell仅一个host记录，错误地把临时源端口当连接终身唯一ID。

失败目录 `build-local/builder/v0.4-s1/evidence/run-001/13-H-0-LI/` 中warmup-000与formal-118均源端口40074，约7.16s后复用；对应host Session1/129，130attempt与130host记录完整。`association-failure-001.json`、`failure-readonly-audit-001.json`及`failure-live-process-audit-001.json`记录诊断；全run已有2192attempt、5398not_started，合计7590唯一ID，55start/55reaped且PID均已消失。原run状态仍FAIL，不能离线改成完整成功。

## 2. 最小修复与不变量

只允许父进程在全部请求结束并排空之后修改审计关联函数，以及新增对应短检测器/文档。不得改Client发压、host、产品、负载、时序、端口分配策略、连接参数或失败阈值以避免端口复用。不得仅按warmup/formal分组，因为正式阶段内也可能复用。

分组键是**同一cell/同一host进程生命周期/同一TCP四元组**。当前单IPv4 loopback客户端与单监听地址/端口固定，可由配置和现有target_port/client_port还原四元组；必须验证这些固定前提，不能把跨cell或跨进程数据混合。若后续有多个地址/监听且现有证据不足，明确拒绝，不能猜测。

在每个组内：客户端按已建立连接的发生次序排序，host按accepted时间排序；双方顺序唯一、计数相等且每个连接恰一次使用，然后按序号一一映射。验证客户端每条connect/closed存在且时间顺序合法、同组上一closed不晚于下一connect；host每条accepted/finished存在且合法、同组上一finished不晚于下一accepted。排序键相等或重叠/缺终态/数量差/重复ID/重复消费均拒绝歧义，不任取第一个、不最近时间模糊匹配、不靠延迟阈值丢候选。跨进程时钟不用于计算等待或延迟；仅分别使用两侧内部顺序和非重叠证明。

not_sent/not_started及连接未建立的attempt不参与已建立连接关联，必须显式分类并核对不存在对应host；不能把缺client_port的记录静默当已成功映射。当前成功cell全部已建立请求应与host完全守恒；额外未配对host也拒绝。若失败路径无法证明连接身份，保留原始证据并使该审计失败，不把工具关联缺口包装成策略负面结果。queue wait/target仍来自被唯一匹配的同一host Session，不能拼接不同连接字段。

## 3. 必需验证

1. 最小回归：原失败130attempt/130host离线审计，40074两条分别唯一映射Session1/129。新结果写独立audit目录，原run文件与FAIL保持。其余已完成13cell可同法离线审计，但不补作完整性能结论。
2. 真实loopback短控：自有listener与同一固定源端口先后建立至少两条连接，确认两条四元组相同、连接生命周期非重叠、响应各有不同可核对标记；若环境不能立即复用，可在有界10s内完成有意的服务端先关闭/正常回收握手，不能只伪造端口字段。仅短控可显式绑定源端口，正式发压策略不变。同时覆盖跨warmup/formal与同formal内重复，验证具体ID→Session映射。
3. 拒绝负控：计数不等、任一侧区间重叠、排序时间相等/缺失、重复ID或host消费、额外未匹配host；均真实调用修复函数并非零/抛出预期错误。保留不复用端口普通路径及未发请求边界。
4. 精确源码diff/SHA证明产品、C++host、Client发压/时钟/配置、固定矩阵与原产物未变；新增短检测器纳入现有受影响检测器入口，三套运行相关检测器。若CMake/C++不变不要求无意义重建；已有完整三套回归按身份记录复用边界。

## 4. 正式重测与独立接受

**修复后必须完整新run-002执行原57cell/7590ID**，不只续跑剩余cell：原T最终控制缺失、整轮配对与机器时段未闭合；拼接旧13cell和新后半会破坏完整计划。不得挑选性能最好数据，run-001完整保留及说明工具身份；run-002即使性能更差也如实呈现，原负面/工具受限接受门槛不改。不得在修复前先重跑或改变参数绕开问题。

新run完成后Builder报告本轮修复、所有短控、原失败与新正式结果/准确身份，再交Reviewer。Reviewer独立检视差异和端口复用短控、追加至少一个同formal复用/歧义拒绝控制，并按原设计完整独立57cell、三预设回归及独立复算。原失败不是Reviewer数据，不可当Reviewer已执行。未修关联、短控或完整计划失败则不能接受；若需再次统一纠正累计2/2，由协调者决定，不能私自反复重跑选优。

本轮原生WSL/bash login=false、角色独立v0.4-s1目录与显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；socket/LSan首次精确升级。仅修工具审计，V0.4/S2及产品优化不启动，最终本地提交不推送。
