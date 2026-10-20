# V0.3/S2 Builder 实现报告001

2026-10-20，Builder (Hephaestus)。初次实现及自检完成，Ready for independent review，累计返工0/2。自测通过不替代独立验收；未提交、未推送，提交由协调者负责。

## 依据、范围与交付

依据[Approved设计](../../../leader/designs/V0.3/S2-design.md)、[审查计划](../../../reviewer/reviews/V0.3/S2-review.md)、[Leader001](../../../leader/reports/V0.3/S2-report-001.md)。三份SHA分别为002b00cdb5501d1e86326e02160dc9eaf785e4b11ed56fd116174a8c3078ded3、a3adaec952fcf85c4942827af108354784f3c063a3476ad3c5afd51e4b60f8c7、c3927110ba03c6cac6136f6d123cc394320923adc5be590652bd3ed2da8f7230，最终逐字核对一致。

分支codex/v0.3-s2-admission-queue，起点b704df268e2865bda146ba4c816dd105e6c8302c。无项目专用Builder指南，回退plan-project-docs Builder模板；沿agent-execution-route与personal-cpp-standards完整规则/正反例。初始Leader规划改动保留；旧报告/Approved/第三方/旧测试断言不变。来源与职责见[changes](../../../references/V0.3-S2-changes.md)，实施见[拆解](../../breakdowns/V0.3/S2-breakdown.md)，使用说明见README新增S2节和config/admission-example.json。

已实现显式opt-in配置、Router唯一inflight的全局与每实例限额、每模型count/逻辑byte有界FIFO、Waiting原请求所有权、取消/期限/健康重查、Runtime有界合并调度和停止。未引入依赖、重试、主动探针、优先级、管理接口；未做S3、P1诊断/旧soak、模型下载或性能优化。

## 实现边界

AdmissionController只保存稳定ID和charge，deque成功分配后才改账；Session保有唯一请求正文及原16MiB预约，等待无RequestLease/ConnectionLease/streamCapacity。Router按当前健康与限额检查，只有真正选择才推进游标、占Trial及递增唯一inflight；global为全部实例inflight和，没有第二份容量计数。

新请求有任何队列时也先排队。Runtime按持久模型游标查看队头，每轮每模型至多一次，每次最多32个处理；没有进展不自唤醒，仍可进展才投一个合并task。调度guard防重入，回调只转发具名方法，weak有效期token在Runtime析构首部失效；任务不能访问已销毁Runtime。Runtime是产品唯一task生产者，意外投递拒绝按致命调度错误处理，不静默丢通知。Session释放只标dirty，清理点再调度。

Waiting在派发前检查原total与queue期限，等号也过期、相等时total优先；停止/取消/超时/派发恰一次退账。完整请求后SHUT_WR保留等待，RST/明确socket错误取消。出队按当前健康/LI负载选一次目标，池满503/upstream_capacity中立释放、不重排。未启用admission时保留原分阶段时钟路径；旧S1/legacy断言均未改。

## 实际路线与命令

原生WSL、/bin/bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway。E表示build-local/builder/v0.3-s2/evidence，角色tmp/cache/debug/release/asan独立。构建、Python与测试显式设置：

```bash
export TMPDIR="$PWD/build-local/builder/v0.3-s2/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.3-s2/cache"
export PYTHONPYCACHEPREFIX="$XDG_CACHE_HOME/pycache"
cmake --preset debug -B build-local/builder/v0.3-s2/debug
cmake --build build-local/builder/v0.3-s2/debug -j4
ctest --test-dir build-local/builder/v0.3-s2/debug --output-on-failure
```

release/asan逐套替换执行。所有socket/LSan测试首次用精准宿主权限路线，不关闭ASan/UBSan/LSan。最终仅Admission变更后，实际三套分别执行`ctest --test-dir build-local/builder/v0.3-s2/<preset> -R '^Admission$' --output-on-failure`。

