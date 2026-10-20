# V0.3/S2 独立审查报告001

2026-10-20，Reviewer (Athena)。**PASS，累计交付返工0/2，无发现或待接受债务。** 本轮独立构建并完整执行三预设19项测试、固定Release混合一次及补充组合；未复用Builder测试通过结果冒充独立证据。V0.3整体仍待S3，本报告不启动S3或宣称MVP完成。

## 依据、范围与路线

读取[Approved设计](../../../leader/designs/V0.3/S2-design.md)、[审查计划](../../reviews/V0.3/S2-review.md)、[Leader001](../../../leader/reports/V0.3/S2-report-001.md)、[Builder001](../../../builder/reports/V0.3/S2-report-001.md)、拆解/来源、S1最终接受记录及根文档相关范围。无S2正式返工或旧Reviewer报告。无项目专用Reviewer指南，按plan-project-docs全局Reviewer模板回退；复用已读personal-cpp-standards完整规则及正反例、重新确认agent-execution-route。用户跨项目规则适用，未发现实质权威冲突。

审查AdmissionController、GatewayConfig、ModelRouter、ProxySession、GatewayRuntime、EventLoop既有task/cleanup调用路径、新Admission测试/host/脚本和配置文档。没有修改产品、测试、Approved、Builder材料或根状态文件；仅生成本报告和独立证据。Builder停止负载后开始验证，未使用其构建产物、进程、端口或可变测试目录。

实际原生WSL，/bin/bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway，分支codex/v0.3-s2-admission-queue，HEAD b704df268e2865bda146ba4c816dd105e6c8302c。独立build-local/reviewer/v0.3-s2/{tmp,cache,evidence,debug,release,asan}；构建/Python前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME及PYTHONPYCACHEPREFIX。socket和LSan按已知边界首次精确提升权限，没有关闭检测器、下载依赖/模型或运行P1矩阵/旧长期soak。无提交或推送，S1远端未独立核验。

## 实际执行

下文E为`build-local/reviewer/v0.3-s2/evidence`。三套分别执行`cmake --preset MODE -B build-local/reviewer/v0.3-s2/MODE`、`cmake --build build-local/reviewer/v0.3-s2/MODE -j4`、`ctest --test-dir build-local/reviewer/v0.3-s2/MODE --output-on-failure`；MODE为debug/release/asan，各配置/构建/完整测试均退出0。

| 独立执行 | 实际结果 | 原始证据 |
| --- | --- | --- |
| Debug完整CTest | 19/19，35.03s，零失败 | E/configure-debug.log、build-debug.log、ctest-debug.log、last-test-debug.log |
| Release完整CTest | 19/19，30.75s，零失败 | 对应release四份日志 |
| ASan+UBSan完整CTest | 19/19，48.31s，零失败，无检测器错误 | 对应asan四份日志 |
| 固定Release混合一次 | 24请求全部成功，68检查，0.854089s，退出0 | E/mixed-release-001.json及.log |
| 独立四组关键组合 | 122断言，FD4→4，退出0 | E/Independent.cpp、Independent、independent.log |
| UTF-8逻辑charge与边界 | 1061字节、7断言，退出0 | E/Charge.cpp、Charge、charge.log |
| 新示例实际启动/停止 | READY 127.0.0.1:8080，SIGTERM退出0并回收 | E/example.log |
| 格式/差异/人工检查 | 12 C++文件dry-run、diff --check均退出0；函数边界、职责组、回调人工通过 | E/format.log及本报告 |
| 样本与身份独立复算 | 24唯一请求、FIFO/等待统计/计数/末态全部通过；94源与45独立产物清单 | E/Audit.py、audit.json、source-sha256.json、binaries-sha256.json |

混合实际命令为`python3 tests/admission/RunAdmission.py build-local/reviewer/v0.3-s2/release/AdmissionRuntimeHost --mixed build-local/reviewer/v0.3-s2/evidence/mixed-release-001.json`。只执行一次，没有择优重跑；固定负载和全部客户端尝试已落盘。负控属于AdmissionE2E，不混入24请求分母。

