# V0.2/S3 Reviewer 独立初审报告001

2026-10-19；Reviewer (Athena)。结论：**FAIL**。唯一发现 **V02-S3-F-001，Major：部分异常请求尝试不能落入原始样本记录**。真实模型协议、取消/故障、两类完整长期运行和三套产品回归均通过；本次FAIL针对交付工具的失败证据完整性，不是已复现的网关产品故障、假PASS或进程泄漏。

本阶段当前累计返工 **1/2**：此前协调者审计触发的33→36项二进制计数文档纠正已由Builder002完成；本报告不自动增加返工计数。尚余一轮受限纠正，交协调者统一处理；不能提前关闭S3/V0.2或开始第三轮。本轮不接受债务，不提交、不推送。

## 1. 权威、范围、路线

完整读取S3 Approved设计/审查、Leader001、Builder001及002、breakdown、变化记录、tests/integration/README及全部工具/固定输入；复核根范围与S2接受链。Approved状态中的0/2保留其历史时点，当前累计计数取协调者交接和Builder002。

- 设计SHA256：`af975691b5540600e9f8c894b0964346ba6ad3b77c30bc420eedaea74475ae5a`。
- 审查SHA256：`1315d12f060048cd5706e59a552a3658e4e6d2e45e8145d7369ca06bc2b7b0b5`。
- 分支`codex/v0.2-s3-integration`，HEAD `d933e8892033a600b68ff5ac0db950dec5abea90`。

遵循用户AGENTS、agent-execution-route、personal-cpp-standards完整规则/正反例；无项目Reviewer指南，回退plan-project-docs全局Reviewer模板。实际路线：原生WSL、`/bin/bash` login=false、cwd `/home/power/projects/AI-Inference-L7-Gateway`。独立目录`build-local/reviewer/v0.2-s3/{tmp,cache,evidence,debug,release,asan}`；以下E指其中evidence。Python/构建前设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME，已知socket/LSan第一次精确窄升级，无下载/安装/禁检查。只读共享固定资产，自己的模型/host/gateway进程、端口、日志和构建；没有接管Builder后台。真实与模拟使用不同host，真实模型始终最多一个。

所有产品src、第三方、旧文档等100项保护文件与HEAD逐字节一致。本阶段实际新增测试host/标准库Python工具、固定输入和CMake入口；Reviewer未修改产品、工具、权威或历史。没有派生代理。所有本轮自有进程在交接前已经wait回收。

## 2. 唯一发现 V02-S3-F-001

**严重度：Major。** 对应设计§6“所有样本包括计划失败/取消均保留”、§7原始样本完整性，AC04/AC05及RV04/RV05检测器要求。

**位置与根因：** `tests/integration/Support.py:259`在try/finally之前调用socket.create_connection；连接拒绝/连接超时直接逸出。`Support.py:291`等SSE断言、JSON解析/结构访问、原始HTTP转换、回调异常和客户端界限断言可能抛AssertionError/ValueError/KeyError/TypeError等；`Support.py:320`只捕获OSError/HTTPException。后者虽执行finally并关闭socket，仍不返回已累积的result。随后`RealRun.py:29`、真实soak的exchange调用、`SyntheticRun.py:88`均未到append，协议标签/index/请求hash/起止时间/已收字节/具体错误没有形成逐尝试记录。模拟worker内落盘已修复“成功返回但晚到future未收集”的旧缺口，尚未覆盖exchange本身抛出的异常。

**预期：** 每个已开始的请求尝试恰好留一条可审计结果，包括连接阶段失败、HTTP/SSE解析或结构错误、校验/回调异常及并发晚到失败；保存已知请求标识、时间、响应状态/部分字节和错误。判失败仍须非零，不能为了记日志吞掉错误或把不完整响应改为成功。信号/取消应记录适当的中断状态并保持原传播/清理语义。

**独立复现：** E/SampleLossProbe.py直接调用交付RealRun.sample和SyntheticRun.run_sample，使用本角色loopback端口；分别构造真实连接拒绝、模拟连接拒绝、HTTP有效但SSE内容为`not-data\n\n`。三例都抛异常，实际逐请求样本数均为0，E/SampleLossProbe.log记录`LOST_FAILURE_SAMPLES 3 OF 3`，exit1。E/LateFailureProbe.py安排4个错开完成的模拟worker连接失败，4个future均真实结束，样本仍0/4，exit1；E/late-failure-errors.json保留全部实际异常。原证据不覆盖。

**影响边界：** 当前正常正式run仍可以逐条审计且没有意外失败；故障run会非零退出，并非静默丢失败后继续得PASS。但失败尝试及并发晚到异常的分母/部分响应无法完整追溯，违反本阶段显式交付要求，不能用成功长run抵消。没有因此认定网关会丢数据或推理取消失效。

