# V0.4/S1 Builder 有限返工报告002

2026-10-20，累计统一返工 **4/4**，本次用户新增额度1/1。依据Approved rework002/003/004及Leader003/004/005，承接Reviewer001 F-001。Builder001及所有Stop/FAIL/权威历史字节保持；本报告不关闭独立Reviewer问题、不宣称阶段接受。原生WSL `/bin/bash` login=false，cwd仓库根，证据E=`build-local/builder/v0.4-s1/evidence`，显式任务tmp/cache及TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；socket/LSan按已知边界窄提升，无禁检测器或下载。

## 修改范围和实际保障

只有 `tests/BackpressureTests.cpp` 与 `tests/RuntimeTests.cpp` 变动。共用Fixture默认语义、产品、阈值、socket参数、发压工具、性能host、矩阵与配置均未改；CMake没有本轮变化。旧测试保护的两项例外由rework002明确授权，其余保护不扩大。

Backpressure对每cycle调用真实上游事件处理，记录其返回时本session的triggerPending/token，再允许runtime poll处理下游，形成真实high触发证据，不能用此前fast请求全局峰替代。首次paused观察打印framing/reset/stopMode/cycle、paused/token/pending、high/low、triggerPending/triggerToken、pause/resume累计及recv调用/字节；分拆检查pause累计恰增1、触发pending≥high和token注销，poll后仍paused/token0且low<pending≤容量。允许合法迟滞中间状态。原三种HTTP定界、两轮pause/resume、暂停不读、旧token无效、新token恢复、快请求、RST/停止/正文/排空保障保留。

Runtime新增局部FakeIo用例走真实解析/acceptStreamResult/writeStream路径，未直接赋值pending/paused/计数。high实测32842，pause次数1/token0；精确写预算依次到16384、8193仍paused且recv次数/字节不变；再写1byte到8192恢复，新token非零且异于旧token，resumes增1。旧token事件不读，恢复token可读；剩余合法chunk响应完整。5个纯快照负控拒绝未注销token、无high触发、low+1提前恢复、恰low仍pause、没有pause计数。

SSE校验显式kAllowEventStream，每次≤16KiB wire输入，按consumedBytes严格正向推进并立即复制bodyFragment；最终kComplete、全wire消费、decodedTotal==累计正文长度、message().body空，正文精确32768个h加z，不调用finishInput伪造终态。局部默认buffered负控实际返回unsupported_stream；每片日志有status/errorStatus/errorCode/consumed/offset/wire/decoded/fragment。

## 历史失败与诊断优先过程

1. Reviewer001原Release Backpressure联合断言失败，没有token/pending子值，**首次根因不可回溯确认**。代码允许high触发后同轮下游写进入迟滞区间，只能说明原观察断言过强的候选路径；不能把原失败认定环境抖动或已复现。
2. rework002首次Debug定向：Backpressure通过，新Runtime末尾默认buffered一次性SSE校验失败；保留targeted-debug-rework002.log，退出8，立即停止，Release/ASan和全套未启动。旧2/2停止不改。
3. 用户新增一轮至3/3，rework003修流校验；首次Debug定向Backpressure通过，Runtime三次消费16384/16384/172完成wire32940/decoded32769和精确正文，随后新增四项资源全零断言失败。targeted-debug-rework003.log及targeted-last-debug-rework003.log保留，退出8，立即停止，未执行后续套。此前模式失败现场没有错误码，局部负控证明API契约，不伪称回溯现场。
4. 用户新增诊断优先一轮至4/4，rework004 A只加日志，一次Debug Runtime直接执行，退出1保留原资源失败。诊断前未reset session/修改断言。异常守卫只在原失败传播后等价清理session并记录前后；budget/loop/pool仍活着，析构后不解引用session。A结果已先回报协调者及Leader，协调者确认B范围后才修改。

A四项实值与完整owner数据见runtime-rework004-diagnostic.log / .exit及rework004-ownership-audit.md：

| 时点 | reserved | streamCapacity | pending | paused | 其他状态 |
| --- | --- | --- | --- | --- | --- |
| 剩余上游完成前 | 16777216 | 262144 | 8192 | 0 | session活跃，reservation/stream/upstream lease有效，token131/timer1/pool leased1 total1 |
| flush / checkCleanup / 正文后 / 失败析构前 | 16777216 | 0 | 0 | 0 | session存在且finished，reservation有效；stream/upstream lease、token/timer/pool均0 |
| 失败记录后session析构 | 0 | 0 | 0 | 0 | session不存在；budget/loop/pool仍活着，无token/timer/pool |

