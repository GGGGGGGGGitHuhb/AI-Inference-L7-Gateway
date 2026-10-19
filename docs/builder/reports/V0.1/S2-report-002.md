# V0.1/S2 Builder 第1轮返工报告 002

日期：2026-10-18。Builder (Hephaestus)。S2 累计 **1/2**；本轮修正与自测完成，交 Reviewer 独立复验。S2-F-001/F-002 的最终关闭由 Reviewer 判定；不宣称阶段完成。S1 历史2/2、初次报告与全部失败证据保留。

## 权威与范围

依据 Approved [rework-002](../../../leader/reworks/rework-002.md)、Leader S2-report-002、Reviewer S2-report-001，以及未改字节的原 S2 Approved 设计/审查。返工 SHA256：`fd8165b4251ca748f179fa9a683fb05ec35588ba7db90823f1f3f5a70a3bdbcf`。原设计 `a8d0206472e85bbb8facc5ba668c1aa4964803f48d7737cca659855aafc9de51`，原审查 `c8ad195e1c0a75155f91912179dc92bcd9187bf281329a063ef49b733a63c471`。

沿用 agent-execution-route、personal-cpp-standards 及完整规则/正反例、plan-project-docs Builder guide 回退。本轮行为修改为 ProxySession、SessionIo、RuntimeTests、GatewayE2E；GatewayRuntime 及其余 S2 自有/迁入 C++ 只补排版分组。另更新 S2 复用目标散列、差异补记、breakdown、README事实及本报告。未改 S1 无关文件、第三方、兄弟仓库、原权威或历史报告；无 commit/push/tag。

分支 `codex/v0.1-s2-proxy`，HEAD `bb318d8c55f5851d27cd52e6cd3367f450a5d8dd`，未提交工作区。WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`。最终身份见 `build-local/builder/s2/evidence/r1-handoff-identity.log` 与 `r1-source-sha256.txt`。

## RW-01—03 行为与不变量

`writeDownstream` 最后send成功后进入独立 `Phase::kClosing`，由 `beginClosing` 只记录一次 `outputCompletedAt_`，释放输出/解析器/上游。`shutdownWrite` 通过 SessionIo 调用真实 `shutdown(SHUT_WR)`，成功后 `writeShutdown_` 防止再次成功调用。send与shutdown共享本次64次写操作额度；EINTR用尽额度则保留OUT等下次事件继续，既不重记完成时刻也不刷新截止。硬错误直接终结。

成功半关闭后移除OUT，仍以原64KiB/64次读预算丢弃额外输入，EAGAIN不终结。先前或随后读到EOF且半关闭成功才finish；RST/硬错误、截止或强制停止也可finish。closing明确禁止 prepareError，即使输出释放后offset=0也不会再生成状态行。Channel仍活到事件回调后cleanup，finishSession保持幂等。

| 路径 | 实际 nextDeadline | 终结语义 |
| --- | --- | --- |
| 正常closing | min(acceptedAt+total, outputCompletedAt+1000ms) | 取代已完成的downstream_write；到期只关闭，不发504 |
| 错误closing | min(原errorDeadline, outputCompletedAt+1000ms) | 输出和读排空共享同一错误窗口；不新增1000ms，不重新套已过期total |
| 对端EOF | writeShutdown成功后终结 | 请求完整后的EOF不能提前取消待发响应 |
| 首次停止 | Runtime原shutdown绝对截止 | 优先于closing/error窗口 |
| 第二信号、强制停止、RST/硬错误 | 立即终结 | 不等待任意客户端确认 |

closing仍在Runtime会话map中，占一个连接和完整16MiB预约，保留一个下游Socket/Channel与最多一个会话timer；cleanup后才一次归还。没有第二上游、额外缓存、队列或线程。初次报告最坏逻辑存储10.125MiB上界不增；closing已释放大字符串，仍保留原完整预约避免大量FD堆积。

## 测试与原反例

| 对应要求 | 本轮实际验证 |
| --- | --- |
| 原关闭窗口不改 | Reviewer原CloseWindow.py逐字节复制为Builder `r1-CloseWindow.py`，SHA256同为 `158de752e714596bbdacf5e0e5c351d098d74239faf95d3b7f4d63ec8b58b425`；保持后端120ms、客户端额外写150ms及原全部20次断言；三个构建各20/20通过，完整105字节，0失败 |
| 输出前/后握手 | E2E closing_handshakes：正常200与本地Expect417，两者请求同批携带额外输入；读到输出EOF证明已SHUT_WR后再send120000字节，保持槽满拒绝新连接，随后客户端SHUT_WR；正文精确BODY/固定JSON、Content-Length、一个状态行，上游分别1/0次 |
| 确定性顺序 | testClosing记录最后send→一次shutdown，EAGAIN仍存活；额外200000字节单轮只读65536；EOF后fd F_GETFD=EBADF；重复就绪与timer调用不再次输出/半关闭 |
| EINTR/硬错误/异常 | 70次shutdown EINTR，首轮send占1次后只允许63次shutdown，下一轮完成第71次调用/唯一成功；900ms重试后仍在原1000ms到期；ENOTCONN终结；先到EOF、closing bad_alloc/RST只关闭无第二响应 |
| 绝对关闭截止 | 正常1000ms及total400ms两个分支，在limit−1热读仍存活、limit时就绪/timer终结；downstream_write=10ms不再限制已完成输出。错误输出前耗800ms，closing仅剩200ms；错误由total触发仍保留原错误窗口 |
| 额度/计数/停止 | testRuntimeClosingBudgets使用真实Socket，输出EOF后active=1/reserved=16777216/timer=1/upstream=0，拒绝另一连接；EOF、signalfd首次50ms截止、第二信号三个分支最终所有计数0；整个Runtime组FD数恢复 |
| 实际持续输入到期/公平 | E2E输出EOF后持续额外发送，约1秒终结，随后健康请求成功且仅2次上游；原热发送120/150ms场景恢复，其他请求408且首请求200。closing中首次70ms停止/第二信号进程均有界exit0 |
| 原回归保持 | 原S1/S2协议、短IO、容量、取消、timeout、信号等全部断言保留；旧fake客户端flush后显式提供EOF完成对端关闭，再断言资源归零，不把提交完成误认为资源已释放 |

接缝测试是可控syscall/时钟证据，真实E2E与原探针是独立Socket链路证据，不互相冒充。未抓包，不声称观测到了具体RST包序列。有限关闭不保证RST、强制停止或耗尽deadline后客户端应用必然读完，但原有限额外输入反例现在保持严格完整响应断言。

## RW-04 排版、来源与命令

真实使用 clang-format 18.1.3。范围文件清单 `r1-format-scope.txt`；人工逐文件复核记录 `r1-manual-format-review.md`：

- ProxySession、GatewayRuntime、SessionIo 的头/源；GatewayConfig、SignalSource 的头/源及main。
- EventLoop、Channel、Epoller 的头/源；HttpNormalization头/源；RuntimeTests。

检查构造/析构及单行函数之间空行、内联函数边界、public/private标签、接口/状态/成员职责分组；FakeIo shutdown和SessionFixture构造的非简单实现移至类外。未把工具绿当作人工规则已自动满足。S2来源JSON固定sourcehash未变，只重算目标hash；六文件从固定Server提交git show重新核对，规范化源从S1提交核对，8项匹配，见 `r1-provenance.log`。

所有构建/Python/测试均显式环境：

```bash
export TMPDIR="$PWD/build-local/builder/s2/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/s2/cache"
xargs -a build-local/builder/s2/evidence/r1-format-scope.txt clang-format-18 -i
xargs -a build-local/builder/s2/evidence/r1-format-scope.txt clang-format-18 --dry-run --Werror
for variant in debug release asan; do
  cmake --build build-local/builder/s2/$variant -j 4
  ctest --test-dir build-local/builder/s2/$variant -V
  python3 build-local/builder/s2/evidence/r1-CloseWindow.py \
    build-local/builder/s2/$variant/ai-inference-gateway
