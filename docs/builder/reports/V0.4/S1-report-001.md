# V0.4/S1 Builder 实现报告001

2026-10-20。基于 Approved S1-design / S1-review / Leader001 及 Approved S1-rework-001 / Leader002；累计统一返工 **1/2**。本报告是首次正式 Builder 交付，不代替 Reviewer 独立接受。分支 codex/v0.4-s1-performance-baseline，起点 44266088f5d93880983eb58a27117b796af7075b；未提交、未推送。

## 实现与边界

新增 tests/experiments 固定性能工具：57 cell 已含三重复，7104 正式与 486 预热；独立发压进程、有界 IPC/摘要、增量 HTTP/SSE 校验、固定 SLO/到达、独立合成后端、链接原 runtime 的只读 host、有限资源采样、运行期分区日志预算、finally 全计划终态留存、原始数据复算。CMake 新增 ExperimentRuntimeHost 和 ExperimentDetectors；无产品、旧 P1/MVP、第三方及历史 Approved 修改。文件职责见 docs/references/V0.4-S1-changes.md，命令与限制见 tests/experiments/README.md。

无项目 Builder 指南，使用 plan-project-docs Builder 模板回退；沿 agent-execution-route 原生 WSL /bin/bash login=false。目录 build-local/builder/v0.4-s1/{tmp,cache,evidence,debug,release,asan}；所有执行显式 TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX。socket/LSan 使用窄提升，不关闭检测、不下载、不跑旧 P1/长 soak。

## 自检、正式失败与统一返工

初次短控 detectors-initial.log 揭示只读 host 在 idle 时没有持续输出新资源采样，修为每轮 poll 后采样；host-fixed / complete-001 / complete-002 均通过。此为首次交付前自检，旧失败日志保留。正式前增加 B 必须证明 formal 增量 pause/resume、每 cell 绝对 alarm 护栏及 RR→LI 配对方向，随后三套相关检测器各通过。

run-001 退出 1：完成 13/57 cell，第14个 13-H-0-LI 后置审计报 client/host association ambiguous。warmup-000 与 formal-118 实际复用源端口40074，相隔约7.16秒；host Session1/129 及两条请求均完整，但旧工具错误把端口当整个 cell 的永久唯一身份。130/130 原始记录保留；全 run 2192 attempt + 5398 not_started =7590 唯一ID，55start/55reaped且原执行环境无残留。该 run 是工具验证失败，不能作为有效负面性能结果、不能拼入新正式结果。

按 Approved rework001（累计1/2）仅父端后置审计增加 Association.py：同 cell/同 host 生命周期/固定 IPv4 loopback 四元组内，以客户端 connect 和 host accepted 各自排序；双方时间存在、终态顺序、非重叠、唯一排序、基数相等及全消费验证；不跨进程相减计算指标。未发/未开始/未建立显式分类，额外 host 拒绝。queue wait 与 backend 仍取唯一匹配的同一 Session。未改产品、C++host、Client、Worker、Plan、Backend、时序/端口策略或任何已编译产物。

AssociationTests 真实 loopback 绑定同源端口连续三连接，覆盖 warmup→formal→formal，返回不同可核查标记；独立拒绝计数差、双侧重叠/相同排序/缺时钟/逆序、重复 client/host、额外 host、外来 cell/监听、非 loopback 和未发带连接。原失败130条另目录离线关联成功，40074分别唯一对应Session1/129；原FAIL目录与数据不变。精确diff的旧版逆向恢复内容SHA与冻结manifest吻合。

## 实际回归与规范

证据根 E=build-local/builder/v0.4-s1/evidence。

| 执行 | 结果 | 原始证据 |
| --- | --- | --- |
| 三预设 configure/build | 各退出0 | configure-*-final.log / build-*-final.log |
| Debug 全 CTest | 21/21，41.39s | ctest-debug-final.log / LastTest-debug-final.log |
| Release 全 CTest | 21/21，39.50s | ctest-release-final.log / LastTest-release-final.log |
| ASan 全 CTest | 21/21，58.14s | ctest-asan-final.log / LastTest-asan-final.log |
| formal guards 相关检测器 | 三套各1/1 | ctest-*-final-guards.log |
| 返工后相关检测器 | Debug1/1 7.28s，Release1/1 7.25s，ASan1/1 10.13s | ctest-*-rework-001.log |
| 持久实际端口复用与完整短控 | 退出0 | detectors-rework-001.log / detector-proof-rework-001/ |
| 原失败cell离线 | 130/130映射 | rework-001-offline/mapping.json |

复现构建命令：`cmake --preset <debug|release|asan> -B build-local/builder/v0.4-s1/<preset>`，`cmake --build <dir> -j4`，`ctest --test-dir <dir> --output-on-failure`；返工相关运行增加 `-R ExperimentDetectors`。精确工具命令见README。完整三套21/21对应冻结产物；返工仅两个既有Python文件及两个新Python模块，三套最终关联检测器实跑；其余20项按未变源码/51产物身份复用，不虚称完整三套在返工后重跑。

唯一新增C++ RuntimeHost.cpp 已实际 clang-format-18 -i，随后 --dry-run --Werror，版本18.1.3，format-final.log；人工检查命名/状态、成员职责、回调表达及全部相邻函数（含类内）空行。Python py_compile 与 git diff --check 实跑。后续仅Python返工，不需要重建或重格式化未变C++。

## 性能取证粒度与风险