| 实跑 | 结果 / exit | 原始证据 |
| --- | --- | --- |
| Debug完整CTest | 19/19，34.14s，0 | E/ctest-debug-final.log、last-test-debug-final.log |
| Release完整CTest | 19/19，31.41s，0 | E/ctest-release-final.log、last-test-release-final.log |
| ASan首次完整 | 18/19，Admission测试时钟前提失败，49.57s，8；保留 | E/ctest-asan-final.log、last-test-asan-initial-failure.log |
| ASan修正后完整 | 19/19，48.71s，0 | E/ctest-asan-fixed.log、last-test-asan-fixed.log |
| 最终Admission三套 | 各359断言，1/1，0；含最终FD基线 | E/ctest-{debug,release,asan}-fd-final.log、last-test-*-fd-final.log |
| AdmissionE2E负控 | 每套42检查，0 | 各完整套LastTest证据 |
| 固定混合Release一次 | 24/24成功、68检查，0，0.851s | E/mixed-release-001.json、mixed-release-001.log |
| 格式/语法/差异 | 12 C++文件dry-run、py_compile、diff --check均0 | E/format-final.log、diff-check-final.log |

三套完整回归后，只修正/补充`tests/AdmissionTests.cpp`中的测试前提及显式AC断言；每次三套构建日志都仅重编译/链接AdmissionTests（build-*-fixture-fix/ac-final/fd-final.log）。最终三个AdmissionTests已实际复测，不复用旧Admission通过结果。其他产品、库、测试host与旧测试源码没有变化，故复用完整套的另外18项；ASan修正后完整套也实际再跑。mixed之后不改产品/host/混合脚本，不重复混合凑结果。混合host失败时保留原始客户端尝试的脚本取证分支在mixed之前补齐；此分支不属于此前完整套负控执行路径。

## 自检失败与修正记录

1. 首次Admission测试fixture把已有平铺listen配置写成嵌套对象，失败unknown config key；修正测试为真实配置，不改产品，E/admission-initial.log与admission-02.log保留。
2. ASan首次完整套在40个FakeIo fixture建立时间超过10ms后，Runtime真实时钟预检认为健康冷却结束，冻结FakeIo仍认为摘除，导致`admissionTaskPending_`断言失败。此用例只测32预算/停止，不测恢复；将该用例冷却设置为300000ms，长于CTest120s护栏，移除混合时钟前提。产品时钟与算法未改。ASan修正后完整19/19与最终359断言都通过。
3. 最终逐AC自查补足真正三项队列的中间取消、排队后LI负载变化、恢复Trial再取消中立、全测试退出FD基线。原有间接覆盖不能替代这些明确断言；新增后重编译并运行三个Admission目标，不把进度描述当证据。
4. 类方法外移辅助脚本首次正则未识别override而退出；源码未受损，修正脚本后外移成功并编译。该编辑工具错误不是测试失败或Reviewer返工。

## 逐AC实际证据

| AC | 实际函数/断言与说明 |
| --- | --- |
| 01 配置 | AdmissionTests::configChecks：默认/省略、各字段bool/float/负数/overflow、未知/重复/legacy、上下界、直接构造非法限额拒绝。所有旧17项CTest保持原断言 |
| 02 容量 | limitChecks：双模型四实例global2/per1、逐实例≤1、多次容量失败不推进游标、不占Trial。lifecycleChecks：独立ConnectionLease占满选中池时503中立/不重排/无连接尝试；S1 completionChecks保留下游lease而请求inflight已0的原断言继续运行；mixed观测global峰2、单实例峰1 |
| 03 队列 | queueChecks：count/byte恰等于上限、超1、单请求过大、两种0等待、charge精确值。middleCancellationChecks：三项中间取消及队首出队后的FIFO/账。allocationChecks：实际operator new注入deque分配失败，count/byte不变。lifecycleChecks：无两类上游lease/streamCapacity、预约恰16MiB、正常派发/重复finish/取消/停止/超时退账 |
| 04 时间/健康 | lifecycleChecks：截止前1ms仍阻塞、等于queue/total不派发、相同期限total优先、接收已耗500ms不重置total；摘除后新选实例、全部不可用503；排队后LI按当前负载选1号实例；恢复Trial派发后取消回Ejected且inflight0。limitChecks及原Routing健康/旧epoch断言保留 |
| 05 事件/停止 | RuntimeTestAccess::fairnessChecks：阻塞a不挡b、取消a队首后下一个获容量；budgetChecks(false/true)：40等待、首调用32后剩8、单任务续轮/停止、不忙转、无误发，最终队列/bytes/inflight/预约/timer归零；main显式整个Admission执行FD回入口基线。socket负控验证真实SHUT_WR响应、RST退账、释放后无人为新请求即派发、queue timeout和活动流+等待者停机 |
| 06 交付 | 三预设完整套与变更目标实际复测、下面固定混合原样本、最终SHA/保护审计、格式人工复核。无独立Reviewer结论冒领 |

