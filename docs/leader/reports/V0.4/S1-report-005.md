# V0.4/S1 Leader 诊断优先恢复报告005

2026-10-20，Approved / Ready for diagnostic，累计**4/4**（新增1/1）。

## 第一部分：PM 决策摘要

**结论：At Risk，按用户新增一轮授权恢复，先观测再修复。** 原3/3停止历史保留，当前仅允许一次诊断优先的有限返工，无第五轮自动纠正。

**计划与实际：** 新增Runtime迟滞用例正文已验证，资源四项联合归零失败但具体值未知。先一次仅加日志的Debug定向，打印四项资源、finished/析构、timer/token/连接lease及终态/析构前后，再回报并按证据限定修复。

**只读依据：** Fixture::checkCleanup不析构session；session预约由成员RAII在对象析构时释放，而流资源在finished时释放。这是有源码支持的候选解释，不是本次四项实值或已确认无泄漏。

**风险与保障：** 不提前reset让账本归零，不删除保障，统一审计新增用例全部资源断言。若仅测试时点不对，修测试；若证据提示产品问题，先报告最小范围与性能影响，不擅自改产品。阶段未完成。

**PM决策：None。** 用户已明确授权。Builder一次诊断后先回报，再执行证据支持的限定修复与三套定向/完整回归；Reviewer独立三套及57cell。完成后文档同步、本地提交不推送。

## 第二部分：详细工作记录

供PM按需查阅。

用户原文：“允许再进行一轮有限返工，先把四项资源值和对象生命周期查清楚，再针对原因修复”。[返工004](../../reworks/V0.4/S1-rework-004.md) SHA256 `f86734b600db29be1275385a8e348431c6a831cb149b80df93015763c448a586` 为本轮叠加权威；[Stop002](S1-stop-002.md)、返工003、Leader004及Reviewer FAIL保持原字节。当前4/4仅新增一轮，不重置前三轮。

读取Stop002、targeted-debug-rework003.log、Runtime新增用例与SessionFixture、ProxySession构造/finishSession/析构、CapacityLease及BufferBudget。新增用例在checkCleanup后仍持session unique_ptr，checkCleanup只检finished/无上游/timer0；reservation_成员没有在finishSession主动release，析构成员时才由CapacityLease::~CapacityLease释放。streamCapacity_/pending/paused沿releaseStream清理。需以一次现场分项值证实，而不能拿源码预期代替实际结果。

A阶段仅诊断：完成前后、原断言前及异常展开析构前后打印四项、所有权有效性、token/timer/pool等；保留原失败传播。专用守卫/作用域确保budget等比session活得久，析构后不解引用对象。允许该一次预期失败取证，不把它算修后验证失败；回报四项实值与全部断言owner/时点表后才进入B。

B阶段条件限定：若仅session存活时保留16MiB预约，且流资源及时释放/析构全归零，测试分为finished但存活、正常销毁后两层断言，完整正文/迟滞/连接清理先检，不用提前reset遮蔽。若其他资源/生命周期不符，先报告实际证据及可能最小修复影响，不授权猜测产品修改。所有资源断言统一审计，不单行试错。

C阶段Builder三套各一次定向及完整回归，Reviewer独立三套与原57cell/7590ID。产品/发压/配置/测量host和性能binary不变才复用Builder正式数据；测试binary差异明确列出。修后未知失败或再需新增纠正立即硬停；不扩负载/阈值/SLO/预算，不开始S2。

路线原生WSL/bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway，Leader v0.4-s1独立临时/缓存及显式环境，socket/LSan首次窄升级。仅只读规划与文档，未执行诊断/实现/负载。根状态同步4/4诊断优先，保护/链接/diff与身份见Leader evidence/rework-004-check.log、rework-004-identity.json。交Builder后停止修改；最终协调者提交不推送。
