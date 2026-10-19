# V0.2/S2 Reviewer 独立初审报告001

2026-10-19；Reviewer (Athena)。结论：**PASS**。本阶段初审，累计返工 **0/2**。未发现需返工的产品、规范或来源问题，没有接受债项或契约内阻塞的未验证项。此报告提供独立验收结论；阶段状态同步和本地提交由Leader及协调者完成，不代表已经提交、推送或V0.2整体完成。

## 1. 权威、范围与独立性

已读取当前Approved设计、审查计划、Leader001、Builder001、breakdown、V0.2-S2变化来源，根状态中的当前范围及V0.2/S1 Reviewer002接受链。没有S2返工权威。适用用户AGENTS、agent-execution-route、personal-cpp-standards完整规则及正反例；项目没有Reviewer专用指南，回退plan-project-docs全局Reviewer模板。阶段审查计划关于未接受Minor也不能PASS的明确规则优先于通用模板简表。

批准包保持原字节：

- `docs/leader/designs/V0.2/S2-design.md`：`5dfc90adad8f0b9802a946b713434540a1954c69b3a2344a161f025b60e9bef6`。
- `docs/reviewer/reviews/V0.2/S2-review.md`：`af34802f758c1598b0fa89008b8ea5d694f055f65c8b354c65f52897aa93b201`。

执行路线为原生WSL、`/bin/bash`、login=false，仓库`/home/power/projects/AI-Inference-L7-Gateway`，分支`codex/v0.2-s2-backpressure`，HEAD `2f7cf831a302fc87717afcae510e777187c7d0ef`。Reviewer自有`build-local/reviewer/v0.2-s2/{tmp,cache,evidence,debug,release,asan}`。下文E指该目录的`evidence/`。每次脚本/构建显式设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME；已知socket/loopback/LSan边界首次精确窄升级，没有禁检查、安装、联网或跳过。未改产品/权威/历史、未派生代理、未commit/push。

审查覆盖所有当前C++变更及相关旧调用链：BufferBudget/CapacityLease、GatewayRuntime、ProxySession、ConnectionPool、GatewayConfig、RuntimeTests、BackpressureTests；同时追踪EventLoop注册/派发/cleanup、StreamOutput固定存储、HttpParser及标准库容量路径。Builder结果仅作输入，下面结果来自Reviewer自己的构建、执行和反例。

## 2. 独立执行结果

| 验证 | 结果及原始证据 |
| --- | --- |
| Debug配置、构建、完整CTest | exit0，**12/12，27.32s**；E/debug-{configure,build,test}.log、debug-LastTest.log |
| Release配置、构建、完整CTest | exit0，**12/12，23.42s**；对应release日志 |
| ASan+UBSan配置、构建、完整CTest | exit0，**12/12，49.30s**；对应asan日志，无sanitizer诊断 |
| 原response完成反例 | **18/18，exit0**；E/DeadlineMatrix.log |
| 原total完成对照 | **18/18，exit0**；E/TotalDeadlineMatrix.log |
| 解析错误先于候选、首字节commit和实际capacity | **16项，exit0**；E/ParseOrderProbe.log |
| 原120/150ms关闭窗口 | **20/20，exit0**；E/CloseWindow.log |
| Reviewer额外构造/发布分配故障探针 | **9个实际分配点逐点失败回滚、15个未触发成功对照、16个流分配路径清理，exit0**；E/AllocationProbe-ready.log |
| Reviewer额外同刻期限/极端水位探针 | **4种分类优先级、3个高水/low=0边界，exit0**；E/BoundaryProbe.log |
| 格式和空白 | clang-format-18 dry-run/Werror exit0，覆盖12个修改/新增C++文件；E/format.log；git diff --check exit0，E/diff-check.log |

三个完整CTest均实际执行Backpressure、Runtime、StreamingE2E、非流式/池/协议回归和AssertionFailure等入口，不用Builder的12/12代替。检查了Release主动失败入口的CTest预期失败语义。旧18cell合成成本实验与本阶段无关，未重复，也没有新性能收益结论。

原S1探针从Reviewer自己的v0.2-s1目录复制，保留`*-original.cpp`，新版本仅为SessionFixture加有明确寿命的BufferBudget及构造参数，差异记录`*-constructor.patch`；没有改时钟推进、输入、断言或期望。当前二进制链接Reviewer本阶段库。原CloseWindow脚本SHA256仍为`158de752e714596bbdacf5e0e5c351d098d74239faf95d3b7f4d63ec8b58b425`。

