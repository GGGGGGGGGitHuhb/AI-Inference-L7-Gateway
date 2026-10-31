# V0.6/S2-trace Reviewer 报告001

日期：2026-10-31。最终验收结论：**FAIL**。

观察设施在第三项功能控制的正常收口中出现 fixture 被 SIGTERM 终止，关键前置未通过。AC2开销、AC3直接归因及AC4产品优化交接均未验证，保持 **BLOCKED**。这是工具交付失败，不是有效负面性能实验，也不是 Gateway/L4 产品失败的证明。

## 审查依据与范围

已读 Approved [设计](../../../leader/designs/V0.6/S2-trace-design.md)、[审查计划](../../reviews/V0.6/S2-trace-review.md)、[启动报告002](../../../leader/reports/V0.6/S2-trace-report-002.md)、[返工001](../../../leader/reworks/V0.6/S2-trace-rework-001.md)、[返工002](../../../leader/reworks/V0.6/S2-trace-rework-002.md)，以及 [Builder001](../../../builder/reports/V0.6/S2-trace-report-001.md)、[Builder002](../../../builder/reports/V0.6/S2-trace-report-002.md)。结合 ROADMAP/ARCHITECTURE 的既有边界审查，本轮不授权产品优化。

项目没有专用 Reviewer guide，回退读取 plan-project-docs 全局 Reviewer 模板并向 Leader 披露；同时读取 personal-cpp-standards 完整参考与 agent-execution-route。原生 WSL 工作区保持，所有独立 tmp/cache/build/evidence 在 `build-local/reviewer/v0.6-s2-trace/`，执行显式设置 TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX。回环回归采用窄权限执行，没有运行 XDP 压力、安装依赖或修改系统配置。

检查 GatewayRuntime、ProxySession、ConnectionTrace、CMake、诊断单元，新 Client/Backend/Decode/TraceRuntime/RunCell/Negative/ResetBackend/Matrix 及自测；L4仅检查本仓隔离副本与版本化补丁。外部实际 dirty 工作树275文件只读复制、逐文件hash核对；没有改外部源、旧capacity/capacity_diagnosis工具或历史证据。Reviewer没有修改实现文件。

## 独立构建、回归和静态结果

自有 `gateway-source` 与 `l4-source` 独立复制，不复用 Builder 构建状态；L4从外部实际文件复制后自行应用补丁。CMake均为 Release、BUILD_TESTING=ON、-j2；U的诊断开关OFF，O为ON且 unset CONNECTION_TRACE_DIR；L4 XDP及loader均OFF。自有 U/O Gateway、U/O L4 四套构建完成。

| 验证 | 独立实际结果 | 自有 evidence 日志 |
|---|---|---|
| Gateway U完整CTest | 21/21，41.55s | gateway-ctest-u.log |
| Gateway O完整CTest，含诊断单元 | 22/22，41.97s | gateway-ctest-o.log |
| L4 U相关TCP，CPP005 | 13/13，54.49s | l4-ctest-uninstrumented-005.log |
| L4 O相关TCP，CPP005 | 13/13，54.66s | l4-ctest-trace-005.log |
| 最终解析/清理自测 | 12/12，0.033s | python-selftest-final.log |
| 最终矩阵模拟自测 | 9/9，0.040s | matrix-selftest-final.log |
| 自有隔离fixture纯谓词 | 3/3，0.000s | fixture-selftest-final.log |
| 自写共享绝对清理截止mock | 临近及已过截止两情形通过，不重开12秒 | independent-shared-deadline-test.log |

实际命令形式：`cmake -S <自有源> -B <自有构建> -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON`，分别设置 `GATEWAY_CONNECTION_TRACE` 或 `L4LB_CONNECTION_TRACE`；`cmake --build <目录> -j2`；`ctest --test-dir <目录> --output-on-failure -j1`。L4 CTest精确选择 s2_net_unit、s2_tcp_integration、s2_reactor_state、s3_product_smoke、v03_health_unit、v03_health_checker、v03_health_tcp_product、v03_metrics_tcp_events、v03_metrics_tcp_product、v03_system_tcp、refactor_callback_lifecycle、v04_lifecycle_state、v04_shutdown_product。Python使用 `python3 -B tests/connection_diagnosis/{SelfTest,MatrixTest,FixtureTest}.py`，FixtureTest显式指定自有 TRACE_L4_SOURCE；最终测试前后工具hash一致。