已证实本次资源断言时点错误：finishSession释放流、上下游和timer；session reservation_由CapacityLease成员析构归还，Fixture::checkCleanup不销毁session。不能要求仍活着的finished对象提前归还16MiB。这一结论仅针对本次有分项日志的新增资源失败，不追溯洗掉原Release失败。

B按实际所有权统一分两层：finished活对象reservation有效且reserved恰kSessionBytes，其余流资源/lease/token/timer/pool逐项0；完整正文与全部负控后正常销毁session，再逐项全0。FD比较fixture初始化值减1（session下游fd已关闭，peer/loop仍存活）；实测13→12。再次空reset不重复释放预约。共用Fixture及产品生命周期不改，诊断守卫仍仅在异常路径保留失败传播。

## 规范、身份与性能复用

已完整应用personal-cpp-standards规则及正反例。实际`clang-format-18 -i tests/BackpressureTests.cpp tests/RuntimeTests.cpp`，随后相同范围`--dry-run --Werror`退出0，版本18.1.3；证据format-rework004-final.log。人工逐相邻函数/类内定义空行、声明/成员职责分组、局部诊断守卫寿命及无复杂持久lambda检查完成。测试职责按snapshot/解析校验/资源诊断辅助划分；未格式化无关文件。

E/rework002-to004-exact.diff保留两源完整前后差异。E/source-builder002-sha256.json仍118项，仅两测试源变化；E/protected-builder002-sha256.json仍212项，仅批准的两测试变化，其余210保护项保持。E/binaries-builder002-sha256.json为51产物，**6项变化、45项不变**：debug/release/asan各自BackpressureTests与RuntimeTests变化，完整before/after SHA逐项见builder002-reuse-proof.json。不能说51产物均未变。

产品源、所有实验Python/C++host/配置及测量产物SHA不变，按Approved复用Builder原run-002完整57cell/7590ID性能证据，没有重新压测；原T/CPU受限标记与结论仍有效，不能外推容量/因果收益。原run-001工具失败、run-002原始文件、Builder001和Reviewer001/所有Stop/Approved均保护，最新交接identity给出逐项hash。Reviewer仍须独立三套与完整57cell，不能以Builder复用替代。

## 本轮实际验证与交接

编译三套均退出0，日志build-{debug,release,asan}-rework004-final.log。A阶段诊断与C阶段修后测试分开编号；没有以重复跑同用例等待成功替代修复。C阶段各套定向一次后各套完整一次，全部退出0：

| preset | 定向Backpressure/Runtime | 完整CTest | 完整套内检查计数 |
| --- | --- | --- | --- |
| Debug | 2/2，1.48s | 21/21，43.04s | Backpressure1150、Runtime1343 |
| Release | 2/2，1.30s | 21/21，39.39s | Backpressure1183、Runtime1343 |
| ASan+UBSan | 2/2，1.97s | 21/21，60.13s | Backpressure1099、Runtime1343 |

Backpressure检查总数随实际socket读写循环变化；固定场景/关键机制均执行，没有用检查总数比较性能。原始targeted-<preset>-rework004.log及targeted-last-<preset>-rework004.log，完整ctest-<preset>-rework004.log及last-<preset>-rework004.log均保留。实际完整套打印每cyclehigh/计数/token/recv，Runtime完整打印五负控通过与两层资源/FD。

可复现命令（均先设置上述显式env）：

```bash
cmake --build build-local/builder/v0.4-s1/<preset> -j4
ctest --test-dir build-local/builder/v0.4-s1/<preset> -R '^(Backpressure|Runtime)$' --output-on-failure
ctest --test-dir build-local/builder/v0.4-s1/<preset> --output-on-failure
```

A阶段仅一次`build-local/builder/v0.4-s1/debug/RuntimeTests`，非零1是保留原断言的诊断，不算PASS；全部后续修复遵循已回报且获确认的B范围。C退出0与原A退出1及前两轮CTest退出8独立保存。`git diff --check`最终退出0；已执行两受影响C++的真实格式化/dry-run与人工规范复核。

自有构建/CTest命令全部完成，原宿主只读进程审计无本角色路径残留，见processes-builder002-final.json；本轮未启动性能矩阵/模型。完整118源/51产物/212保护项及精确差异、所有Approved/旧报告/失败/性能原始数据保护结果在E/handoff-builder002-identity.json，包含本报告SHA。已完成Builder范围，**停止等待独立Reviewer**；F-001由Reviewer决定关闭，未提交、未推送，不启动S2。