**清理对照：** E/FailureCleanupProbe.py仅在自身解释器内用轻量自有进程替代模型启动，调用实际RealRun.run，在协议阶段注入异常。子进程exit1、result.json为FAIL，fake后端与真实IntegrationRuntimeHost两个自有进程均reaped且/proc不存在；顶层对照exit0。证明当前run级finally清理/非零传播有效，不能把本发现夸大成已证实进程泄漏。返工须保持这条性质。

**处置要求：** 统一覆盖上述同根异常出口，保存每attempt记录后继续原失败判断/异常传播；不通过修改协议校验、负载、期限、容量或过滤失败样本绕过。增加连接拒绝、坏HTTP转换、非法SSE/JSON结构、回调异常、并发首失败后晚到future、超时及run级清理/非零对照，核查失败数/唯一index与实际启动尝试数一致。记录失败不得重复落盘，仍需清理属于自己的socket/进程。Reviewer未代修。

## 3. 独立环境与真实协议（RV01—03）

独立复算固定tar19144446字节/SHA `9cbbff430e4f2d976135d68d998576530cc1bd87babe1d71db4886d8a79e7b2e`，GGUF491400032字节/SHA `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`，与Approved一致。进一步将解压目录37个实际文件逐字节与固定tar对应成员比较，全部一致；模型LICENSE及server/库身份记录E/asset-check.json、extracted-asset-check.json。没有只信资产清单或Builder结论。

版本输出7481/cc0a04343、GNU11.4；ldd无缺依赖，许可沿固定MIT/Apache2原文。当前WSL2 Linux6.6.87.2/glibc2.39、Python3.12.3、20逻辑CPU，MemTotal7974056kB，见E/environment.json及backend-version/ldd.log。命令固定ctx2048/parallel1/threads4/threads-batch4/ngl0/alias gateway-qwen/metrics，只绑定127.0.0.1。模型日志真实加载并推理，首轮direct warmup的非流/SSE均200，作为本次M0直接接口证据；不是仅health成功。

独立正式数据位于E/real-001，包含93条protocol-samples（含预热、正式、取消/恢复、故障、正式程序及soak前后探针），标签区分用途。E/protocol-audit.json独立重算：

- warmup不计入正式；direct/proxy各10非流+10流，共40正式样本，严格交错。非流唯一application/json;charset=utf-8、流唯一text/event-stream；状态、非空assistant内容及合法终态通过。
- 长流3条各512个非空content增量，首content至HTTP结束分别约5.733/5.890/5.925秒，真实观察增量；慢读3次、完整请求SHUT_WR3次均成功。
- 固定合法大messages触发真实4830 tokens>2048 context，direct/proxy均400，195字节JSON error结构一致；未加厂商字段或放宽产品解析。
- 首content后RST5次，L1清理约0.151–0.154秒：同负载snapshot活动账本全0、FD7；L2上游/租约/FD释放并有backend cancel task/slot release日志；L3每次/slots在取消前processing=true、后false，新短请求在取消后约0.487–0.523秒成功。仅证明固定CPU模型slot恢复，不宣称GPU计算停止。
- 自有backend请求前关闭、首content后TERM、首content后KILL各一轮；前者明确502/503，后两者已提交200但截断、无正常DONE/HTTP完成。保持原端口/CLI重启，实际TIME_WAIT等待在120秒启动护栏内；每轮2非流+2流新请求恢复，无网关retry。
- 正式ai-inference-gateway独立进程正常流/非流冒烟成功；活动长流首content后SIGTERM约3.127秒有限截断，进程exit0，无成功终态。没有用test host取代正式入口。

本轮直接/代理没有比较不稳定ID/created/timing或声称模型逐字节确定性；精确透明性通过模拟固定字节流验证。RV01—03本次实际执行通过，不抵消F-001的工具异常路径缺口。

## 4. 两类完整长期运行（RV04）

两个run没有修改源文件；manifest的64项源与本次独立source清单完全一致。时长从原始样本最早start到最晚end重算，排除了启动、故障重启和末尾排空，不用summary收尾时间补足门槛。E/AuditRuns.py独立检查唯一连续index、原seed序列、类别、正文hash/长度、实际并发、账本/RSS及进程退出；E/run-audit-final.log exit0，结果E/run-audit.json。

