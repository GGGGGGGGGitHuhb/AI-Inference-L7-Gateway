# V0.3/S1 Builder 实现报告001

2026-10-20，Builder (Hephaestus)。初次实现及自检完成，Ready for independent review；累计返工0/2。自测通过不代表独立验收，没有提交或推送。

## 目标、依据与结果

依据[Approved设计](../../../leader/designs/V0.3/S1-design.md)、[审查计划](../../../reviewer/reviews/V0.3/S1-review.md)与[Leader001](../../../leader/reports/V0.3/S1-report-001.md)，完成模型路由、RR/Least Inflight、每实例池、被动健康/epoch与有限生命周期。已阅读V0.2/S3收口与P1接受边界，保留历史，不重开P1约44ms诊断，不提前实现队列/重试/主动探针或真实多实例综合验收。

分支codex/v0.3-s1-routing-health，起点e231fda25879060fcd730f562982f06448f2ba11。实施[拆解](../../breakdowns/V0.3/S1-breakdown.md)已更新；无项目Builder指南，按plan-project-docs全局Builder/阶段拆解模板回退。遵循agent-execution-route、personal-cpp-standards完整规则与正反例。用户已有完成后本地提交、不推送授权，提交交协调者。

实际交付包含配置/协议错误兼容、纯路由和请求RAII租约、多池Runtime、Session最早上游终态与连接归池epoch防护、确定性与socket测试、中文示例/边界文档。没有新增依赖，产品无管理端点；第三方/默认单上游样例/P1工具/历史文件未修改。文件责任与来源见[changes](../../../references/V0.3-S1-changes.md)。

## 关键实现与差异

- ModelRouter只持静态目录及有界状态，选中与inflight递增同步；RequestLease不可复制、可移动，显式一次complete，析构中立兜底。Router不可复制，Runtime保证寿命长于Session/lease。无健康timer。
- Runtime保留legacy单池入口，新模式每(model,id)独立池；测试快照新增逐实例状态与池计数。聚合peakTotal是各池峰值和上界。停止先禁路由/池获取、清idle，Session强制停止后各池清理，事件回调后的retired销毁顺序保留。
- Session在验证model后选择一次目标，不重试/改选。完整HTTP在deadline与输出准备成功后即报告，流在确认HTTP终态后报告；下游排空仍可持ConnectionLease，但不持请求inflight。归池再次查epoch与Available。当前epoch摘除同步clearIdle，迟到旧epoch结果不能恢复健康。
- 所有明确上游错误/timeout通过有类型Observation报告；本地/客户端/总deadline保持中立，暂停中的response deadline中立。完整状态按2xx成功、3xx/401/403/404/5xx失败、其余4xx中立。
- 自检发现HttpParser原来把所有响应解析拒绝统一映射502，单靠errorStatus无法区分本地上限与协议故障。按设计已要求的分类新增通用ParseFailure（协议/资源上限/内部错误）；HTTP层不依赖routing，原errorStatus/errorCode及原对外响应保持。Session消费枚举，不靠错误字符串猜健康。Coordinator确认这是既有契约内最小实现，无Approved修改。

## 实际执行路线与命令

原生WSL、/bin/bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway。下文E=`build-local/builder/v0.3-s1/evidence`，角色独立tmp/cache/build，不共享Reviewer可变状态。构建/测试均设置：

```bash
export TMPDIR="$PWD/build-local/builder/v0.3-s1/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.3-s1/cache"
export PYTHONPYCACHEPREFIX="$XDG_CACHE_HOME/pycache"
cmake --preset debug -B build-local/builder/v0.3-s1/debug
cmake --build build-local/builder/v0.3-s1/debug -j4
ctest --test-dir build-local/builder/v0.3-s1/debug --output-on-failure
```

release/asan分别替换preset和目录，实际逐套配置、构建和完整运行；没有关闭ASan/UBSan/LSan。所有socket/LSan测试在已知边界首次精准提升权限；未安装/下载模型或依赖，未跑P1长矩阵/旧600和300秒soak。

