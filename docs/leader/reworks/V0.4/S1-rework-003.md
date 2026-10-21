# V0.4/S1 返工003：新增迟滞测试的流响应校验

2026-10-20，**Approved / 待执行**，用户新增授权额度1/1，本阶段累计**3/3**。用户明确：“允许再进行一轮有限返工，继续把 v0.4/s1 完成，文档同步，完成后提交不推送。”据此恢复[停止记录001](../../reports/V0.4/S1-stop-001.md)后的阶段；旧2/2停止、Reviewer FAIL及返工002首次失败原文保留，不追溯改写。不允许第四轮；再需纠正立即停止交用户/协调者。

## 事实与只读定位

返工002首次Debug定向：Backpressure通过，新增Runtime testStreamingHysteresis末尾`parser.parseBytes(fixture.io.sentClient).status == kComplete`失败；此前high32842、middle16384、low+1=8193有日志，low边界/token检查在失败行前，但整个测试未通过。证据为build-local/builder/v0.4-s1/evidence/targeted-debug-rework002.log。原Release联合断言失败的子条件仍不能回溯确认。

当前新增测试构造HttpParser(MessageKind::kResponse)，默认ResponseMode::kBuffered；HttpParser::validateHeaders在非eventStream模式拒绝text/event-stream（unsupported_stream）。这是源码可见的测试校验模式不匹配，首次日志未记录ParseResult错误码，尚未运行证实该次具体结果，不能宣称已复现。切换kAllowEventStream后，流正文每次parseBytes只保存在16KiB bodyFragment中，调用开始重置片段，message().body保持空；因此只改mode后仍一次喂全32769字节正文或比较message().body也不符合契约。现有StreamingParserTests::parsePieces为可参考模式，不修改解析器迁就测试。

## 最小允许变更

在已保留未交付两测试diff基础上，仅修Runtime新增迟滞用例末尾响应校验及必要失败诊断。保留返工002授权的Backpressure真实high触发/分拆日志与high→middle→low边界、不读上游、新旧token、暂停恢复、正文/资源保障；不删原断言以绕过，不改水位/期限/输入正文，不改产品、发压、矩阵或旧协议工具。

校验显式使用kAllowEventStream；以每次不超过16KiB的wire片段调用parseBytes，每次消费后立即累计bodyFragment；严格依据consumedBytes推进，要求正向进展、无Rejected且不重复/跳过字节。最终必须kComplete、全wire已消费且无尾随字节，decodedTotal与累计正文长度一致，正文精确等于32768个h加z，message().body空为预期。不要调用finishInput把缺chunk终止冒充完成；如使用它，只能证实已完成状态不变，不能替代chunk终态。

失败分支至少输出status/errorStatus/errorCode/consumed/累计offset/wire长度/decodedTotal/片段长度，让mode拒绝、fragment_limit、缺尾和正文不符可区分。可增加一项局部负控确认默认buffered对同SSE头拒绝unsupported_stream、正确流模式接受，从而固定此次测试API契约；不得修改HttpParser行为。若输出实为产品错误响应/截断或其他根因，停止报告，不自行扩大修复。

## 验证与停止规则

Builder实施一次最小修复批次，三个预设各一次定向Backpressure/Runtime，再各一次完整CTest。允许一次独立小型parser诊断用于明确默认模式错误码（保留日志，不启动完整Runtime反复复现）；不要求先故意重跑已知失败测试。未解释定向/完整失败即硬停，不迭代直到通过；编译问题保留证据且不得扩大语义范围。

Reviewer独立审查模式/分片/正文/终态和真实迟滞保障，三套完整回归通过后，执行原完整57cell/7590ID及独立数据审计。Builder已有正式run-002可按产品、发压、配置、计量host及性能binary SHA不变复用；两测试binary变化明确列明，不声称全部产物未变。旧Stop/FAIL、一次诊断通过、返工002初次失败和本轮证据分别保存；本轮通过不洗掉历史失败。

F-001及新增校验失败只有独立Reviewer接受后才关闭；原全部AC、固定负载/SLO/预算/工具限制不变。用户新增1轮不授权产品优化、阈值放宽、增加测量规模或自动接受债务。再有实质纠正需求累计3/3耗尽，立即硬停。

路线原生WSL/bash login=false，角色v0.4-s1独立tmp/cache/evidence，脚本显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；socket/LSan首次窄升级。执行前核对原命令已退出，进程只按本任务证据PID识别和回收，不按名称杀其他服务。Leader仅只读诊断与规划，不实现或跑矩阵。完成后协调者本地提交、不推送。
