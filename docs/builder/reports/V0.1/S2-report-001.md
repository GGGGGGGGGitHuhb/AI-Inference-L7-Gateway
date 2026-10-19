# V0.1/S2 Builder 初次实现报告 001

日期：2026-10-18。Builder (Hephaestus)。S2 初次实现、累计返工 **0/2**；S1 历史 2/2 保持。本报告提交实现与自测证据，等待 Reviewer 独立审查，不代表阶段验收或发布。

## 权威、路线和范围

完整读取 Approved [S2 设计](../../../leader/designs/V0.1/S2-design.md)、[审查计划](../../../reviewer/reviews/V0.1/S2-review.md)、Leader S2-report-001、根架构/路线及适用技能。没有项目 Builder guide，使用 plan-project-docs 的 Builder guide 模板回退；执行 agent-execution-route 和 personal-cpp-standards 规则及正反例。

分支 `codex/v0.1-s2-proxy`，HEAD `bb318d8c55f5851d27cd52e6cd3367f450a5d8dd`。原生 WSL、`/bin/bash`、login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`。GCC 13.3.0、CMake 3.28.3、clang-format 18.1.3。没有网络下载、全局安装、提交、推送、标签或兄弟仓库修改。

Approved design SHA256 `a8d0206472e85bbb8facc5ba668c1aa4964803f48d7737cca659855aafc9de51`；review SHA256 `c8ad195e1c0a75155f91912179dc92bcd9187bf281329a063ef49b733a63c471`。最终身份清单见 evidence/handoff-identity.log 与 source-sha256.txt；保留 Leader 的根规划和权威文件，不将其工作计为 Builder 实现。

新增 src/app（配置、信号、main）、src/gateway 的 GatewayRuntime/ProxySession/SessionIo、六个 src/net 事件文件、config/example.json、RuntimeTests/GatewayE2E/ProxyBackend；修改 CMake 和 HttpNormalization 的 close 策略、README 事实；新增 S2 breakdown、复用 md/json 和本报告。原 S1 测试、第三方及历史文档没有改动。

## 实现与验收追溯

| REQ/AC/RV | 实现与具体验证 |
| --- | --- |
| 01 来源/事件 | 固定 Server 六文件迁入，保留 token 查表与回调后 cleanup。RuntimeTests::EventFixture 验证同批删除另一 Channel、注销旧 token、自身回调返回后析构、eventfd/dup2 实际 fd 数字复用、token 耗尽、timer 取消/到期；来源逐文件重算 |
| 02 配置/启动 | 单静态 IPv4、严格重复键/未知键/类型/数值/自连接校验，读取前限制 64KiB；RuntimeTests config 验证 65535/65536/65537 和合法上下界；E2E config_cases 覆盖 CLI、缺字段、重复嵌套键、布尔/浮点、端口/地址/容量/timeout 错误，exit2 无 READY；occupied bind exit1、help exit0 |
| 03 代理/协议 | 全请求 HTTP+JSON 验证后新建单上游；改 Host、移除认证和 hop-by-hop、Via、CL、close。真实 E2E 固定/合法 BWS chunked/EOF/1xx/204/304/400/500/471/599/分片、900k 早期 413、最大 1MiB 请求慢上游、4MiB 响应慢下游；请求正文逐字节比较；坏请求/Expect 上游 accept=0；同批/跨批 pipeline 仅一条上游 |
| 04 IO/生命周期 | SessionIo 确定性 EINTR、7字节短写、EAGAIN后恢复、连接 SO_ERROR、早期响应、完整 SHUT_WR、截断EOF、上下游RST、bad_alloc；空输出移除OUT。真实 E2E 完整请求半关闭、取消后健康请求；Runtime 实际会话结束后 sessions/reservation/upstreams/timers 全0，整组 fd 数恢复 |
| 05 资源/公平 | 构造 parser 前预约16MiB、连接数/预约双门槛，超限直接关新fd；Runtime N−1/N/N+1、两连接容量/单槽预约及释放；E2E 超限响应502、慢读边界与热额外输入下另一请求408，原请求200且上游仅1次；实际存储推导见下表 |
| 06 deadline/停止 | acceptedAt/连接阶段/连接成功固定起点，最早 deadline，不因IO刷新。确定性 request/connect/upload/response/downstream/total、多个已过期deadline选择最早者、未发头 total504、已发头只关闭、错误排空999/1001ms不重建。真实请求/响应/total timeout、成功/拒绝连接；SIGTERM正常排空、shutdown到期、第二信号强制、退出后端口关闭 |
| 07 工程回归 | Debug/Release/ASan+UBSan完整7项，S1全回归、manifest、主动失败负控；实际clang-format18与README示例启动。初次失败日志保留；本报告和复用清单独立新增 |

单线程 LT；每事件最多接收32连接，每方向每次IO最多64KiB、最多64次调用，读缓冲16KiB。无待发数据时移除OUT；上游读写并行观察，早期最终响应先完整校验后停止上传。后续客户端输入只进行有界丢弃，既不保留也不再次派发。Channel 对象保留到 Runtime cleanup，finishSession 幂等注销/关fd/撤timer。

错误在未输出时生成受控 JSON；进入独立错误排空后仅保留一次 min(downstream_write,1000ms) deadline。无空间生成错误时关闭；不记录 prompt、正文或凭据。signalfd 处理阻塞的 SIGINT/SIGTERM，未引入异步 signal handler。

## 16MiB 单会话逻辑预算

这是设计要求的有效数据/临时副本逻辑字节上界推导，不是 RSS、allocator 容量或系统 socket 缓冲测量。配置只在进程启动解析，最大64KiB，不按会话重复保存。每会话两个 Socket/Channel、一个 timer 和固定状态另有有界元数据。

| 同时存活阶段 | 保守计算 |
| --- | --- |
| 接收/JSON校验 | 请求正文、SAX lexer字符串、已见key集合、各层当前key、模型metadata及结果副本、错误/临时字符串分别按整个1MiB输入保守分配共7MiB；HTTP头/URL/chunk行/16KiB栈及容器元数据再预留1MiB，合计≤8MiB |
| 请求规范化 | SAX局部对象已释放；正文≤1MiB + 请求输出≤1MiB+64KiB；头/临时拼接/hop集合/栈和固定状态保守预留1MiB，≤3.0625MiB；随后销毁requestParser |
| 上游接收/早期最终响应规范化（峰值） | 尚未发完请求输出≤1MiB+64KiB + responseParser正文≤4MiB + 规范化响应≤4MiB+64KiB + 所有头/临时拼接/集合/chunk行/16KiB栈/固定状态保守预留1MiB，≤10.125MiB |
| 下游排空 | responseParser、请求输出、上游socket均已释放；响应输出≤4MiB+64KiB，或先清理大对象后的受控错误小串；加1MiB保守余量≤5.0625MiB |

因此同时逻辑存储保守≤10.125MiB < 16MiB。HTTP头总量16KiB、起始行4KiB、chunk行1KiB，逐字节先检查原协议预算；规范化前 checkOutputBudget 从1024固定头余量起逐项计数，正文和所有头合计先检查≤bodyLimit+64KiB，再生成输出。normalizeMessage 逐个 header 临时拼接，正文 append 不复制第三份整正文；返回string move。并非把各阶段峰值相加。SAX 不构建DOM，最大1MiB输入约束所有key/string总内容，容器固定条目开销有限；本表1MiB额外元数据余量远大于HTTP固定100头/32深度/8192 JSON项等约束。

max_connections 默认16、max_reserved_bytes 默认256MiB，预约在 parser 构造前增加；失败回滚，callback后清理只扣一次。预算拒绝不会创建parser/上游/等待队列。达到上限后的接入与释放由两套实际 socket 测试验证；不把RSS作为本项验收证据。

## 可复现命令与结果

所有 Python/构建/测试前设置（目录已 mkdir -p 建立）：

```bash
export TMPDIR="$PWD/build-local/builder/s2/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/s2/cache"
cmake --preset debug -B build-local/builder/s2/debug
cmake --preset release -B build-local/builder/s2/release
cmake --preset asan -B build-local/builder/s2/asan
for variant in debug release asan; do
  cmake --build build-local/builder/s2/$variant -j 4
  ctest --test-dir build-local/builder/s2/$variant -V
