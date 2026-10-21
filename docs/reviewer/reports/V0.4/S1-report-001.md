# V0.4/S1 独立审查报告001

2026-10-20，Reviewer（Athena）。**FAIL；当前累计统一返工1/2。F-001（Major）为未解释的独立Release回归失败，不能用一次诊断通过消除。** 三套独立构建完成；Debug/ASan完整通过，Release20/21。按协调者指令完成已启动的独立短控后停止；正式57cell尚未启动，不存在Reviewer性能接受结论。若需修改旧测试，必须先由Leader批准最后返工范围，Reviewer没有自行修复或反复复测。

## 权威与执行路线

依据[Approved设计](../../../leader/designs/V0.4/S1-design.md)、[审查计划](../../reviews/V0.4/S1-review.md)、[返工001](../../../leader/reworks/V0.4/S1-rework-001.md)、[Leader002](../../../leader/reports/V0.4/S1-report-002.md)、[Builder001](../../../builder/reports/V0.4/S1-report-001.md)。旧V0.3/S3的2/2不转移至本阶段。分支`codex/v0.4-s1-performance-baseline`、HEAD`44266088f5d93880983eb58a27117b796af7075b`。

重新读取agent-execution-route，复用已读取的personal-cpp-standards完整规则/正反例和plan-project-docs Reviewer模板；无项目专用Reviewer指南，继续全局模板回退。原生WSL、`/bin/bash login=false`、cwd=`/home/power/projects/AI-Inference-L7-Gateway`，独立目录`build-local/reviewer/v0.4-s1/{tmp,cache,evidence,debug,release,asan}`。Python/构建/测试显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；socket/LSan/prlimit按已知边界首次窄权限执行，没有禁检测器/下载/调系统或重跑P1/旧长soak。

以下E为`build-local/reviewer/v0.4-s1/evidence`。本次只写独立证据和新Reviewer报告，未改实现、测试、Builder文档、Approved或根文件，无提交/推送。

## 独立执行及首次失败

三套实际执行`cmake --preset MODE -B build-local/reviewer/v0.4-s1/MODE`与`cmake --build build-local/reviewer/v0.4-s1/MODE -j4`，均退出0。测试命令为`ctest --test-dir build-local/reviewer/v0.4-s1/MODE --output-on-failure`。

| 检查 | 原始结果 | 证据 |
| --- | --- | --- |
| Debug完整CTest | 21/21，46.25s，退出0 | E/ctest-debug.log、last-test-debug.log |
| Release完整CTest首次 | 20/21，Backpressure失败，CTest非零，其余20项通过 | E/ctest-release.log、last-test-release-failed.log |
| ASan+UBSan完整CTest | 21/21，75.22s，退出0 | E/ctest-asan.log、last-test-asan.log |
| 一次同Release binary窄诊断 | 979检查，退出0，1.02s；不能覆盖上行失败 | E/backpressure-diagnostic-001.log |
| 独立持久ExperimentDetectors | 退出0；包含预算、分类/时钟/SLO/分位、端口复用、host背压、双客户端中断和晚到future | E/detectors-001/、detectors-001.log |
| Reviewer独立追加控制 | 迟到整批未发、部分200坏尾、双进程累计预算与失败记录、同formal真实端口复用及歧义拒绝均通过 | E/IndependentChecks.py、independent-controls.json、independent-controls.log |
| 新C++格式与人工 | `clang-format-18 --dry-run --Werror tests/experiments/RuntimeHost.cpp`退出0；函数/类内定义空行、职责分组、具名短回调/寿命人工复核 | E/format.log |
| 身份与保护 | 118源、51独立产物、214个HEAD保护文件核验；git diff --check通过 | E/Identity.py、identity.json及三清单 |

持久短控命令：`python3 tests/experiments/DetectorTests.py build-local/reviewer/v0.4-s1/release/ExperimentRuntimeHost --output build-local/reviewer/v0.4-s1/evidence/detectors-001`。追加命令：`python3 build-local/reviewer/v0.4-s1/evidence/IndependentChecks.py`。同binary窄诊断由协调者在首次失败后明确授权，仅一次：`/usr/bin/time -f 'exit=%x elapsed=%e' build-local/reviewer/v0.4-s1/release/BackpressureTests`，新日志保留，未重建/改源码/覆盖首次日志。

## F-001：旧Backpressure测试在独立Release首次失败（Major，未关闭）

首次Release CTest中Backpressure用时0.66s并非零。原始错误为：

```text
Access::token(*session) == 0 && Access::pending(*session) >= config.streamBuffer.highWaterBytes at line 292
```

由main固定顺序和前面六个场景日志可定位为`testSlowReader(1, false, stopMode=1)`第一次暂停后的预置断言：此前三种framing两轮普通慢读及三种framing的RST场景均已走过；当前是chunked优雅停止场景，尚未执行SIGTERM。不是首content超时或正式性能cell失败。早期进度消息中的“首content超时”定位已纠正，以本报告及原始日志为准。

测试先调用`runtime.pollOnce(1)`直到`Access::paused`为真，然后第292行同时要求token=0与pending≥highWater。配置high=32768、low=8192。源码证据：

- `src/gateway/ProxySession.cpp:645` pauseUpstream设置paused、暂停上游事件；`acceptStreamResult`在pending达到high时触发它。
- `src/gateway/ProxySession.cpp:724` writeStream可在下游可写时继续减少pending；仅当pending≤low才resume。因高低水滞回，paused且low<pending<high是允许状态。
- EventLoop一次poll可分派多个就绪事件；因此“观察到paused后，pending仍必≥high”不由产品状态机保证。它可能使第292行成为受事件顺序影响的过强测试断言。

