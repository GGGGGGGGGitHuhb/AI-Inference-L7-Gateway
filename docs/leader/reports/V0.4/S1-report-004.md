# V0.4/S1 Leader 恢复与有限返工报告004

2026-10-20，Approved / Ready for Builder，累计**3/3**（用户新增额度1/1）。

## 第一部分：PM 决策摘要

**结论：At Risk，按用户明确新增一轮授权恢复。** 旧2/2停止记录保留；本轮是唯一新增额度，再需纠正立即硬停。阶段尚未完成或验收。

**计划与实际：** 新增迟滞测试已执行部分状态检查，但末尾SSE正文校验失败。只读发现其使用默认buffered解析模式，与SSE响应不匹配；正确流模式还要求增量收集bodyFragment。仅授权修新增测试校验和诊断，产品、负载、阈值不变。

**证据与不确定性：** 失败日志未记录parser错误码，模式不匹配是源码事实，尚未运行证实该次具体拒绝原因。原Release联合断言的子条件仍不能回溯，不把历史失败写成已确诊。

**PM决策：None。** 用户已明确授权本次有限恢复。Builder执行最小修复、三套定向与完整回归；Reviewer独立三套和原57cell/7590ID。Builder既有性能证据按SHA复用。完成后文档收口、本地提交、不推送，不启动产品优化。

## 第二部分：详细工作记录

供PM按需查阅。

用户授权原文：“允许再进行一轮有限返工，继续把 v0.4/s1 完成，文档同步，完成后提交不推送。”新[返工003](../../reworks/V0.4/S1-rework-003.md) SHA256 `fdb5c790221e6f5552384a082d1f5cc1a5b1ca32c11a78662df92c5459938dfc`，优先规定新增1轮与本次校验修复范围。原[停止记录001](S1-stop-001.md)、[返工002](../../reworks/V0.4/S1-rework-002.md)、[Leader003](S1-report-003.md)与[Reviewer001 FAIL](../../../reviewer/reports/V0.4/S1-report-001.md)保持原文，历史2/2不是当前剩余额度。

读取targeted-debug-rework002.log与两测试完整diff、HttpParser默认参数/selectResponseMode/validateHeaders/parseBytes/handleBody以及StreamingParserTests::parsePieces。新增Runtime校验构造默认kBuffered，SSE头在该模式被拒绝；kAllowEventStream下每次16KiB片段且message().body空。最小修复应正确选择模式、增量推进consumedBytes、逐次累计bodyFragment，验证完整chunk终态/全部wire无尾随/正文精确32769字节及decodedTotal一致，并记录错误分支。不能直接放宽正文校验、扩大parser缓冲或用finishInput弥补截断。

原真实high触发、分拆日志、high→16384→8193→8192迟滞/token/不读/排空保障保持；模式校验成功不单独替代整个用例或回归通过。各角色按限定次数执行，未解释失败即停止，禁止复测择优。性能产品与发压身份不变时Builder矩阵可复用，Reviewer正式矩阵未开始，仍须独立完整执行。

沿原生WSL/bash login=false、Leader v0.4-s1临时/缓存目录与显式环境。只读进程列表在当前沙箱可见范围未见相关负载进程，不将该视图声称为宿主全量PID核验；执行者仍按原任务进程记录在适当权限下核对，只清理本任务所属PID。Leader未杀进程、未实现、未运行测试/矩阵。

根当前状态更新恢复3/3，新增本报告/返工003，旧Stop/FAIL/Approved/报告及未交付测试diff保持。保护/链接/diff检查见build-local/leader/v0.4-s1/evidence/rework-003-check.log，身份见rework-003-identity.json。交Builder后停止修改，完成后由协调者提交不推送。
