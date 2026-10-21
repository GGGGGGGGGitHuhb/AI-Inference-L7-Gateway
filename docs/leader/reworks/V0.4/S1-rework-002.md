# V0.4/S1 返工002：背压测试迟滞契约与诊断

2026-10-20，**Approved / 待实现**，最后统一返工**2/2**。[Reviewer001 FAIL](../../../reviewer/reports/V0.4/S1-report-001.md) F-001触发，用户阶段启动/技术委托及协调者明确旧测试例外授权本范围。原设计、审查、返工001与所有报告原字节保持；本次Leader→Builder→Reviewer是一轮2/2，不另计或重置。

## 1. 事实和证据边界

独立Debug/ASan各21/21，Release首次20/21，BackpressureTests.cpp原292行联合token==0和pending>=32768失败，定位为testSlowReader(1,false,stopMode=1)第一次pause预置。失败尚在SIGTERM前。一次授权同binary诊断979检查通过，但原日志没有token/pending值，**不能认定原失败是哪一子条件，也不能认定产品无错或已复现根因**。

源码显示acceptStreamResult在未完成HTTP且pending>=high触发pause，随后同一次poll中的下游事件可writeStream减少pending；paused直到pending<=low才恢复。high32768/low8192下，paused且8192<pending<32768是合法状态。该代码证据证明旧断言对观察时点过强的可能性，不证明首次失败实际经过此路径。产品及旧测试未变SHA不能豁免实际失败。

## 2. 允许范围与保持的保障

仅允许必要修改`tests/BackpressureTests.cpp`的测试观察、诊断及不变量；可在已有`tests/RuntimeTests.cpp` FakeIo设施新增确定性迟滞用例，或在Backpressure文件内用现有SessionIo接口建立最小夹具。无产品修改、无公开接口、无修改水位/期限/缓冲/socket参数，不删除既有暂停期间不读、旧token无效、新token恢复、正文一致、取消/停止/排空检查，不改发压工具/固定矩阵。

socket场景每轮首次观测paused必须分拆并输出framing/reset/stopMode/cycle、paused、token、pending、high/low、pause/resume累计值和上游读调用/字节数，再分别检查，失败日志不能只有联合表达式。对“未完成且仍活动的已暂停流”检查paused=true、token=0、pending>low且不超过StreamOutput容量。不要将pending>=high简单换成无说明的较低数值；必须有下面的触发证据与确定性机制测试共同保证high门槛。

**真实pause触发证据**：在测试观察周期确认pause计数相对该cycle前增加，并保留该session本次高水触发的证据。可采用测试专用SessionIo受控收发、现有只读friend观察上游可读处理返回但尚未处理下游写的状态；不直接赋值paused、pending或计数制造暂停。如果只用runtime全局peakPending，必须证明该阶段仅本session贡献且基线已分离，不能用此前fast请求/预热峰值当本次触发。每次真实pause依然要求上游token注销、不再recv及恢复新token；不降低两轮pause/resume及三种HTTP定界原覆盖。

## 3. 确定性迟滞用例

利用现有FakeIo/SessionIo发送限额与EAGAIN脚本，通过实际协议解析/acceptStreamResult/writeStream路径构造未完成的流，不直接改产品私有状态：

1. 下游写暂时阻塞，输入足量但未完整HTTP的真实流片段，明确观察pending>=32768、pause次数增1、paused=true、token=0，记录触发前后状态。
2. 保持未新增上游输入，允许下游准确发送至预选中间水位（例如16384），随后EAGAIN。执行上游读事件后紧接下游写事件的顺序，代表同轮poll可发生的合法事件序列；观察8192<pending<32768且paused/token0，读次数/字节不增加。明确这是确定性状态迁移证据，不冒充首次Release失败现场重现。
3. 继续受控发送至low+1，仍暂停；再到恰好low，真实resume发生，paused=false、新token非零且不等旧token、resume次数增加。未跨low不得提前恢复，等于low必须恢复。
4. 旧token触发不得读，恢复token才可读；完成剩余合法正文并核对无丢/重字节及资源归零。原异常/停止场景仍执行。

新测试断言需能拒绝token未注销、没有high触发、在low+1提前resume、到low未resume等错误。可以将观测不变量判定作为测试纯函数，提供非法快照负控；不能为了负控改产品，也不能仅测试手工状态代替上述真实方法调用。所有新C++按个人规则/clang-format与人工相邻函数/回调检查。

## 4. 有限验证与复用

Builder完成一次实现批次后，三个预设各执行一次定向Backpressure/新增迟滞测试，然后三个预设各一次完整CTest；定向用于检查新增机制，完整用于回归，不能无限循环等通过。保留初次Release失败和原979诊断日志。若定向或完整出现未解释失败，立即停止交协调者；不得继续尝试直到通过或进入未经批准的第三轮。编译错误也保存，常规同轮构建修正不得扩大语义范围。

Reviewer独立审查测试为何准确覆盖迟滞、非法状态拒绝及实际pause证据，然后独立三个预设各一次完整CTest（含新增机制），全部通过后才启动原完整57cell/7590ID与独立复算。Reviewer首次正式矩阵尚未执行，不可用Builder数据替代。独立检视原失败仍标FAIL，最后报告明确“原子条件未记录，首次根因不能回溯确认；已纠正过强观察断言并独立验证产品迟滞契约”，不能改写成已确诊环境抖动。

Builder已完成的正式性能run若产品、发压、矩阵、配置、测量host及其binary SHA保持，可复用，**不因测试限定修改强制重新压测**。保存修改前后源清单与产物清单，受影响测试binary变化逐项列明；不得说所有产物未变。新三套全回归重新执行，旧失败不被“复用”洗掉。若任何产品/发压/计量变化或发现产品缺陷，停止报告影响，由协调者裁决，不利用本文件自行扩大范围。

## 5. 接受与停止边界

F-001只有在精确测试契约、真实high触发、确定性中间迟滞/low边界、失败分支诊断和双方完整回归证据齐备后由Reviewer关闭；原阶段所有AC、预算与性能矩阵仍须满足。未知token异常不得当过强pending断言解释。无第三轮自动返工；再有阻断即硬停交协调者，不降级债务或降低门槛。

执行路线保持nativeWSL `/bin/bash` login=false，仓库原生路径，角色v0.4-s1独立tmp/cache/evidence与显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；socket/LSan首次窄升级。Leader只规划不执行上述测试。完成后本地提交不推送，S2优化不启动。