额外AllocationProbe首次失败和两个诊断输出全部保留。原因是Reviewer直接调用listener接缝前没有等待监听fd的POLLIN，就把尚未accept到连接误当成功对照；诊断显示alloc=0、sessions=0。最终探针增加最长1秒的poll(POLLIN)前置硬断言，随后才开启分配注入，没有修改产品或放松回滚断言。最终在第0至8个实际分配点抛bad_alloc，覆盖会话构造、注册、timer和map发布的分配序列；每次均sessions/reserved/timers=0且FD回到accept前基线。第9至23点是实际只分配9次的成功对照。流分配16点扫过后finish释放数组计费，预约仍持有至session.reset，随后归零。该探针故障不记为产品发现。

## 3. AC/RV逐项验收

| AC/RV | 独立检查与判断 |
| --- | --- |
| 01 配置、容量、回滚 | 新配置默认、极值、部分默认导致low≥high、类型/溢出/重复/未知拒绝均在三套Runtime重跑。BufferBudget唯一真值，容量凭证不可复制、move转移且release幂等；Session预约在构造前取得，作为首个成员最后析构，closing不退。Runtime预算成员寿命覆盖sessions。数组reset先于流凭证release。额外逐点分配探针及恢复注册失败验证无泄漏。容量证明见下文。PASS。 |
| 02 真实慢读与水位 | 三套Backpressure逐项检查真实Socket门控：CL/chunked/EOF各两轮明确paused、pending≥high、token=0；观察窗口reads/bytes不增，后端正文尚未被网关读完；放行后≤low且新token，最终逐字节decodeChunks==262153字节正文，唯一零块并要求末尾无多余字节。S1 StreamingE2E的前缀先见/后端尾部控制门仍通过。额外high=32768/196608/229376，实际pending=32840/196760/229544，low=0，仅排空后恢复；追加上界受每次16KiB限制。PASS。 |
| 03 暂停事件与租约 | 真实FIN/RST暂停观察与恢复在三套Backpressure执行；EOF完整尾部保留、RST无正常尾块。源码确认suspendEvents经id/generation定位后removeChannel，真实DEL且旧token移除，恢复ADD新token，无递归read。旧IN/HUP/ERR投递不增加读计数；Runtime的回收FD/stale注册测试与恢复注册失败注入通过。暂停无轮询timer，也无已注册HUP可反复派发；有限观察不被声称为无限时间性能证明。PASS。 |
| 04 跨会话预算与公平 | Runtime中1槽/2槽/524289非整倍数预算实测，空pending仍占262144，N+1返回503 buffer_capacity、上游失效，无等待/重试；释放后新流成功。三套真实Backpressure中慢流仍paused时另一普通请求完整200、第三接收超时408先完成，随后才释放慢读门，证明本工作负载不被停读会话饿死。会话预约混合限制/closing回归均通过。PASS。 |
| 05 分类期限 | 原81完成组合及独立18+18重跑；新Runtime验证idle/body与write/send的9/10/11ms、EINTR/EAGAIN不刷新、idle剩余6ms跨两次暂停保持、元数据不刷新、暂停response/total到期、排空后新episode。额外BoundaryProbe同刻依次屏蔽更高优先期限，确认total→write→response→idle；write直接结束且无输出，其余未提交504分类正确。源码每次上游IO/parse后先查旧期限，正数流send先标commit再查旧期限，不能发送第二头或过期成功尾块。非流式旧写规则保持。PASS。 |
| 06 取消与停止 | 三套StreamingE2E完整请求SHUT_WR/真实RST、Backpressure paused首信号排空/第二信号/停止期限、Runtime完成/取消/迟到resume/重复finish均实际执行。结束计数一次、timer/租约/pending/paused/数组容量/预约归零，真实用例最后FD回到起点。已结束状态先于恢复，暂停中的generation不转为idle；stream=true回退仍invalidate。PASS。 |
| 07 回归、规范、来源 | 三套完整独立构建测试及旧关闭/期限探针通过；格式、人工函数边界/接口与成员职责分组、具名短回调检查通过。57项源清单与Builder当前源逐字节匹配，48项已跟踪历史docs与HEAD逐字节相同，Approved hash保持。PASS。 |

