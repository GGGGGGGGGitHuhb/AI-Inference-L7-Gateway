# V0.4/S2 Leader 有限恢复报告005

2026-10-21，At Risk，累计返工 **3/3**。

## 第一部分：PM 决策摘要

**结论：按用户新增一次“批准”，允许有限恢复独立验收。** 已完成只读诊断；上次外层执行退出143，但信号来源和确切原因仍未知，不能称产品错误、工具超时或环境抖动。旧14/21实验不足以验收。

**计划与实际：** 产品和实验工具无需修改，已有独立三套21/21及控制证据与当前身份完全一致，可以复用。增加有限执行生命周期记录与子进程回收，再从头独立执行一次完整21cell/2970ID；不拼接旧样本，不调整性能门槛或预算。

**重大偏差与风险：** 本次是用户新增的第3/3轮，保留原2/2停止记录；未知宿主终止仍可能发生，监督记录不等于已经解决根因。若出现新阻塞，停止且不自行开展第4轮。完成新run也不会倒推上次为何中断。

**PM决策：None。** 用户已批准这一有限继续，[返工003](../../reworks/V0.4/S2-rework-003.md)将其具体化。下一步Reviewer保留全部历史并执行一次完整复验、自写审计；独立PASS后Leader文档收口、协调者本地提交不推送。当前仍未完成。

## 第二部分：详细工作记录

供PM按需查阅。

### 输入与诊断

读取Stop001、Builder004及Reviewer只读诊断`build-local/reviewer/v0.4-s2/evidence/stop001-readonly-diagnosis.md`与JSON，后两者SHA分别为`d408057c8238dda36abee95b576cd4f87756c72eba290142610e40d38a7f675c`、`e9edf5c8194a100597699aa5f0fc1fd0b904c863205c0eae42bb3724a1f9fce3`。原session62465的exec/write_stdin均await，yield为返回周期，不能归咎unawaited或默认总timeout。143仅外层结果，无Python信号/发送者日志；原result/exit缺失且两backend遗留意味着完成记账中断。时间标记不足以给出精确终止时点，未显示达到内部预算期限。

identity-before.json SHA `cc1b0765e887fc151957d778ff581b544deeb3986240842994b0cf43cd6100e7`中的249保护/9源与配置说明/42Reviewer产物无漂移；三套完整21/21、控制与独立反例此前均已通过且hash明确。只按身份复用这些证据，不复用中断性能样本，不冒称重跑测试。Builder004的完整矩阵与结果继续作为Builder独立批次保留。

### 采纳方案与权威

[返工003](../../reworks/V0.4/S2-rework-003.md) SHA256 `d28f69e9de47a15ac77ee29058c576cb0c55b7ef10c50e83fa9a87fdb4fe2ac2`，明确记录用户“批准”新增一次，3/3不抹去2/2历史。原返工002额度条款仅按这次用户授权允许继续，其余实现/测试条件保持。

监督器仅放Reviewer evidence，标准库/subreaper、runner独立session、信号与returncode持久化、10s有界停止及收养子进程精确回收。外层960s不改runner900s、cell60s、client16s，外层事件64KiB/console1MiB独立硬上限；原1GiB实验预算/采样/到达均不动。正常路径不增加工作负载采样、不阻塞客户端；保持子进程原始退出码和失败语义，不能将child非零或监督错误改写为0。wrapper仅改善执行取证，不宣称已经排除未知中断。

全新run002完整21cell/2970ID一次，停止后不允许run003或第四轮纠正。完成后按原审查计划独立复算及验收；关键缺证仍FAIL/BLOCKED。保护源/hash需再确认，若测量相关漂移先停止；不由身份例外悄悄授权新源修改。

### 路线与交接

继续原生WSL bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway，分支codex/v0.4-s2-evidence-driven-improvement、HEAD752987a；S2工作区保留。各角色独立tmp/cache/evidence与显式环境，socket/LSan窄权限，执行await persistent session并≤30s轮询。Builder已停止，Reviewer在本权威交接前仅只读诊断；Leader没有实现或测量。无安装、下载、系统调优或产品变更。

新增本报告和返工003，原设计/审查、Stop001、失败原始目录与旧报告不覆盖。git diff --check通过。根当前状态留待最终独立结论同步，不能提前标记完成或声称候选推荐；最终仍以独立PASS→文档收口→本地提交不推送结束。