| 项目 | 真实real-001 | 模拟synthetic-001 |
| --- | --- | --- |
| 原始样本跨度 | **601.662秒** | **310.192秒** |
| 正式数量/分布 | **1270，635流+635非流**，严格交替 | **650：260快流、130慢流、130非流、65取消、33坏chunk、32截断** |
| 实际最大在途 | 1 | 4；seed20261019逐index复算一致 |
| 实际分类 | 1270正常，0意外失败 | 520正常、65预期取消、65预期故障，0意外失败 |
| 排空点（含协议/预热） | 137，全部FD7/活动账本0 | 14，全部FD7/活动账本0 |
| 预热排空RSS B | 4,157,440字节 | 4,349,952字节 |
| 每秒采样gateway RSS峰值 | 4,157,440字节 | 5,005,312字节 |
| 末5排空RSS跨度 | 0 | 28,672字节 |
| 模型每秒RSS峰值 | 624,513,024字节，低于2GiB护栏 | 无真实模型，不混报 |
| 退出/清理 | exit0，全部6个自有进程记录reaped | exit0，自有host reaped、后端线程随驱动结束 |

两者均满足B+32MiB及末5点跨度8MiB阈值。模拟累计3160次pause/resume，峰值预约67108864、数组容量1048576、pending815998字节；所有快照容量上界及最后活动状态均验证。固定模拟正常正文按hash及长度严格相等，故障前缀也精确相等，原始HTTP解码拒绝尾随；取消不冒充HTTP完成。

资源来自同一主负载host、同一产品库和真实socket，非另一低压fixture；100ms账本与累计峰值共同使用，1秒RSS仅采样诊断。不声称捕获所有瞬时RSS或给出吞吐/TTFT收益。真实模型小流没有触发高水，未拿它当背压压力证据；模拟和三套Backpressure提供实际高水覆盖。

本次长run所有已执行请求都有连续原样本且验证通过，正常工作负载结果有效。RV04的异常留存交付项仍因F-001未满足，不能据正常样本将阶段标PASS。

## 5. 回归、检测器、规范（RV05）

| 独立验证 | 结果/证据 |
| --- | --- |
| Debug完整CTest | **13/13，25.87秒，exit0**；E/debug-{configure,build,test}.log、debug-LastTest.log |
| Release完整CTest | **13/13，23.16秒，exit0**；对应release日志 |
| ASan+UBSan完整CTest | **13/13，38.96秒，exit0**；对应asan日志，无sanitizer诊断 |
| 原response/total完成探针 | **18/18+18/18，exit0**，当前Reviewer Debug库重新链接 |
| 原120/150ms关闭窗口 | **20/20，exit0**，当前Reviewer Release gateway |
| 交付9项检测器负控 | 各子进程非零，顶层exit0；E/detectors.log及三套CTest记录 |
| Reviewer额外原始HTTP控制 | **8项，exit0**；合法CL/chunked、重复零块、尾随、缺零块、CL短/多字节、CL+TE冲突；E/WireProbe.py/.log |
| 失败留存反例 | SampleLossProbe **3/3丢失，exit1**；LateFailureProbe **4/4丢失，exit1**；即F-001 |
| run级异常清理对照 | 子进程exit1、2个自有进程已回收，外层验收exit0；FailureCleanupProbe日志 |

三套覆盖原S2 Backpressure/Runtime的水位、分配、期限、取消、旧token和停止回归，新增IntegrationDetectors不下载模型、不执行长run。18+18探针沿S2 Reviewer已记录的constructor-only预算适配，原件/patch一并保留，时序/断言不改；CloseWindow SHA仍为`158de752e714596bbdacf5e0e5c351d098d74239faf95d3b7f4d63ec8b58b425`。未重复无关18cell旧成本矩阵。

逐行审查RuntimeHost.cpp与所有Python模块；host只消费既有snapshot/pollOnce，新增friend只读停止状态，无产品管理API。CMake仅加测试host/快速入口。实际clang-format-18 dry-run/Werror exit0；核对Builder实际-i记录并人工检查函数间空行、方法/成员职责和短回调，未发现规范问题。git diff --check通过。

Builder原失败与身份链已检查：真实校准TIME_WAIT失败保留；模拟首个正式run失败和晚到future缺失已标无效；补位改为新snapshot确认closing退休，未提高连接额度或改变seed/配比。Builder真实run期间唯一变化为未被RealRun导入的SyntheticRun，旧文件与manifest/patch对应。本次Reviewer两个run都直接执行最终相同身份，无运行中源变化。Builder002纠正36项计数属实，不把历史001改写为正确。

## 6. 命令、身份和过程证据

环境统一为：

```bash
export TMPDIR="$PWD/build-local/reviewer/v0.2-s3/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/reviewer/v0.2-s3/cache"
```

三个mode分别`cmake --preset "$mode" -B build-local/reviewer/v0.2-s3/$mode`，`cmake --build <该目录> -j4`，`ctest --test-dir <该目录> --output-on-failure`。所有配置/构建退出0。E/command-exits.json记录实际命令结果；反例exit1与功能测试exit0分开，不掩盖为“全绿”。