done
build-local/builder/s2/release/FoundationTests --intentional-failure
build-local/builder/s2/debug/ai-inference-gateway --config config/example.json
git diff --check
```

沿用初次已配置的三个Builder独立目录，没有复用Reviewer构建、临时配置、实例或端口。原探针只有源文件只读复制。Socket已知边界按精确命令升级；无下载、全局安装或跳过测试。

| 最终构建 | 完整CTest | 检查日志索引 | 原探针 |
| --- | --- | --- | --- |
| Debug | 7/7，exit0，9.56s | Runtime242、E2E448、Foundation33、Protocol76848 | 20/20，exit0 |
| Release | 7/7，exit0，6.92s | 同上 | 20/20，exit0 |
| ASan+UBSan | 7/7，exit0，20.98s | 同上，无sanitizer报告 | 20/20，exit0 |

其余CTest是主动失败负控、MockBackend五场景、Manifest。Release直接主动失败exit1；README示例READY127.0.0.1:8080、SIGTERM exit0。格式dry-run、diff-check、来源重算均exit0。

原始证据均为 `build-local/builder/s2/evidence/r1-*`：`<variant>-build-verified.log`、`<variant>-ctest.log`、`close-window-<variant>-final.log`、`close-window-source.log`、`format-final.log`、`manual-format-review.md`、`readme-smoke.log`、`release-negative.log`、`provenance.log`、`handoff-identity.log`、`source-sha256.txt`。日志中实际request/shutdown/closing耗时仅代表这些场景，不是性能结论。检查数量是索引，覆盖依前表具体输入/顺序/期限和源码断言。

## 本轮初次失败与边界

保留 `r1-runtime-initial.log` 的基础194项通过和原探针首轮20/20。新增真实容量测试在 `r1-debug-targeted.log` 中一次poll后立即recv新拒绝连接仍得到EAGAIN；改为最多20次有限poll等待，仍要求最终EOF且原closing预约不减少。

`r1-debug-targeted-02.log` / `r1-runtime-diagnostic.log` 发现测试在事件循环外直接调用第二次requestShutdown，loop已停止而callback后cleanup尚无执行机会，snapshot中残留finished会话；该夹具改为实际 `raise(SIGTERM/SIGINT)→signalfd→pollOnce` 路径。产品Runtime未改行为；三种退出路径现在都记录active/reserved/timer/upstream=0。没有删除旧归零断言或延长产品deadline。

当前无已知未满足的本轮要求，仍需独立Reviewer确认两项发现、原反例、规范与完整回归。没有S3、SSE、池、重试、排队、真实GPU或性能验收；未提交/发布。
