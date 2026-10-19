# V0.1/S3 Reviewer 初次审查报告 001

日期：2026-10-19；Reviewer (Athena)。结论：**FAIL（仅规范性 Minor，功能验证通过）**。S3初次审查、提交审查时返工0/2；协调者将本项纳入第1轮有限纠正。没有Major/Blocker功能发现，不是环境阻塞，没有接受技术债，不宣称阶段完成或Git发布。

## 1. 权威、路线与独立性

完整读取Approved S3设计/审查计划、Leader001、Builder001、S3变化记录，及S2 rework-002/Reviewer002；核对README/ROADMAP/ARCHITECTURE中阶段范围、模块、资源、停止与后续能力边界。遵循用户全局AGENTS、agent-execution-route、personal-cpp-standards完整规则/正反例，项目无Reviewer指南，使用plan-project-docs全局Reviewer模板并向协调者披露。未派生代理，未修改产品、测试、第三方、兄弟仓库、权威或历史报告。

继续原生WSL2 `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`；分支 `codex/v0.1-s3-connection-reuse`，HEAD `3cb65244312d2feef563c2fd755ae8447d4589c5`。独立构建、临时、缓存、日志和自有进程均在 `build-local/reviewer/s3/`，设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME。已知loopback/LSan边界的精确测试命令直接申请窄权限执行；未跳过、关闭sanitizer或安装依赖。

证据前缀 **E = `build-local/reviewer/s3/evidence/`**。Reviewer独立编译产品，不使用Builder二进制运行验收。identity-audit.log逐一校验Builder的51项产品/测试身份，与当前一致；Release独立产物SHA256也一致。批准包：

- S3-design SHA256 `2d41cb66f20750105e81dba0b6f7c1b5bce694aee0998290c100f7603a92a127`。
- S3-review SHA256 `ca8d3c1dc62809f728aaed083b660c13ff614e678e8dcfd6f703ab6e140e826e`。
- 独立源码集合 E/source-sha256.json SHA256 `b64077d48f2fb5b47867ce5d0cd18848a800529ebb6c31c813bdc8f7bb431931`。
- 独立Release二进制 SHA256 `9313a0eaf12986693ee4f89e4994213d26bcf724a19acf8acefbf797f0d71700`。

## 2. 唯一发现与结论适用

**S3-F-001 — Minor：新增函数缺相邻定义间空行，人工规范复核声明不准确。**

- 位置：`src/app/GatewayConfig.cpp:77–78`，readTimeouts结束的 `}` 后直接开始 `void readPool(...)`。
- 权威：personal-cpp-standards“C++代码排版与工具”明确要求 `.cpp` 相邻函数定义间一个空行；S3 REQ/AC-07、RV-07要求工具检查及人工分组复核。
- 期望：两函数之间保留一个空行；Builder报告的人工检查结论应与实际文件一致。
- 实际：没有空行；Builder001声称12个文件人工复核已通过。clang-format-18 dry-run仍退出0，该工具并不覆盖这条人工要求。
- 复现：`nl -ba src/app/GatewayConfig.cpp | sed -n '72,83p'`；无需运行时输入。影响仅规范/交接证据准确性，没有行为、所有权或协议影响。
- 处置：Builder补一空行，更新S3变化记录中该文件当前hash和新增报告；保持历史报告及Approved设计原字节。独立复验身份、差异确实仅空白、格式及必要增量构建，功能证据可明确复用本次不变语义基线。无需重复18cell成本矩阵。

全局模板把FAIL定义为Major/Blocker、BLOCKED定义为环境阻碍，但同时规定Minor要纠正或明确接受，对“仅未接受Minor”存在结论枚举缺口。已向协调者报告该冲突；协调者明确要求本次采用 **FAIL（仅规范性Minor）**，列入S3第1轮有限纠正、不转债。此处保留真实严重度，不将单空行抬高为Major，也不自行批准PASS WITH DEBT。产品功能的独立通过证据不因该结论被改写为失败。

## 3. 逐项独立验收

