# V0.1/S2 Reviewer 复验报告 002

日期：2026-10-18。Reviewer (Athena)。结论：**PASS**。本次 S2 第1/2轮返工复验，累计1；S1历史不变。原报告001及失败证据保留。最终阶段状态由 Leader 同步，本报告不宣称提交、推送或发布。

## 1. 权威与独立性

基线为 Approved S2-design（SHA256 `a8d0206472e85bbb8facc5ba668c1aa4964803f48d7737cca659855aafc9de51`）、S2-review（`c8ad195e1c0a75155f91912179dc92bcd9187bf281329a063ef49b733a63c471`）及 rework-002（`fd8165b4251ca748f179fa9a683fb05ec35588ba7db90823f1f3f5a70a3bdbcf`），本轮重新计算一致。读取 Leader002、Builder002、旧 Reviewer001与现有实现。沿用 agent-execution-route、personal-cpp-standards规则/示例和 plan-project-docs 全局 Reviewer模板回退；项目无专用指南。

路线：原生WSL `/bin/bash` login=false，仓库 `/home/power/projects/AI-Inference-L7-Gateway`，分支 `codex/v0.1-s2-proxy`，HEAD `bb318d8c55f5851d27cd52e6cd3367f450a5d8dd`。自有构建/进程/临时目录全部在 `build-local/reviewer/s2/`。未改产品、测试、第三方、兄弟仓库、权威或历史报告，未派生代理。已知Socket/LSan限制使用精确动态测试命令升级，无跳过。

以下证据前缀 E = `build-local/reviewer/s2/evidence/`，均为本轮新文件。首次报告的完整代码审查继续适用；本轮重点逐段审查新增closing、系统调用接缝及所有相关测试，重新检查迁入事件循环、停止入口和排版范围。

## 2. 发现关闭

| 发现 | 原严重度 | 结果与证据 |
| --- | --- | --- |
| S2-F-001：额外输入跨关闭窗口丢首响应 | Major | **关闭**。原 CloseWindow.py 字节不变，SHA256 `158de752e714596bbdacf5e0e5c351d098d74239faf95d3b7f4d63ec8b58b425`；原120/150ms条件独立20次均完整105字节、0失败，E/r1-close-window.log。新增独立握手正常200正文abc、错误400完整JSON，长度与单状态行匹配，上游分别1/0；收到服务器EOF后仍成功发送12000额外字节，再SHUT_WR。E/ClosingHandshake.py、r1-handshake-final.log。 |
| S2-F-002：函数间空行/职责分组 | Minor | **关闭**。人工复核app配置/信号/main、ProxySession/GatewayRuntime/SessionIo、EventLoop/Channel/Epoller、HttpNormalization及RuntimeTests；相邻定义空行、访问标签与头文件分组已补齐。非简单FakeIo shutdown和SessionFixture构造在类外；简短getter保持同行组。clang-format18 dry-run与diff-check均0，E/r1-format.log、r1-diffcheck.log。 |

没有新增契约内发现，没有接受技术债务。独立握手脚本初次误把错误JSON预期写为只有code，随后还曾误选invalid_request；失败属于Reviewer夹具预期，未改产品。E/r1-handshake.log、r1-handshake-corrected.log保留；最终按S1契约精确比较 `{"error":{"code":"invalid_http","message":"Request rejected"}}` 后通过，不能用最后通过覆盖早期失败历史。

## 3. REQ/AC/RV与返工验收

| 项目 | 独立判定 |
| --- | --- |
| 01 构建/依赖/来源 | 三套重新构建及完整CTest各7/7；固定git show校验六Server来源与两个S1规范化来源，source/target八项全部匹配。Manifest测试通过，第三方未改。E/r1-provenance.log、r1-source-sha256.txt。 |
| 02 启动/配置 | 原配置非法输入、CLI、自指、类型/重复键断言仍在完整E2E内；README配置用Reviewer二进制实际READY127.0.0.1:8080、SIGTERM退出0，E/r1-readme-smoke.log。 |
| 03 单上游及首响应 | 原协议/规范化/真实E2E回归通过；closing不重建上游，错误路径也统一半关闭。独立原反例和握手见上表，第二请求不派发。 |
| 04 所有权/取消/异常 | 最后send后beginClosing记录一次完成时刻，释放解析器/输出/upstream；shutdownWrite只成功一次，失败或EOF适当finish。closing异常不能因offset归零再生成错误。Channel仍在回调后cleanup删除，单调token忽略旧事件。RuntimeTests覆盖读异常/RST、EOF先到、EAGAIN保留、关闭后事件/计时重复触发。 |
| 05 资源/公平 | closing保留active与16MiB预约，到cleanup归还；仅一会话timer，额外输入16KiB栈块丢弃、每方向64KiB/64次边界不变。Runtime实际Socket记录closing active1/reserved16777216/timer1/upstream0，EOF/首次停止deadline/第二信号后三种均active/reserved/timer/upstream0。热输入真实E2E证明固定期限与其他请求/计时器推进。原保守逻辑缓存推导约10.125MiB仍低于16MiB预约；并非RSS上限。 |
| 06 截止/停止 | 人工检查nextDeadline对closing取min(total,完成+1s)，错误取min原errorDeadline且不再套过期total；活动不刷新，downstream_write完成后不再约束。可控IO70次EINTR第一回调63次shutdown+1send、下回调完成，900ms延迟重试不重置1s；harderror立即终结。正常total400ms、错误输出耗800ms剩200ms、total触发错误窗口、EOF先到及异常均有具体断言。实际signalfd首次50ms/第二信号清零，真实E2E停止退出。 |
| 07 回归/规范 | Debug/Release/ASan+UBSan各7/7，未删S1测试；Release主动失败exit1。人工分组检查与格式检查相互独立。 |