显式正式长run：

```bash
python3 tests/integration/RealRun.py --assets build-local/integration/v0.2-s3 --host "$PWD/build-local/reviewer/v0.2-s3/release/IntegrationRuntimeHost" --gateway "$PWD/build-local/reviewer/v0.2-s3/release/ai-inference-gateway" --output build-local/reviewer/v0.2-s3/evidence/real-001
python3 tests/integration/SyntheticRun.py --host "$PWD/build-local/reviewer/v0.2-s3/release/IntegrationRuntimeHost" --output build-local/reviewer/v0.2-s3/evidence/synthetic-001
```

没有传calibration或缩短阈值，分别E/real-001.log/.exit、synthetic-001.log/.exit。既有负控命令`python3 tests/integration/DetectorTests.py <Reviewer Release IntegrationRuntimeHost>`。额外探针逐个`python3 <E/探针.py>`，保留stdout/异常/子进程结果。18+18编译命令使用`c++ -std=c++20 -g -I src -I tests -I third_party/llhttp/include <E/探针.cpp> <Reviewer debug>/libgateway_runtime.a <Reviewer debug>/libgateway_foundation.a <Reviewer debug>/libllhttp.a -pthread -o <E/探针>`；关闭窗口`python3 <E/CloseWindow.py> <Reviewer release>/ai-inference-gateway`。

- 独立64项E/source-sha256.json SHA256：`72eee933535c0f66a19279d4b33d936c0a7b9e31200a0797fd3dcadc6a330d34`，与Builder最终源逐项相同。
- 独立36项E/binaries-sha256.json SHA256：`becb5a2bd132d5590ba9bdbdc97e3a4e621267b471ac152f0da5a2e934c80992`；每模式9可执行+3静态库，不以CTest数量代替产物数。
- 当前Support.py：`532fe1dd2a89e45ab988598bcd6b45fe9b3132aa3337bd108b86c596d612c244`。
- 当前RealRun.py：`f55c1be741cd5dbe9bb45c8ffc10ab72b56900747b09b564507faaf4d882336c`。
- 当前SyntheticRun.py：`eea879a85be849531c8a0693c1bf8ecccfc91acf1fb1a99af1a348d5fbcf7bed`。
- Reviewer探针身份见E/probe-sha256.json；保护计数/环境/完整审计见E/identity.json、environment.json、run-audit.json。

原始证据在收口审计时约47,386,813字节，低于角色128MiB护栏；进程日志、失败探针及全部正式样本不删除。独立核对所有processes中的start均有reaped且对应PID已不存在，真实计划KILL的-9单列，其余正常退出。无模型/host/gateway遗留。

## 7. 最小返工复验范围与交接

建议下一轮只修F-001，不改变Approved范围，不为验收重写正常收发或产品。若精确差异仅覆盖异常记录/传播、必要采样包装及其负控，且能证明：

1. 产品库、host、WireResponse正常解帧、请求输入/CLI、timeouts、正常IO/时钟/慢读、并发/退休门、seed配比、资源采样及门槛没有改变；
2. 本轮成功样本走的正常分支语义保持，新的异常处理不会吞掉失败、覆盖partial字段、重复记录或把取消改为成功；

则**无需无理由重复600/300秒**。可按本报告原64项/36项身份明确复用601.662秒真实与310.192秒模拟、完整回归、18+18/20及当前协议/取消/故障证据，不能把旧结果伪称新源码全量实跑。

最低新增独立复验应包含：精确diff与新旧身份映射；原SampleLoss/LateFailure反例保留并在新工具上不丢任何attempt；连接/HTTP/SSE/JSON/回调/超时/中断和并发晚到失败控制；失败结果非零及所有自有资源回收；9项旧负控与新增负控；短正常真实协议/取消/重启校准、模拟50请求校准，确认成功路径、分类和无重复样本；相应快速CTest/语法格式检查。校准只能标校准，长期接受证据仍引用本次原身份。

若修复触及正常收发/帧判断/时间、调度/退休门、配置/负载、资源采样或长期判断，必须重跑受影响的完整长期run；共享正常路径变化则两者重跑。原因是原长run未执行这些新语义，不能仅凭hash差异说明或短探针推断持续行为。产品/C++改变另按实际影响执行相关三套回归。

最终结论保持FAIL，未接受延期。当前没有其他正式发现、未验证的真实环境阻塞或产品故障。取消仅分层CPU观察，暂停断连延后、容量不等于RSS/内核内存、单后端单slot不代表调度性能等Approved限制保持。请协调者统一交付最后一轮受限返工；Reviewer报告与全部原始结果保留，修复后新增报告002，不覆盖本001。不提前修改根状态为S3/V0.2完成。