| 审查/AC | 结果与具体证据 |
| --- | --- |
| RV/AC-01 所有权 | 功能通过。审查ConnectionPool全实现、Channel/EventLoop分发/cleanup、ProxySession/Runtime成员析构顺序。池唯一持有Socket/Channel，租约move-only且归还/失效先清空句柄；ID/generation与fd/token分离；idle/leased转换注销再注册。分发复制租约回调，退休对象只在回调返回后cleanup销毁。PoolTests实际注入旧leased/idle token、旧timer、回调内失效、move与双失效；独立探针额外验证两个活租约move assignment、generation/ID耗尽不回绕、timer分配失败撤销租约和FD/计时器回滚。三预设和独立ASan均无诊断。 |
| RV/AC-02 容量与配置 | 功能通过。readPool保持原配置合法，默认16/16/5000；错误类型/重复/未知键、范围、默认组合、max_idle=0断言通过。实际2槽、第三合法请求503 upstream_capacity且后端日志无该marker，之后请求恢复；idle=1不驱逐leased。有效Entry≤N，acquire前有效+退休<2N，最多新增1，因此合计≤2N；retired预留2N且不持FD，回调后清空。独立探针N=1在同一清理窗口两次退休后第三次拒绝创建，cleanup后恢复。 |
| RV/AC-03 消息和资格 | 功能通过。真实ReuseE2E七类合法响应（CL/chunked/1xx/204/304/400/500）各20独立下游、唯一marker、仅1上游；并发marker不交叉。close多字段大小写、EOF、同块尾随、持有期迟到、idle迟到、截断及旧协议回归通过。源码原始头判定、显式requestWriteComplete、consumedBytes/EOF和事件mask共同限制归池。独立探针补阻塞/部分上传、同轮HUP/ERR、完整响应后RDHUP/ERR和下游写期限失效，首响应保持或按期限结束。SHUT_WR前持有、EINTR暂不归还、成功后旧closing RST不影响下一租约由Runtime接缝和真实closing_isolation共同证明。 |
| RV/AC-04 陈旧和期限 | 功能通过。idle只IN/RDHUP，无OUT；固定deadline，归还及租出均SO_ERROR+非阻塞1字节peek，32次EINTR预算。Pool测试data/EOF/硬错/SO_ERROR/EINTR耗尽逐出、有限EINTR后EAGAIN可用、过期项不出借；真实FIN/RST/迟到/10ms过期后下一请求新建。已借出首write失败502、connectCalls/created及sentUpstream证明不换连接重发，后续可恢复。新租约response从新connectedAt起算，total不刷新，已独立运行10/30ms可控时钟边界。 |
| RV/AC-05 停止和资源 | 功能通过。首次停止先stopAcquisition关闭idle、监听；未派发合法请求503 gateway_stopping，已有租约不抢占，归还时关闭；第二信号/截止终结并清池。真实Runtime20轮快照：closing仍active1/reserved16MiB，已归池idle1/timers2；客户端关闭后active/reserved0、idle1/timer1；SIGTERM后包含retired的计数全0。真实GatewayE2E活动/不完整请求/closing及热输入公平停止保留，ReuseE2E补有idle时未派发和二次信号。原120/150ms关闭窗口20/20通过。事件外直接requestShutdown仍不是SDK，未作为产品停止替代验证。 |
| RV/AC-06 初始成本 | 功能通过。独立Release完整固定18cell，360预热+3600测量均精确正文/状态、0失败/拒绝；close每cell220接受/220请求，reuse并发1累计1连接、并发4累计4。原始分布/计数/采样/进程配置完整；独立重算nearest-rank三个分位数与JSON一致。详见下节。 |
| RV/AC-07 回归和证据 | 构建、三预设9/9、Release负控、第三方/历史来源、README实际启动全部通过；唯一未满足项S3-F-001人工排版。根文档当前尚未标记S3已验收，后续生命周期同步由Leader完成。 |

源码检查覆盖全部S3产品修改和新增测试/脚本：GatewayConfig、ConnectionPool、ProxySession、SessionIo、GatewayRuntime，RuntimeTests/PoolTests/GatewayE2E/ReuseE2E、PersistentBackend/ReuseHarness/ProxyBaseline及CMake/示例；并追踪未改的EventLoop/Channel/TimerQueue提供的回调和定时器保障。没有扩大到SSE、多后端、队列或重试。测试计数只索引实际执行，不能替代上表的输入/状态覆盖。

## 4. 独立命令和结果

所有构建/Python前：

```bash
export TMPDIR="$PWD/build-local/reviewer/s3/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/reviewer/s3/cache"
```

每mode单独检查退出码（debug/release/asan）：

```bash
cmake --preset "$mode" -B "build-local/reviewer/s3/$mode"
cmake --build "build-local/reviewer/s3/$mode" -j 4
ctest --test-dir "build-local/reviewer/s3/$mode" --output-on-failure
```

E/{mode}-configure.log与{mode}-build.log均exit0；E/{mode}-test.log均exit0，Debug9/9 12.72s、Release9/9 10.40s、ASan+UBSan9/9 23.34s。没有跳过测试或禁用LSan。

其他命令：