Independent.cpp复用已审阅的FakeIo/socketpair装配辅助代码，但Reviewer自行编写Runtime friend入口及四组序列；没有调用Builder的fairnessChecks/budgetChecks来冒充追加覆盖。编译使用`g++ -std=c++20 -g -Isrc -Itests -Ithird_party/llhttp/include E/Independent.cpp build-local/reviewer/v0.3-s2/debug/libgateway_runtime.a build-local/reviewer/v0.3-s2/debug/libgateway_foundation.a build-local/reviewer/v0.3-s2/debug/libllhttp.a -o E/Independent`，再运行E/Independent。Charge.cpp使用相同独立库构建执行；E按上述目录展开。

格式工具Ubuntu clang-format18.1.3，实际命令`clang-format-18 --dry-run --Werror`覆盖src/admission/AdmissionController.{h,cpp}、src/app/GatewayConfig.{h,cpp}、src/routing/ModelRouter.{h,cpp}、src/gateway/{ProxySession,GatewayRuntime}.{h,cpp}、tests/AdmissionTests.cpp、tests/admission/RuntimeHost.cpp。人工检查包含.cpp类内方法间空行，非简单方法外移、短lambda具名转发及weak token寿命；没有重复S1漏检或代替Builder格式化源码。

## 逐AC独立核验

### AC01：配置与兼容

检查明确opt-in、models约束、各整数范围/负数/溢出/bool/未知/重复字段。Admission.configChecks实际覆盖省略/默认/上下界与legacy拒绝，Runtime直接构造非法限额抛错。Reviewer补充perbackend=0直接验证拒绝，并实际用新增配置启动正式Release程序、立即SIGTERM收口，不需要真实后端。旧S1/legacy17入口完整回归，原断言与旧两样例SHA保持。

### AC02：限额与请求/连接分离

Router仅真正选择时推进游标、占Trial、递增RequestLease；inspectModel只读，先区别健康与容量，全局由唯一实例inflight求和。完整Admission.limitChecks验证双模型四实例global2/per1、多次容量失败不改变游标/Trial，混合观察峰2/1。S1多idle/HTTP完成早释放和旧epoch断言仍完整执行。

独立补充先取得a请求租约和16个连接租约，完成请求后保留连接；队列释放容量再派发命中仍满的池，结果精确upstream_capacity、无connect、无重排/改投、global归0且健康不计失败。证明可用推理额度不保证传输池立即空闲。

### AC03：有界FIFO与账本

Controller只持ID/charge，不复制请求正文；deque插入成功后才记账，remove幂等。Admission.queueChecks/middleCancellationChecks/allocationChecks实际验证count/bytes恰满及超1、单项过大、两种0等待、三项中间取消FIFO和真实分配异常下账不变。Waiting无RequestLease/ConnectionLease/streamCapacity，只有原16MiB预约，派发/终止/异常均经releaseWaiting清账。

Reviewer以中文body“中文”及header值“值”独立按UTF-8字节计算：1024+method4+target2+body6+(name6+value3+4)+(name4+value4+4)=1061；实际charge一致。队列byte上限1061时可入，再入1字节拒绝，移除后归零。大小是逻辑请求预算，不等于新增16MiB、RSS或allocator用量。

### AC04：deadline与当前健康

Waiting nextDeadline为accept总期限与入队期限最小值；等于即拒绝，同刻total优先；dispatchWaiting检查后dispatchUpstream再次检查，跨等待不刷新total。Admission生命周期验证提前1ms、恰等、同时、接收已耗500ms、排队后LI变化、摘除后重选、全部不可用立即503、Trial取消中立。

Reviewer独立组合在队首a的total/queue同时恰到期时释放全局容量，同次Runtime清理中a必须total_timeout且0连接，b随后成功派发，不因容量释放复活已过期队首。旧S1健康状态/epoch/取消保护完整保留并实跑。

### AC05：通知、轮转、取消与停止

源码追踪入队/释放/取消只dirty通知，Runtime在回调结束后按稳定ID查Session，guard禁止重入、32处理预算、仅仍可进展投一个task；纯容量阻塞不自唤醒。task短转发具名方法，weak token在Runtime析构首部失效，捕获owner在失效后不访问。requestShutdown先停新准入/路由，等待者503退账；强制停机及清理保持有限且幂等。

独立取消a队首后，b在持久轮转顺序中先获得刚释放容量，其余a保持FIFO；之后真实dirty通知驱动剩余a，无新请求依赖。独立48等待先确认纯阻塞无task，随后摘除模型让首轮恰处理32、余16且一个task pending；此时停止，16项退账，续轮task空操作，不误派发，最终Session/queue/bytes/inflight/timer/预约归零，整组FD4→4。该序列与Builder40项用例不同。