**这是代码支持的候选解释，不是已经证实的首次失败根因。** 联合断言没有打印token/pending具体值，首次日志只有framing/缓冲/内存诊断；无法排除是token非零或其他异常。一次同binary复现成功只能说明未稳定复现，不能确证产品契约通过，不能将首次结果标为测试环境噪声或自动接受为债。

产品及测试源码未发生本阶段修改：BackpressureTests.cpp、ProxySession.cpp、ConnectionPool.cpp、EventLoop.cpp与Reviewer的V0.3/S3原清单逐字SHA相同，见E/regression-identity-and-processes.json。未变身份不足以豁免本次实际失败。相应SHA：

- BackpressureTests.cpp：253513200cb8f92e6a6d15b67549ada1d8b742bf08df36636510d8bcd12dd9a1。
- ProxySession.cpp：2f8905670aaa2cedc99cadc35c63c3e9a903ec84b25183ee22f1e2b15243bccf。
- 本次Release BackpressureTests：8c1548d7e6f1f98a7d6bb6a9421ef1cf55e22772c0bd5c53373ae62b90513530。

交Leader/协调者统一裁决最后返工。建议先限定诊断与测试契约澄清，保留token注销、不再读上游、恢复/排空等实质检查，不能直接删除断言或把high换low后宣称根因已证实；需要实际记录失败分支，并以确定性证据验证合法滞回状态及非法状态拒绝。若涉及旧测试保护例外，需Leader明确批准；若发现产品缺陷则按实际影响范围单独评估，不能借本报告授权修改产品。当前1/2不自行重置或推进，且不允许Reviewer自行循环复测择优。

## 已完成源码审查与追加控制

完整阅读Plan、Client/Worker、Budget、Infrastructure、Backend、RuntimeHost、RunExperiments、Statistics/Analyze、Association/AssociationTests及DetectorTests，核对57cell含三重复、7590计划ID、固定SLO/交错顺序、H/Q原点scheduled和闭环屏障分母、成功分位门槛与到达限制裁决。开环线程不等HTTP完成补发；SLO与发送后时延分开。正式R使用官方程序，逐实例generation task集合0→1→7为聚合观察，不能推断P逐ID目标。

新1GiB三池隔离于旧MVP，父进程唯一受管写入者；子进程通过≤8KiB帧/256队列IPC回传，host逐ID≤16事件且≤1KiB，state≤4KiB，直接路径预留512KiB/内核硬限/core0。父finally对未回传ID按是否启动/到计划时刻分别保留interrupted/not_sent/not_started；正式全run未开始ID索引不伪装已发送。检查异常/超时、晚到future传播和所有自有进程清理路径。以上静态及短控审查不能替代未执行的完整矩阵/运行预算证据。

Reviewer追加独立源码未调用Builder summary：

1. 调用实际Worker.run_batch安排7条已迟到超过50ms的开环计划，全部not_sent/dispatch_late、无send/补发；端口1未接触。
2. 自有socket服务先发合法200和首content，再发非法chunk尺寸；实际Client记录protocol_failure、http_valid=false、有首content，不能算success/SLO。
3. 两个自有进程各声明直接文件后，受管2048bytes池连续1200+1200写入触限，子驱动非零退出8；两个进程回收，Cell.finish_records通过错误池保留原protocol_failure记录，总实际文件量未越预算。
4. 独立真实loopback两条同formal连接复用同源端口，以不同响应标记确认实际通信；将两侧输入逆序仍唯一映射Session20/21，再制造host区间重叠明确拒绝。没有仅伪造端口来冒充实际复用。

持久检测器和追加控制的7组进程记录共19个PID，start/reaped匹配、/proc均不存在；正式模型未启动。CTest本身完成退出。E/Audit.py为已编写但**尚未执行**的独立正式数据复算脚本，因正式run未启动，不能把它列作已完成的性能审计。

## AC状态、身份与停止交接

AC01/AC05的完整回归门槛未满足；AC02–AC04的57cell性能/资产运行/到达有效对/背压正式增量/完整资源复算均未执行。本报告不给Reviewer57cell表、不引用Builder结果冒充独立数据、不作策略收益或容量结论。正式矩阵维持未启动，待统一纠正及必要回归通过后，仍须按Approved执行完整57cell一次及独立复算。

权威SHA保存在E/identity.json，均与交接一致。独立源清单SHA为5d76c88a6aaa5de4d66227d21fac16e123f583e4ce64ea58fb28a974f55a456d；51产物清单SHA为3c1105dfc1fbfeb9258882e56a55da3a60d5db6e64f41ed67702cfbfa278a9fb；214保护项清单SHA为6a5cb35a5e61534a76e1668b8fcc9117ce87177e00979ff67ae79baf20699f49。保护范围是HEAD全部已跟踪文件除允许改动的CMake及三根状态文档；比Builder212项更广，不是遗漏历史文件。

**最终FAIL，F-001保持未关闭，当前1/2，无自行接受债。** 已按协调者要求停止，所有已启动独立项结束，不继续诊断/复测/正式负载，不修改产品或旧测试。交Leader决定最后统一返工范围和复验要求；不启动S2、不提交推送。