Runtime详细独立输出见 E/r1-runtime-detail.log（242 checks及三种closing stopMode归零）。测试计数仅作索引；上述状态、输入、顺序和期限的源码/断言审查才是覆盖依据。真实Socket与可控时钟证据分开，不宣称已观测TCP包序列。

## 4. requestShutdown直接调用的调查与范围

独立探针 E/DirectShutdown.cpp 在同一owner线程、事件回调外两次调用requestShutdown，然后pollOnce，得到 `active=1 reserved=16777216 upstream=0 timers=0`（E/r1-direct-shutdown.log）。因此Builder披露的观察真实存在，不能说所有内部调用方式都立即清空快照。

源码原因：第二次forceShutdown把会话finish并关闭Socket/注销Channel，EventLoop停止；wake事件不触发业务cleanup，map对象与预约计数留到GatewayRuntime析构。析构明确clear会话及预约，没有跨进程泄漏。实际产品main仅startListener/runGateway，受控停止入口为onSignalEvent→requestShutdown，后续dispatchChannelEvent执行cleanup；shutdown定时器也经dispatchTimerTask执行cleanup。三种真实Socket/signalfd路径已独立验证归零。

判定：Approved §4/§8定义的产品停止接口是SIGINT/SIGTERM，没有交付可复用Runtime SDK或事件外直接调用的完整清理保证。因此这不是本阶段信号停止验收失败，也不是用真实信号替换测试来遮蔽产品可达路径；本报告仅接受该进程契约。内部public方法可被误用仍是明确使用限制，未来若暴露嵌入式Runtime接口，应先定义并验证事件外终结清理，不可沿用本报告声称该用法通过。未擅自为此扩展本阶段需求或接受债务。

## 5. 可重现命令与结果

所有命令前显式环境：

```bash
export TMPDIR=$PWD/build-local/reviewer/s2/tmp
export TMP=$TMPDIR TEMP=$TMPDIR
export XDG_CACHE_HOME=$PWD/build-local/reviewer/s2/cache
for mode in debug release asan; do
  cmake --preset "$mode" -B "build-local/reviewer/s2/$mode"
  cmake --build "build-local/reviewer/s2/$mode" -j 4
  ctest --test-dir "build-local/reviewer/s2/$mode" --output-on-failure
done
python3 build-local/reviewer/s2/evidence/CloseWindow.py build-local/reviewer/s2/debug/ai-inference-gateway
python3 build-local/reviewer/s2/evidence/ClosingHandshake.py build-local/reviewer/s2/debug/ai-inference-gateway
build-local/reviewer/s2/debug/RuntimeTests
build-local/reviewer/s2/release/FoundationTests --intentional-failure
clang-format-18 --dry-run --Werror src/app/*.cpp src/app/*.h src/gateway/{ProxySession,GatewayRuntime,SessionIo}.{cpp,h} src/net/{EventLoop,Channel,Epoller}.{cpp,h} src/http/HttpNormalization.{cpp,h} tests/RuntimeTests.cpp
```

构建/配置均0，日志 E/r1-{debug,release,asan}-{configure,build}.log；CTest均0，各7/7，耗时9.37s、7.09s、19.96s，E/r1-{debug,release,asan}-test.log。原探针及最终握手exit0；负控exit1符合预期，E/r1-negative.log。来源使用Python hashlib重新计算目标及 `git -C <固定仓库> show <commit>:<source>`，八项逐一assert；源码集合身份存E/r1-source-sha256.txt。未联网或安装依赖。

## 6. 限制与交接

结论仅限S2受限文本单上游非流式代理与本次Approved关闭修正。20次反例回归不是任意网络可靠性证明；RST、固定期限或强制停止下不保证应用已消费全部响应。ASan/UBSan及本地回环验证不等于生产压力或吞吐保证。原失败日志保留，独立握手失败夹具说明如上。

建议Leader基于本PASS关闭两项发现并同步阶段状态；Reviewer未改根状态、提交、标签或推送。