done
find src tests -type f \( -name '*.h' -o -name '*.cpp' \) -print0 | xargs -0 clang-format-18 -i
find src tests -type f \( -name '*.h' -o -name '*.cpp' \) -print0 | xargs -0 clang-format-18 --dry-run --Werror
build-local/builder/s2/release/FoundationTests --intentional-failure
build-local/builder/s2/debug/ai-inference-gateway --config config/example.json
```

格式化完成后重构建三套，再完整测试。最后测试夹具增加清理保障/实际耗时打印后再次完整三套，最终以 `*-ctest-handoff-02.log` 为准。前三个 preset 配置、三套最终构建 `*-build-verified.log` exit0；所有测试会创建自身本地socket，因此沿已知边界窄范围升级执行，未跳过socket或用Reviewer实例。

| 构建 | 最终结果 | 主要检查 |
| --- | --- | --- |
| Debug | 7/7、exit0、7.66s | Runtime121；真实E2E400；Foundation33；Protocol76848 |
| Release | 7/7、exit0、5.26s | 相同；AssertionFailure预期失败验证NDEBUG不吞检查 |
| ASan+UBSan | 7/7、exit0、17.52s | 相同；未报告sanitizer错误 |

其余CTest为MockBackend五场景及Manifest逐文件散列。计数只是日志索引，覆盖以表中具体输入、测试源码和原始日志为准。Release直接 `--intentional-failure` exit1；README原样启动输出READY127.0.0.1:8080，SIGTERM后exit0，输出无敏感内容。格式dry-run exit0，git diff --check exit0。

所有原始证据根目录：`build-local/builder/s2/evidence/`（gitignored、本机持久保留）。最终：`debug-ctest-handoff-02.log`、`release-ctest-handoff-02.log`、`asan-ctest-handoff-02.log`、`*-build-verified.log`、`format-verified.log`、`readme-smoke.log`、`release-intentional-failure.log`、`provenance-verified.log`、`handoff-identity.log`、`source-sha256.txt`。CTest日志含真实request/shutdown elapsed_seconds；精确罕见deadline由fake monotonic clock推进验证，不依赖黑洞路由。

## 初次失败与当前边界

初次 `runtime-initial.log` 暴露测试fixture Content-Length 57/实际56错误，已修为56；`runtime-02.log` 暴露connect返回时accept可能尚未就绪，改为有界poll等待而保留容量断言。`e2e-expanded.log` 的早期响应fixture未读完请求即close产生RST，改为发送响应后SHUT_WR并有界排空；产品写失败路径也先尝试读取已到达早期响应。后续runtime-03/04、e2e-expanded-02及完整三套均保留。最后强化Python finally时曾缩进错误，原输出 `python-cleanup-edit-initial.log` 和修复编译 `python-cleanup-edit-verified.log` 保留，之后三套完整复验。

最终夹具清理后，`asan-ctest-handoff.log` 曾在热输入首响应200断言失败：原后端120ms返回而客户端持续写150ms，测试窗口跨越响应完成关闭。当前后端延迟400ms、热输入仍150ms，保留另请求408、首响应200、仅一次上游全部断言；没有更改产品关闭语义。原窗口诊断副本 `tmp/old-window-diagnostic.py` 运行到第5次时观察空响应（`old-window-diagnostic.log`），符合继续写入跨越close而被RST的时序解释，但没有抓包证明其内核原因；请Reviewer独立判定该窗口与设计§5“全部输出进入Socket后关闭”的边界。调整后3次ASan E2E均通过（`asan-e2e-timing-1/2/3.log`），三套完整复验记录独立存放。

目前没有已知未实现的S2项或请求变更验收语义。接缝测试证明罕见系统调用分支，真实loopback证明链路，两者互补；没有生产流量/性能结论。无SSE、连接池、重试、路由、排队、GPU、L4LB联调或S3实现。需要Reviewer独立审查，尤其预算推导、生命周期及协议边界，Leader随后决定是否收口。