另只读复核 Builder `gateway-sanitizer-o.log`：受影响路径 ASan+UBSan 7/7、30.47s；build.ninja实际含 `-fsanitize=address,undefined`，Debug、诊断ON。此项为审阅 Builder 证据，不冒称 Reviewer 重跑。所有测试通过事实都不替代真实功能控制的收口验证。

静态已确认：256B聚合记录、131071槽加256B头恰32MiB，固定数组不复用槽；默认编译移除观察点，O热路径不新增端点查询/时钟调用；接入异常互斥分类、提前结束后发布计数补偿、normal erase后移除时间及停止clear后补记录保持原清理顺序。L4健康在同一reactor线程同步执行，显式kind3探针记录，不增加锁。导出只在停止阶段设置独立SIGALRM十秒，分片独占创建且最大1MiB。关联只接受完整四元组与重叠生命周期的唯一候选，缺失/复用歧义保留unknown。

自有U Gateway SHA256 `a4e729016ffaa3b23f785eacefba5a4177a197b901b24cda1291f81d378c0ed1`、U L4 `dc4c217780a3bc189fc65b50ac83345cb2dee240b77269e30138c1dc2403b77e`，与自有S1产物完全相同；O分别为 `c73cb9328e26712e84aba1db3d3d3f64167114dee22a9e751878868e79465c54`、`75a71c0efb0a565fbe24c93139c978523cae6d5e864c6db3d3d1bf09287de092`。两次测试副本返工未改变产品二进制。

## 准备阶段失败与隔离测试例外

原始失败均保留：自有CPP002 L4 U的 metrics 测试失败 real created point；RW001增加五处真实连接的有界POLLIN前提。自有CPP003 U随后11/13，metrics失败于即时7字节断言；shutdown forced为pending=[0,65160]，属于TCP而非UDP。

Builder取得发送 EAGAIN/SYN_SENT证据；Reviewer独立从 shutdown 原始数据确认c2b=173768恰等于源173760+握手8，平台可表示源已耗尽，b2c差额65160与屏障相符。失败发生在正式第二SIGINT前，finally再次terminate产生的forced日志不能作场景通过证据。未推断初始EAGAIN的内核根因。

Approved RW002只给首条实际后端增加POLLOUT/SO_ERROR=0前提，并对deadline/forced持续有界补源、检查fresh阻塞/平台/双向未转发差额。16秒及每向16MiB上限保持，接受前再次检查；原7/11字节、all(pending)、deadline、第二信号、listener摘除和PID/FD断言均保留。最终CPP005相对前一隔离副本只改两份测试文件，未改产品或外部原测试；旧失败不被后续通过抹去。详见自有 `shutdown-readonly-analysis.md`、两个 l4-source-after-rework*.json 与原失败日志。

## 冻结与真实首停的独立审计

CPP005源摘要SHA256 `33073dc06c0177678b3594ff091b263aeea0d441c4257b31a737c7b789680807`；版本化补丁SHA256 `239af4f6d435229d810192bf7fb549ab9fd70b109f13373d567edac09c85c6c4`。采集前独立核对Draft、38个冻结输入、四二进制、源/隔离全文件集合、预算和空run，并给予条件性采集前放行；这不是阶段验收。

Builder实际使用 `manifest-frozen-001.json`，SHA256 **`502047b4ade0787b8a0da1b75f8778e0d55774dda9de0922f963ed8bdeaf83b0`**。测后独立核对其与provenance完全一致，Matrix.verify对工具、源、隔离L4全部输入、外部实际dirty文件、补丁和二进制再次通过。没有冻结后静默修改。

| 实际项 | 独立核验 | 保留状态 |
|---|---|---|
| N-connection-limit | 两客户端连接；唯一tuple对应Gateway outcome2，active1、reserved16777216 | complete |
| N-reservation | 两客户端连接；唯一tuple对应Gateway outcome3，active1、reserved16777216 | complete |
| N-peer-reset | 单完整ID及后端tuple匹配；L4首次观察上游侧2、errno104、SO_ERROR；reset-peer退出−15 | failed |
| 1920低档 | 九项未开始 | not_started |
| 3840高档 | 六项未开始，低档未解锁 | not_started |