真实AdmissionE2E验证RST退账、完整请求SHUT_WR仍取得完整响应、释放容量后无人为新请求也推进、queue_timeout、活动流和等待者同时停止。EOF与完整TCP离开不可总区分的边界如设计保留，不宣称探测所有取消。

### AC06：固定混合与交付

下表由Reviewer的E/Audit.py直接读取原始host记录及客户端尝试重算，不导入Builder统计函数。核验24唯一Session ID和24唯一input_index、每模型12条（短9/长3）、全部status200/outcome complete、完整五时刻顺序；22条enqueued>0、2条未排队独立计数。按实际enqueued排序与dispatched排序同模型完全一致，不以线程启动编号证明FIFO。

| 模型/类型 | 完成 | 排队/未排队 | 等待median ms | 等待max ms |
| --- | --- | --- | --- | --- |
| a/短非流 | 9 | 9/0 | 479.758271 | 764.680063 |
| a/长流 | 3 | 2/1 | 404.931704 | 542.493056 |
| b/短非流 | 9 | 9/0 | 489.202600 | 771.789192 |
| b/长流 | 3 | 2/1 | 414.473713 | 549.829332 |

全部0超时/拒绝/取消。固定配置global2/per1、每模型16/4MiB队列、queue5000/total10000ms、session64及预约1GiB，四受控实例；统一门闩、模型交替发送，每模型第1/5/9长流目标200ms，其余短目标10ms。独立实际总时长0.854089秒，未超30秒护栏。峰global2、单实例1、总队列22/26286字节，每模型11/13143字节；终态queue/bytes/inflight/sessions/reserved/timers全0。

此场景只验证有限负载正确性与实际等待。短请求受FIFO头阻塞，模型轮转不等于严格墙钟公平；事件边界采样峰不证明所有瞬时峰，限额机制另由确定性测试和代码审查确认。200/10ms仅目标服务参数，host写盘、闭环、本机共享资源均影响时长；不证明长期无饥饿、开放负载SLO、GPU或性能收益。

## 身份、保护与资源

E/source-sha256.json共94项，SHA256 `febfcc184489b3efe49870b91d658715e46c6f52eebe764e5c2ac69b76396c7f`，独立逐项重算与Builder最终源完全相同。E/binaries-sha256.json共45项，SHA256 `233b56b7d967bfc8e5d9b6b9a050aff84cd67913a41b81e41356c57e5048805e`，为独立三预设每套12可执行及3静态库；45不是测试入口数。

混合原始E/mixed-release-001.json SHA256 `42eb4ee2a7603ec59ad5f91e4c0eae44a7487683b62c80db1569e2ff28e26b33`。E/audit.json保留独立计算结果，E/protected-audit.json记录137个已有docs/third_party/tests/config/格式/预设文件逐项与当前HEAD一致，没有拿Builder的unchanged标志代替重算。

权威设计SHA `002b00cdb5501d1e86326e02160dc9eaf785e4b11ed56fd116174a8c3078ded3`、审查计划`a3adaec952fcf85c4942827af108354784f3c063a3476ad3c5afd51e4b60f8c7`、Leader001`c3927110ba03c6cac6136f6d123cc394320923adc5be590652bd3ed2da8f7230`、Builder001`212ad53033fe20e0f2db04ef85733a1c9c3cc30c958ca36f38eb8a226af18fc7`均不变。

所有独立构建/CTest/混合/探针/示例进程已经结束；host communicate回收，受控后端server_close并join，补充fixture FD和账本回基线，无新增持续负载。Builder旧失败日志及其明确的部分回归复用仍为历史，本轮以当前源码完整三套19/19独立执行覆盖，不改写旧日志。

## 发现、限制与最终结论

发现：无。返工要求：无。待接受债务：无。契约内未验证阻塞项：无。新配置说明、错误码、预算及半关闭/被动健康边界已在README；源/测试/证据可追溯。真实多实例推理综合验收、长期公平、性能优化与P1约44ms根因均未测且属于明确后续范围，不转为本阶段缺陷。

**最终PASS，0/2。** Leader可据此同步README/ROADMAP/ARCHITECTURE/CHANGELOG与阶段收口报告，清理当前状态中的“待实现/不启动S2”等旧快照指代；本Reviewer不自行改根状态。协调者再按长期授权本地提交、不推送，V0.3/S3不自动开始。
