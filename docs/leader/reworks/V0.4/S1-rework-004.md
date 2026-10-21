# V0.4/S1 返工004：资源所有权与生命周期诊断优先

2026-10-20，**Approved / 分阶段执行**，累计**4/4**（本次新增1/1）。用户新增明确授权：“允许再进行一轮有限返工，先把四项资源值和对象生命周期查清楚，再针对原因修复”。恢复[Stop002](../../reports/V0.4/S1-stop-002.md)后的阶段，历史3轮与所有Stop/FAIL保持。不允许第五轮自动纠正。本轮先诊断、回报证据，再按下述分支限定修复，不能先猜原因改断言。

## 1. 当前事实与只读候选

返工003首次Debug定向，Backpressure通过；Runtime正确流模式三次消费完成全wire32940、decoded32769与精确正文，随后reserved/streamCapacity/pending/paused全零联合断言失败。四项值未打印，原因未证实；日志targeted-debug-rework003.log及Stop002保持。原Release背压联合断言现场子值也仍不能回溯。

源码显示SessionFixture::checkCleanup只验证session finished、无上游、timerCount0，不销毁unique_ptr session。ProxySession::finishSession释放流容量/pending/paused、timer/channel/upstream/socket；reservation_成员CapacityLease由析构释放，析构本身再次幂等finishSession。Fixture字段保证session先于pool/loop/budget销毁。因此“已finished但对象仍存活，session reserved仍持有16MiB”是可验证候选，不是四项实测结果，也不等于已确认无泄漏。

## 2. A阶段：一次只加诊断的运行

仅在新增testStreamingHysteresis及最小测试friend观察中增加有界分项日志，不改原断言、产品、配置、时序阈值、正文或正常清理逻辑。允许**一次Debug Runtime定向诊断运行**，本次预期原断言失败是取证，不算本轮修复失败；保存新日志与退出码，不覆盖旧日志。诊断前不要求故意重复原未打印的失败。

必须记录下列时点：完成剩余上游输入前；flushClient后；checkCleanup后/正文校验后；原资源断言前；异常离开fixture作用域时的session析构前和析构后。每点输出reserved、streamCapacity、pending、paused四项独立数值，以及session是否存在/finished、reservation有效性、stream lease有效性、上游连接lease有效性/hasUpstream、token、timerCount、pool leased/total及阶段标签；析构后禁止解引用session，session字段标不存在，继续读取仍存活的budget/loop/pool。

测试专用诊断守卫或局部嵌套作用域可在异常展开中记录析构前后，但必须保留原失败传播/非零退出。不得在原断言前reset session，不得提前释放reservation或忽略异常伪造归零。守卫的对象存活顺序需明确：budget/loop/pool在后置快照时仍有效，session自然析构发生一次。若诊断需要显式销毁动作，仅允许在原断言失败已记录后的诊断清理阶段等价于原作用域退出，并标明该动作；不能把这算原断言通过。

同时只读审计新增用例全部资源断言/非法快照负控：逐项列owner、正常释放点、验证时点、对象是否存活、预期值及证据。不要等修完一项再撞下一个联合断言。诊断结束先向协调者/Leader回报四项实值、析构前后、源码对应关系、进程退出和建议范围；**回报之前不得开始修复**。

## 3. B阶段：按证据限定修复

若诊断证明仅session预约因对象尚存活而非零、其他流资源在finished时已释放且析构后全部归零，可在测试中一次统一区分两层保障：

- finished且session仍存活：明确session reservation恰为本fixture应持有额度（单独budget为16MiB），流容量/pending/paused全零，timer/token/上游lease归零；保留正文与迟滞检查，逐项断言并打印实际值。
- session正常销毁后、budget/loop/pool仍存活：所有对应资源归初始基线，session reservation恰一次释放，pool/FD按真实ownership检查。销毁安排在完整finished/正文/流资源检查之后，通过作用域或明确测试清理，不能提前reset掩盖终态泄漏。

仅修Runtime新增用例生命周期布局/断言和必要诊断；Backpressure真实high触发及既有新迟滞、parser校验、旧测试/产品保障不削减。不改变共用Fixture默认语义影响其他用例；如需最小局部辅助，明确只服务该用例。已有相关测试对reservation在session.reset前后检查可作参考，不据相似代码替代实测。

若任何流资源在finished时仍非零、析构后预约不归基线、token/timer/lease异常，或观察与候选不符：先报告实际证据、最小可能产品/测试修复及性能复验影响，停止依赖工作。**本文件不预先授权产品修复**；不得猜测为泄漏或直接改finishSession释放时机。需要超出本轮限定方案或新增纠正时硬停交用户/协调者，无第五轮自动修复。

## 4. C阶段：有限复验与接受

依据A阶段证据确认B范围后，Builder一个统一修复批次，三套各一次Backpressure/Runtime定向及各一次完整CTest；不循环择优。A阶段一次有日志的预期失败与C阶段修后验证明确分开；修后未知失败立即停止。保留所有旧联合失败与诊断，不把其历史改为已确诊或通过。

Reviewer独立审计资源ownership/时点和全部迟滞/正文保障，三套完整回归后原完整57cell/7590ID及独立审计。Builder既有正式run可仅在产品/发压/配置/计量host及性能binary SHA不变时复用；测试binary变化列明。若产品需变动，性能证据复用须重新裁定，不能预先承诺。

原AC、固定负载/SLO/预算保持。独立PASS后Leader同步文档关闭，协调者本地提交不推送；阶段目前未完成。路线nativeWSL/bash login=false，cwd原仓库；角色v0.4-s1独立tmp/cache/evidence及显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX，socket/LSan首次窄升级。只核对并回收本任务证据中的所属PID。Leader只读规划，不执行本诊断或实现。