新增常驻存储没有按chunk增长的容器或历史。StreamOutput数组262144，当前sizeof(StreamOutput)=262168、ProxySession=352、CapacityLease=16、BufferBudget=152；数组之外字段属于原元数据余量。独立ParseOrderProbe观察4MiB buffered body的capacity=7864320，normalized response capacity=4209892。按当前libstdc++保守同时存活上界：请求规范化容量<2.125MiB，buffered body capacity<8MiB、normalized输出≤4.0625MiB、元数据余量1MiB及16KiB scratch，总计<15.21MiB；SSE切换路径请求容量+288KiB流固定存储及片段+1MiB元数据<3.41MiB。请求parser在响应parser建立前销毁；buffered模式不分配流数组。全进程子预算是16MiB预约内的额外限制，不能相加解释为两份可用容量。

实际clang-format检查通过之外，人工逐函数核对本阶段12个C++文件的函数定义空行、头文件职责分组及新增回调。Builder报告及其format记录说明实际-i及最终检查已执行；Reviewer只检查，不格式化产品。没有把旧accepted单行getter机械拆分或扩大规范迁移。

## 4. 命令、源身份及历史保护

命令均在上述cwd，脚本/构建前执行：

```bash
export TMPDIR="$PWD/build-local/reviewer/v0.2-s2/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/reviewer/v0.2-s2/cache"
```

mode依次debug/release/asan，单步检查退出状态并存独立日志：

```bash
cmake --preset "$mode" -B "build-local/reviewer/v0.2-s2/$mode"
cmake --build "build-local/reviewer/v0.2-s2/$mode" -j4
ctest --test-dir "build-local/reviewer/v0.2-s2/$mode" --output-on-failure
```

各探针编译使用`c++ -std=c++20 -g -I src -I tests -I third_party/llhttp/include <E/探针.cpp> <Reviewer debug>/libgateway_runtime.a <Reviewer debug>/libgateway_foundation.a <Reviewer debug>/libllhttp.a -pthread -o <E/探针>`，编译均exit0；然后直接运行对应二进制，原始日志如表。关闭窗口命令`python3 <E/CloseWindow.py> build-local/reviewer/v0.2-s2/release/ai-inference-gateway`。clang-format命令为`clang-format-18 --dry-run --Werror`后接BufferBudget/GatewayRuntime/ProxySession/GatewayConfig/ConnectionPool的h/cpp及RuntimeTests.cpp、BackpressureTests.cpp。

- E/source-sha256.json：独立计算57项，SHA256 `97675b1c18ee9b749b684bcb1803f7d2c52643c2bc544e7e19a045572bd7e788`。
- E/binaries-sha256.json：三套所有根目录可执行文件和静态库身份；E/probe-sha256.json为原件、窄适配和新探针身份。
- 当前ProxySession.cpp：`aae23dcc29ad760e46093b6b429fbf5fb51f96f9aadc59dd1df5a3c97054106d`。
- BufferBudget.cpp：`6ed19e6b70ff0cc528b4f45331e975dffd243b3eefc22658a2172a9aa6d82992`。
- RuntimeTests.cpp：`6a0bc044225a7cef0266135a0a23c69bc6fda4435fc297ed4a7857b095b0bd67`。
- BackpressureTests.cpp：`253513200cb8f92e6a6d15b67549ada1d8b742bf08df36636510d8bcd12dd9a1`。
- 独立Release gateway：`3148634071f6451b18e7e7ab634887f6a45868de18f8b8f30f2706737b04afe7`。

E/identity.log记录当前源与历史核验。旧manifest、原S1反例/失败、旧报告不覆盖。Builder两次初期失败也已读明原因：旧Runtime硬溢出预期被S2明确策略替换；暂停EOF后端缓冲不足改为仅设置测试后端SO_SNDBUF，保留sent==wire.size硬断言。实际Linux缓冲大小在新独立Backpressure输出中记录，未把请求设置值当真实值。

## 5. 发现、限制与交接

正式发现：**None**。返工要求：None。建议接受债项：None。当前契约内无阻塞未验证项。

残余边界按Approved保持：这是单Worker、单静态上游的受限opaque SSE代理；暂停期间远端FIN/RST可以延后观察，response/total/write保证有界；用户态预约不等于RSS/内核缓存，旧buffered容量证明只适用于当前标准库；无严格公平或带宽均分声明，无真实GPU计算取消或稳定性结论，HTTP完整也不等于模型语义完成。实际signalfd/计时回调路径已验，事件外requestShutdown即时snapshot仍不是新SDK承诺。

请Leader据PASS同步README/ROADMAP/ARCHITECTURE中S2待实现/待审文字和CHANGELOG，保留历史时点记录；协调者再按当前授权本地提交，不推送。Reviewer不提前代办阶段关闭或发布。