R保持官方程序：按 Leader 实施澄清，独立PID/端口的 generation task 日志在预热前、两预热后、12正式后三次排空边界核对每实例0→1→7。metrics GET不计推理attempt，核验其不增加生成计数。不凭 RR 或完成顺序推断 R-P 逐ID后端，不按实例归因客户端延迟。每后端/区间 timing 原文保留。CPU共享、各2线程、少量样本，不作GPU/生产外推。

A/P1约44ms问题只复测/报告，N只改变新合成后端NODELAY；不能从诊断外推产品已优化。H/Q报告施加/未发、scheduled与send时延、互斥终态和有效配对门槛；T记录漂移/工具敏感，不把观测开销或CPU占用直接断言为GIL瓶颈。所有分位按样本门槛，三重复不池化。

## 正式结果与逐AC闭合

Approved修复后的唯一完整run-002退出0，57/57 cell，407.06993秒，工具状态PASS。正式6788 success+316 queue_full=7104；预热477 success+9 queue_full=486；共7590唯一ID，无未发/未开始、HTTP timeout、协议/传输错误。run-001的任何样本没有拼入结果。

H20/H60/Q60有效对均3/3；LI−RR goodput三次为20/s下+3.1667/+3.3333/+3.3333、60/s下+11/+11/+11 req/s；queue8−queue0三次−10.5/−13/−10.5 req/s。T首单/双/末单完成吞吐1319.0891/2159.9131/716.9578 req/s，machine_drift、generator_sensitive、client_cpu_at_least_085及suspected_generator_limit均true。因此只接受本次受限环境描述数据，策略因果收益和网关容量**未证实**，不宣称普遍改进或GIL根因。完整57cell及三次原值见docs/performance/V0.4/S1-results.md。

| AC | 实际证据与边界 |
| --- | --- |
| AC01/RV01 | run-002/plan.json、manifest.json在负载前冻结7590ID/请求hash/配置；原始逐ID与summary independently重算一致；三重复不混池；17项关联拒绝控制与既有分类/时钟/SLO/预算负控通过 |
| AC02/RV02 | A/PR和N实际accept/request复用审计、后端NODELAY逐请求getsockopt；B代理三次正式pause/resume增量及各wave快流推进；drains全部FD回基线、RSS≤B+32MiB及账清零；原P1问题未优化 |
| AC03/RV03 | 开环全部到达计划闭合，无not_sent；H/Q有效配对均3/3；325个queue_full含预热9/正式316，与成功互斥；scheduled/send时延及queue_wait来自各自时钟，targets连接实例唯一关联；受T/CPU限制，不作因果结论 |
| AC04/RV04 | run-002/assets.json固定本地资产/库/许可；六R cell各预热2/正式12，双实例三边界0→1→7，开始/释放/timing集合守恒；metrics原文、日志SHA/PID/端口保留；P逐ID目标未观测，真实样本无尾分位 |
| AC05/RV05 | 运行期direct197656576 / managed12108355 / emergency79196 bytes，均在分区内；239start/reaped全exit0，原环境239PID全消失；全三套21/21及最终相关1/1、规范/历史保护/源产物/原始SHA见下；独立Reviewer尚未接受 |

独立离线脚本AuditRaw.py首次在启动空backend_peaks调用max([])失败，raw-audit-002.log保留；新编号AuditRaw003.py明确空峰仅可表示尚无inflight，复算成功。另startup-peaks-audit-001.json逐host证明空数组只出现初始前缀，sessions/inflight/peak_inflight全0，随后必须出现非空峰，不把缺失运行快照默认0。此修正仅离线检查，未动正式工具、样本、产物或重测。raw-audit-003.json独立复核每ID时钟、分位/SLO/goodput/完成吞吐、互斥分类、资源/事件/预算界、真实计数及进程闭合。

## 交付身份与未完成项

E/source-rework-001-sha256.json覆盖118源；E/binaries-frozen-sha256.json覆盖三套51产物；E/protected-frozen-sha256.json覆盖212历史保护项。final-identity-check.json确认全部仍吻合，原run-001所有原始文件SHA保持。run-002-raw-sha256.json逐文件覆盖新正式原始数据，run内部manifest还记录实际source/host/gateway/计划身份。详见E/handoff-identity.json。

完整正式命令：`python3 tests/experiments/RunExperiments.py --host build-local/builder/v0.4-s1/release/ExperimentRuntimeHost --gateway build-local/builder/v0.4-s1/release/ai-inference-gateway --assets build-local/integration/v0.2-s3 --output build-local/builder/v0.4-s1/evidence/run-002`；stdout/stderr为E/run-002.log，退出0。三预设相关复现`ctest --test-dir build-local/builder/v0.4-s1/<preset> -R ExperimentDetectors --output-on-failure`。持久短控：`python3 tests/experiments/DetectorTests.py build-local/builder/v0.4-s1/release/ExperimentRuntimeHost --output build-local/builder/v0.4-s1/evidence/detector-proof-rework-001`，退出0。离线完整复算命令与脚本在E/AuditRaw003.py和raw-audit-003.log；输出在正式目录外，不占用或改写测量样本。

Builder范围已完成，自有负载停止；等待独立Reviewer源码/端口复用与歧义追加控制、三预设和完整独立矩阵。Reviewer重点核查：运行期预算全路径、源端口复用顺序证明/排除边界、H/Q有效配对与T受限结论、R聚合观测粒度及每cell末态。现阶段没有独立接受结论；不提交、不推送、不启动V0.4/S2。文档与实现差异：旧0/2和run-001失败为历史记录，本报告按新Approved返工1/2；根Leader状态由协调者收口。