```bash
build-local/reviewer/s3/release/FoundationTests --intentional-failure
python3 tests/ProxyBaseline.py --gateway build-local/reviewer/s3/release/ai-inference-gateway --output build-local/reviewer/s3/evidence/baseline.json
python3 build-local/reviewer/s3/evidence/CloseWindow.py build-local/reviewer/s3/release/ai-inference-gateway
clang-format-18 --dry-run --Werror src/app/GatewayConfig.{h,cpp} src/gateway/{ProxySession,GatewayRuntime,SessionIo}.{h,cpp} src/upstream/ConnectionPool.{h,cpp} tests/{RuntimeTests,PoolTests}.cpp
build-local/reviewer/s3/evidence/IndependentProbe
build-local/reviewer/s3/evidence/IndependentProbeAsan
git diff --check
```

负控exit1符合预期（E/release-negative.log）；其余exit0。E/close-window.log记录20次105字节完整首响应、FAILURES 0 OF 20；复制的原CloseWindow.py SHA256 `158de752e714596bbdacf5e0e5c351d098d74239faf95d3b7f4d63ec8b58b425`不变，未改120/150ms。格式E/format.log为空成功，但人工发现单空行缺失如上。README实际使用独立Release与config/example.json启动为READY127.0.0.1:8080，SIGTERM退出0（E/readme-smoke.log）。

独立探针E/IndependentProbe.cpp复用RuntimeTests已有FakeIo/会话夹具，但main为Reviewer新增攻击断言，不重复Builder main当独立设计；真实Socket/FD用于资源计量，协议IO与时间通过接缝控制，不冒充真实TCP异常。Debug与ASan/UBSan均28 checks，E/probe.log、probe-asan.log。编译使用自有静态库、`-std=c++20 -g -I src -I tests -I third_party/llhttp/include`，链接gateway_runtime/gateway_foundation/llhttp及pthread；sanitizer额外`-fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie`。首次探针编译两次因Reviewer相对include路径及缺llhttp include失败，E/probe-build.log/probe-build-corrected.log保留，修正仅自有探针/命令；最终E/probe-build-final.log/probe-asan-build.log成功，未改产品以获得通过。

Builder原始ASan失败已核查：ReuseE2E显式信号停止后finally再次发送信号造成进程-15，没有sanitizer诊断；现有代码显式wait自然结束、close仍要求exit0且检测sanitizer输出，没有放宽状态/时间断言。本轮独立三套使用现有夹具均通过。

## 5. 成本审计与观察边界

E/baseline.json及baseline-cells-*保存所有配置、原始样本、后端连接marker日志、10ms资源采样、before/after计数与清理结果。矩阵串行在完整功能回归后运行；每个cell客户端固定436字节请求（content256 ASCII），1024字节JSON响应，closed-loop并发1/4、20预热+200测量、三重复并轮换模式。保留预热池，不重启清空reuse计数。

| 模式 | 并发 | 三次QPS范围 | 三次端到端P99 ms范围 | 含预热的后端accept |
| --- | --- | --- | --- | --- |
| direct-close | 1 | 698.8–917.4 | 1.900–2.354 | 220/220/220 |
| proxy-close | 1 | 404.1–480.3 | 3.074–3.842 | 220/220/220 |
| proxy-reuse | 1 | 644.0–937.7 | 1.894–2.319 | 1/1/1 |
| direct-close | 4 | 1471.6–1524.9 | 4.136–17.827 | 220/220/220 |
| proxy-close | 4 | 1238.9–1366.9 | 4.827–5.185 | 220/220/220 |
| proxy-reuse | 4 | 1934.9–2423.2 | 2.586–3.173 | 4/4/4 |

所有cell网关/后端正常回收且监听不再可连接。网关FD观察峰≤初始FD+16下游+16上游+1临时accept；Runtime精确池/会话计数测试为补充，不能把采样外推成严格实时峰。direct无网关。一次direct并发4出现17.827ms P99，原样保留，未选择性重跑。这里只是合成Python后端、WSL调度、新建线程、采样等共同影响的初始分布，不代表真实推理/生产收益；不以两组P99相减声称额外延迟P99，不设置事后收益阈值。

## 6. 交接、未验证与限制

没有契约内功能未验证阻塞项或新增功能技术债建议；仅S3-F-001待有限纠正，Reviewer不代Builder补空行，不代Leader同步阶段。推荐后续复验只检查该差异、更新来源身份/报告、格式与必要构建；若修改扩展到行为，再按实际影响补回归。

peek只能保证当前可探测污染，不能预测未来断线/识别恶意后端未来伪响应；单线程受限HTTP子集、下游单请求、无重试边界保持。独立sanitizer和有限回环实验不等于任意网络/生产压力保证。原始证据存gitignored目录，不意味着已远程发布。最终状态由协调者/Leader在纠正且接受后同步。