| 最终验证 | 结果 | 原始证据 |
| --- | --- | --- |
| Debug完整CTest | 17/17，0失败，33.78s，退出0 | E/ctest-debug-final.log |
| Release完整CTest | 17/17，0失败，31.31s，退出0 | E/ctest-release-final.log |
| ASan+UBSan完整CTest | 17/17，0失败，50.99s，退出0 | E/ctest-asan-final.log |
| 最终构建 | 三套成功，退出0 | E/build-{debug,release,asan}-final.log；configure-*-001.log |
| Routing | 每套277断言，14类Session终态、资源/FD归零检查 | 各build目录Testing/Temporary/LastTest.log，已复制到E |
| RoutingE2E | 每套183检查，全部自有进程回收 | 同上 |
| 同时双模型补充 | 8并发请求，正文/Host/每实例2次/无重试/进程退出 | E/ConcurrentModels.py、concurrent-models.log |
| 格式、Python语法、差异 | clang-format-18实际格式化和检查、py_compile、git diff --check成功 | E/format-final.log、validation-commands.txt、doc-check.log |

格式工具实际版本Ubuntu clang-format18.1.3 (1ubuntu1)。执行 `clang-format-18 -i` 后执行同范围 `--dry-run --Werror`：`src/app/GatewayConfig.{h,cpp}`、`src/routing/ModelRouter.{h,cpp}`、`src/gateway/{GatewayRuntime,ProxySession}.{h,cpp}`、`src/upstream/ConnectionPool.{h,cpp}`、`src/http/HttpParser.{h,cpp}`、`tests/Routing{Tests,Lifecycle}.cpp`，共14文件。人工检查构造/业务接口分组、类型/函数边界、函数内职责空行、回调仅具名转发，未全仓重排或修改格式配置。运行时回调仅捕获原有Session/Runtime owner，寿命由Runtime持有与清理顺序保证；路由新增同步调用，无短命异步observer。

## 逐AC实际证据

| AC | 已执行/检查的对应入口与断言 |
| --- | --- |
| 01 配置/旧兼容 | RoutingE2E.config_checks实际启动负配置并断言非零且无READY：缺字段、错误类型/范围、重复键/模型/id/同组端点、未知键、深度、大小、两模式冲突、自指、模型/实例/乘积上限；合法32模型64实例×16=1024启动/停止。legacy任意模型请求成功。旧Runtime程序构造配置及全旧CTest断言保持。实际端口0启动路径在所有E2E使用，Runtime所有后端实际绑定端口复查代码已检查；自指拒绝负控使用固定端口配置。 |
| 02 选择/隔离 | Routing.selectionChecks确定RR固定序列、LI持有一个请求时选择另一实例和平局轮转；RoutingLifecycle.leastInflightIdleChecks实际构造3idle，验证total=3不影响初始平局、持有传输后仍按请求inflight选择、上游完成后旧传输有效但inflight已释放。runtimeIsolationChecks同物理端点两个model的pool地址不同/各leased=1，摘除一个不影响另一个；E2E四实例RR及LI门控长流，补充ConcurrentModels真实同时双模型8请求，正文/Host不串。未知404不增加后端计数。 |
| 03 健康 | healthChecks单调时钟精确阈值前后、中立不增不清、成功清零、冷却前/到期、唯一Trial、失败/中立回冷却、恢复，旧epoch成功/失败只释放旧inflight，epoch最大值进入Exhausted不可路由；全状态分类断言。E2E四实例各三轮503摘除→TCP仍可达404试探失败→200恢复；400/429连续请求中立。 |
| 04 生命周期 | completionChecks对非流/流HTTP完整但客户端阻塞观察inflight=0，epoch变化后旧连接不入idle；terminalChecks覆盖RST、连接失败、非法HTTP、recv故障、total、response、本地输出限制、暂停response、stream_idle、stop、connect/write timeout、body保护上限、503正文不完整后EOF（仅一次失败）。idleAndTrialChecks有3idle，派发后2idle，摘除后0；trialAndCapacityChecks覆盖活动Trial取消/停止/池满/流预算不足回冷却，重复finish不重复计数；所有fixture析构后预算/lease/timer归零，整组FD前后相等。 |
| 05 端到端 | 正式ai-inference-gateway测试未知404/全摘除503稳定error.code、每请求最多一次派发；已提交流截断只有一份HTTP状态且无成功零块；未提交上游错误/timeout仍由旧GatewayE2E/Runtime等回归保持。活动Trial流与另一实例idle同存时SIGTERM有限退出0，客户端和服务线程finally关闭；恢复循环每实例3次。 |
| 06 交付 | 三预设17/17，新增277/183实际计数，14文件格式与人工检查，README新配置/被动恢复/协议健康局限、独立示例、源/二进制/历史保护清单齐备。当前为Builder待审，未替代Reviewer接受或Leader状态收口。 |