Reviewer使用独立struct解析三个原始binary导出，核接入守恒、drop/重复/live计数、终态及导出时间，按客户端四元组/生命周期和后端完整ID重新关联。第三项虽有正确的reset观测，fixture非零退出不能被派生证据抵消，原result仍metrics=null，不补判PASS。证据 `builder-first-stop-audit.json` 保留全部run输入SHA，收口前再次核对未变；不是只复述Builder summary。

全轮 **3尝试、2验证、15未开始**，ledger为complete/complete/failed，无running，无重试或续采。四子PID **33777、33780、33783、33785** 均有退出记录且独立检查 `/proc` 已不存在；L4退出0，reset-peer退出−15，未触发deadline_killed，capture loss均0。无已发现遗留进程。L4原始日志和header均有导出证据，但控制器export_begin_ns为null，不将该空字段写作已观测的导出时间。

summary活动1.781080929秒，summary后closure为1.782314185秒；cell账本合计1.708549211秒。closure记录 **193012B** 是当时Builder evidence总量，不是后续交付最终大小。报告时只读复核为196969B，新增3957B派生证据；Reviewer当时自有evidence为231545B（不含随后新增本机收口记录）。具体快照见 `closing-evidence-bytes.json`。源副本、CMake构建及docs报告在evidence外，不混作运行证据。预算未触发，性能预算及性能门槛没有得到实测验证。

## 发现、严重程度及处置

**Major M1：功能控制正常收口不可靠，阻断观察设施验收。**

- 要求：设计§6/AC1及审查计划要求自有进程正常有界回收、功能控制通过后才采样；工具首错必须停止。
- 位置：`tests/connection_diagnosis/TraceRuntime.py` 的 `close_all()`、`Owned.close()`，以及 `ResetBackend.py` 的asyncio停止生命周期。
- 实际：close_all先批量SIGTERM，Owned.close在poll仍为None时再发SIGTERM，停止通知不是幂等。冻结首轮第三控制实际reset-peer returncode=−15，控制器正确将其记为失败。
- 可复核证据：冻结run/N-peer-reset/processes.json、result.json、日志、账本及上述独立审计；本轮禁止通过重新运行获得替代结果。
- 限制：源码的双通知路径是确定事实；现场没有记录两次信号投递及handler移除的精确时序。asyncio退出边界竞争与结果相容，但不能断言第二次TERM必然是现场致死根因。也不能把该问题归因为Gateway/L4产品关闭。
- 影响：第三项控制未完成正常收口；随后所有开销与归因采样失去前置条件。
- 处置：本轮严格首停，冻结工具不改、失败不替换。若后续另行授权有限返工，应验证唯一停止请求/幂等通知、退出边界竞争与全部PID回收，更新冻结身份并保留此次失败；不得直接忽略−15、放宽零退出要求或静默续采。

前期静态及mock测试未检出这条真实退出竞争，必须保留此局限。它不能作为已接受技术债，本报告不建议用PASS WITH DEBT绕过关键前置。

## 未验证项与最终判定

Reviewer矩阵 **未执行**：在Builder冻结工具出现已知真实失败后，Leader明确要求严格首停，不启动同一失败工具。Reviewer仅运行独立构建、回归、无socket确定性测试及只读原始审计；没有自有三控制或性能样本，不能冒称双角色复现。

- AC1观察设施：前置回归、源码保护和回收审计已完成，但真实第三控制失败，**FAIL**。
- AC2：九项低档开销对照未运行，未验证，**BLOCKED**。
- AC3：六项高档关联覆盖和主因比例未运行，未验证，**BLOCKED**。两种拒绝负控不构成生产瓶颈证据。
- AC4：没有有效未插桩前测基线、可信开销或高档机制证据，S2产品优化入口 **BLOCKED**。

本轮最终结论为 **FAIL**。后续状态文档应写明观察设施首错停止、性能数据为空及产品优化未启动；不得称取证成功、已定位主要关闭原因、性能提升或容量上界。Reviewer不修改根文档、不提交Git，交Leader按此结论收口。