## 固定混合原始观察

实际命令：

```bash
python3 tests/admission/RunAdmission.py \
  build-local/builder/v0.3-s2/release/AdmissionRuntimeHost \
  --mixed build-local/builder/v0.3-s2/evidence/mixed-release-001.json
```

仅一次，24条=每模型12条，模型交替发送、统一门闩；各模型第1/5/9条为200ms目标长流，其余10ms目标短请求。global2/per1、queue16/4MiB、queue5000ms、total10000ms、session64/预约1GiB。所有24个客户端尝试和host按稳定Session ID记录的五时刻完整保留；排队顺序来自真实enqueued时间，按模型与dispatched排序一致，不以客户端线程编号证明FIFO。

| 模型/请求 | 完成 | 排队/未排队 | 等待median/max ms |
| --- | --- | --- | --- |
| a/短 | 9 | 9/0 | 486.078 / 773.762 |
| a/流 | 3 | 2/1 | 412.150 / 550.579 |
| b/短 | 9 | 9/0 | 486.188 / 774.555 |
| b/流 | 3 | 2/1 | 412.069 / 550.306 |

全部0超时/拒绝/取消。聚合queue峰22/26286bytes，每模型峰11/13143bytes；inflight峰2、单实例峰1，终态queue/bytes/inflight/session/reserved/timer均0。未排队2条单列，没有填0冒充缺失等待数据。目标sleep不是精确服务时长，观察host含写盘开销；短请求受同模型FIFO头阻塞，跨模型轮转不保证墙钟公平。此有限成功样本不能证明长期无饥饿、开放负载SLO或性能收益。负控分母不混入24条。

## 格式、身份与保护

实际clang-format-18版本Ubuntu18.1.3，执行`-i`及`--dry-run --Werror`覆盖12文件：src/admission/AdmissionController.{h,cpp}、src/app/GatewayConfig.{h,cpp}、src/routing/ModelRouter.{h,cpp}、src/gateway/{ProxySession,GatewayRuntime}.{h,cpp}、tests/AdmissionTests.cpp、tests/admission/RuntimeHost.cpp。人工逐个检查相邻函数定义（含测试类内）、构造/接口/成员职责组；非简单测试类内方法已外移，短回调只转发具名函数，无嵌套lambda。没有全仓格式化或修改.clang-format。

- E/source-final-sha256.json：94文件，SHA256 `febfcc184489b3efe49870b91d658715e46c6f52eebe764e5c2ac69b76396c7f`，沿S1源集合加本次6个新源/配置/脚本。
- E/binaries-final-sha256.json：三预设共45个ELF/静态库，SHA256 `1629632117f7240f40ee84268374e50d14d90169f3c9f5c79c76f33112984f7d`，逐路径列完整SHA，包含最终Admission与mixed实际使用的Release host。
- E/protected-identity.json：137个已有docs/third_party/tests/config/格式/预设文件与HEAD逐字一致，SHA256 `47f36c8f1689404c4f8f39c119e1c23cc6a7d637f5c5a654948868cdf08e3f7e`；当前Approved三件套另列E/authority-sha256.json。
- E/mixed-release-001.json SHA256 `f88689c2d93d4bbf64e42c884003178bd750c9cab04d5bc775c0db783f4067c1`。早期失败日志均保留，未覆盖为成功。

无已知未解决功能问题/新增债务；固定负载与协议健康的边界如上。Builder所有自有构建/测试/host/后端进程已结束，等待独立Reviewer；不提交、不推送，不宣布V0.3整体完成。