## 自检失败与纠正记录

E/routing-lifecycle-001.log保留第一次门控测试失败：测试把pending connect立即投递EPOLLOUT，导致进入response期限而非目标total路径；修正fixture仅在非pending时投递OUT，002通过。E/ctest-debug-001.log保留16/17失败：新增body上限中立断言揭示上述统一502分类缺口；类型化分类后debug-002/release-001/asan-001均17/17。

一次追加测试脚本因插入点不匹配抛ValueError，未把计划的跨模型池/Trial容量断言写入；随后交接前源码审计发现并纠正，明确撤回先前进度中“已补齐”的说法。最终文件确实包含并由routingLifecycleChecks调用trialAndCapacityChecks/runtimeIsolationChecks/leastInflightIdleChecks；routing-lifecycle-003通过，然后冻结并重新完整执行三套final。中间通过不冒充覆盖后来补齐的测试，所有旧日志保留。此为初次实现自检内纠正，尚未交付后的返工，0/2不变。

## 身份与保护

E/source-final-sha256.json覆盖src/tests/config/third_party及CMakeLists/CMakePresets/.clang-format共88项，SHA256 `a2a8ec791c58a9ae97d770031801203bcf217ae0b29b1d3550cc66ba210186e7`。E/binaries-final-sha256.json共39项（每套10可执行+3静态库），SHA256 `e4368c45f61460cba1c098cb8572468cb1722be3807f4bd7f61d4da67057dc95`。测试前后最终文件身份重新核验一致；不把39产物数混作17测试入口。

E/identity-audit.json比较Leader planning-protected161项：150项原样，11项是本阶段CMake及5组既有C++模块文件的批准改动。旧tests、third_party、默认样例、P1和历史docs全保持。三份权威SHA分别为设计`8f3aeeee2d137bf484a008630021218da418824f5dfefa2edc05bc61e1a64740`、审查`79e390d108d1686056956462e01bd3b6ad3f49f2876998dae0364281f6dceafc`、Leader001 `b3676ba2eb6cecb4d102b2873331e9fc0bba4c5420c0ab346917216202a161fc`。

## 待独立验证与限制

没有已知未实现的设计功能或待接收债项；Reviewer特别核查typed解析失败、本地保护中立、旧epoch/多idle/Trial取消与stop生命周期，以及本报告逐AC和实际断言的对应关系。测试host只做内部观察，真实模型/GPU健康和综合多实例部署不属于S1验证；不宣称性能收益或MVP完成。用户配置的初始Available和完整2xx只代表协议级健康，完整2xx业务错误/生成语义不识别。

自有网关子进程均communicate等待退出，backend线程join，fixture资源及FD检查通过；没有保持后台负载。剩余工作为独立Reviewer验收和Leader收口，协调者随后精确暂存本地提交，不推送。
