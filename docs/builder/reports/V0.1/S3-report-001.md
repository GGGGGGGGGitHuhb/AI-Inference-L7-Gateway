# V0.1/S3 Builder 实现报告 001

日期：2026-10-19；Builder (Hephaestus)。初次实现完成、自测通过，**待独立Reviewer验收**；S3返工0/2，未提交/推送/发布。用户“开始s3的工作吧”授权本阶段；技术基线由Leader在既有委托内Approved。

## 输入与目标

完整读取[S3-design](../../../leader/designs/V0.1/S3-design.md)、[S3-review](../../../reviewer/reviews/V0.1/S3-review.md)、[Leader001](../../../leader/reports/V0.1/S3-report-001.md)，以及S2收口003、rework-002和S2源码/测试。沿用户全局AGENTS、agent-execution-route、personal-cpp-standards完整规则/正反例、plan-project-docs Builder模板及stage-design参考；无项目专用Builder指南，回退已告知协调者。保留所有历史权威、报告和来源清单。

预期：独立下游会话顺序复用唯一静态上游，有界总量/idle/期限、唯一租约、资格与污染防护、停止清理和固定成本观测；不添加队列/重试/下游keep-alive/SSE。实际已实现上述范围，独立接受仍待Reviewer。

路线：原生WSL2 `/bin/bash` login=false，仓库 `/home/power/projects/AI-Inference-L7-Gateway`；分支 `codex/v0.1-s3-connection-reuse`，HEAD `3cb65244312d2feef563c2fd755ae8447d4589c5`。角色临时/缓存/证据与构建独立放在 `build-local/builder/s3/{tmp,cache,evidence,debug,release,asan}`。所有Python/构建前显式设TMPDIR/TMP/TEMP/XDG_CACHE_HOME。loopback/LSan验证直接窄升级，不做已知EPERM失败试探、不禁用检查。没有安装/下载或兄弟仓库写入。

## 实现与所有权

- 新 `src/upstream/ConnectionPool.{h,cpp}`：池唯一持有稳定Entry（Socket/Channel）；ConnectionLease为move-only代次句柄。connecting占槽；归还与失效均先清空句柄，双操作无重复释放。ID不复用，generation耗尽逐出，token由既有EventLoop分配。idle→leased及leased→idle先注销，下一兴趣注册获得新token。
- Channel回调永久只转发pool具名函数；租用时保存的会话回调在执行前复制为局部目标，允许回调内清除条目目标。idle无旧会话指针；退休先注销/close再延后销毁，Runtime每业务/计时回调后cleanup先回收已完成会话再清理retired。没有修改net框架或复制旧Server。
- ProxySession显式requestWriteComplete；在原始响应头检查close token、EOF定界、当前read消费边界和同轮关闭/错误。已缓存合法响应期间迟到事件只关闭上游，不再解析终态或产生第二响应。完整下游send并成功SHUT_WR才归还；失败/EINTR未成功时继续持有或失效。已归还后的closing只拥有下游，保留S2全额预约与固定截止。
- PoolConfig支持默认/范围/组合拒绝，满池立即503 upstream_capacity，停止后503 gateway_stopping。默认上游不强制close；max_idle=0请求强制close。无idle且未满才新建；借出后的失败不换连接重发。idle读事件/到期及借还peek+SO_ERROR逐出污染与断开连接。
- 新测试Pool/ReuseE2E、扩展Runtime、持久后端/隔离进程夹具、固定ProxyBaseline矩阵；现有GatewayE2E唯一既有行为适配是默认上游请求不再强制close（S3批准语义），其余S1/S2断言保留，原关闭窗口没有修改120/150ms。

具体修改文件及S2基线/当前SHA-256逐行见[变化记录](../../../references/V0.1-S3-changes.md)。README/示例配置说明实际行为与待验收状态；Leader根架构/路线变更保留，未擅自标记阶段完成。

## 数量、存储与计数边界

令下游额度M≤256、上游额度N≤256、idle额度I≤N：上游活FD≤N，下游FD≤M，临时accept最多1，另固定监听/epoll/eventfd/signalfd。pool仅存传输元数据；每会话仍16MiB预约，不因响应输出释放或归池提前退还closing额度。

connections有效条目≤N；在每次acquire前检查有效+退休<2N，最多增加1个Entry。retire只移动所有权，不增加同时存活条目；退休vector预留2N，push不分配。所以所有Entry/上游Channel合计≤2N（最多512），退休不持FD/正文且最迟本业务或计时回调后清空。直接内部测试调用需要显式cleanup，这不是产品SDK。下游Channel≤M，连接生命周期变换不创建额外Channel。

timer≤activeSessions+poolIdle+1个shutdown；上游connecting/leased使用会话timer，无池活动timer；固定eventfd/signalfd不占timer。Runtime真实20轮快照验证：响应EOF但客户端未关闭时active=1/reserved=16MiB/poolIdle=1/timers=2；客户端关闭后active=0/reserved=0/poolIdle=1/timer=1；实际SIGTERM后所有当前计数包括retired归零。

snapshot.pool.total/leased/idle/retired为当前状态，peakTotal为有效物理条目峰；created/reused/discarded/capacityRejected为饱和累计次数，discarded含正常策略关闭/停止/故障，不能解读为错误率。activeUpstreams仅当前leased（包括connecting和待下游输出），不包含idle。每方向原64KiB/64次IO预算保留；池扫描最多N候选，peek每候选至多32次EINTR尝试，无无限扫描或等待。

## AC与可复现证据

证据根 `build-local/builder/s3/evidence/`。计数仅用于核对，不替代以下覆盖：

| 验收 | 实际覆盖/入口 | 结果 |
| --- | --- | --- |
| AC-01 | PoolTests::testOwnershipAndTokens：借还新token/代次、同批旧token、旧timer、move/双失效、回调内失效后cleanup；Runtime::testPoolAllocationFailures：bad_alloc与归池token分配异常回滚，FD无泄漏；三套sanitizer/真实借还 | 自测通过 |
| AC-02 | Pool::testConfig各类型/重复/范围/省略组合；N−1/N/N+1、idle=1溢出、max_idle=0；ReuseE2E::capacity真实2槽、第3请求503且后端记录无该marker、之后恢复；Runtime快照/预约/FD基线 | 自测通过 |
| AC-03 | 7种合法响应各20独立下游精确唯一marker且仅1上游；并发容量用first/second不串；close多字段大小写、EOF、尾随/迟到、截断/既有坏协议/超限/早期响应/取消；Runtime::testReuseSessionBoundaries覆盖SHUT_WR前租约、EINTR用尽/错误、旧closing RST不影响新借者；原关闭握手 | 自测通过 |
| AC-04 | Pool::testDirtyCandidates归还和租出前data/0/EAGAIN/硬错/SO_ERROR/EINTR耗尽；真实idle FIN/RST/迟到字节与10ms过期重建；testReusedFailureAndDeadlines复用首write失败502零新连接/零重发、response从新租约起算、total保留accept起点 | 自测通过 |
| AC-05 | 原S2连接中/活动/未完整请求/closing停止全保留；新增idle无session实际SIGTERM全清零、已有未派发完整请求503 stopping、第二信号、池持有connecting/leased停止不抢占但force全失效；原热数据定时/信号推进和固定closing期限 | 自测通过 |
| AC-06 | ProxyBaseline固定18cell；原始预热/样本/配置/连接日志/10msRSS-FD采样/身份，详见下节 | 18/18通过 |
| AC-07 | Debug/Release/ASan+UBSan各9/9；原120/150ms窗口20/20；Release负控exit1；clang-format18实际-i/check及人工12文件复核；历史/第三方未变 | 自测通过 |

Pool是确定性传输/时钟接缝，不冒充真实TCP；ReuseE2E和Runtime快照是实际Socket，成本实验运行独立Python后端进程。测试不宣称观测TCP包序列。

### 实际命令与结果

```bash
export TMPDIR="$PWD/build-local/builder/s3/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/s3/cache"
# 每个mode分别执行，失败立即停止；不靠最后命令覆盖中间退出码。
cmake --preset "$mode" -B "build-local/builder/s3/$mode"
cmake --build "build-local/builder/s3/$mode" -j 4
ctest --test-dir "build-local/builder/s3/$mode" --output-on-failure
build-local/builder/s3/release/FoundationTests --intentional-failure
python3 build-local/reviewer/s2/evidence/CloseWindow.py build-local/builder/s3/release/ai-inference-gateway
xargs clang-format-18 -i < build-local/builder/s3/evidence/format-files.txt
xargs clang-format-18 --dry-run --Werror < build-local/builder/s3/evidence/format-files.txt
```

各mode为debug/release/asan；configure/build见`*-configure-verified.log`/`*-build-verified.log`，退出均0。最终`debug-test-final.log`9/9 12.74s、`release-test-final.log`9/9 10.29s、`asan-test-final.log`9/9 24.38s，全部exit0，ASan/UBSan无报告。Release负控`release-negative.log`明确exit1。`runtime-details.log`562检查、`pool-details.log`166、`reuse-details.log`374及每类连接计数；`close-window.log`20次105字节完整首响应、FAILURES 0 OF 20，未改原脚本参数。

格式工具Ubuntu clang-format18.1.3（`format-version.log`），已实际-i和--dry-run --Werror，`format-check-final.log`exit0。12文件范围见format-files.txt：GatewayConfig、GatewayRuntime、ProxySession、SessionIo、ConnectionPool的h/cpp及RuntimeTests/PoolTests。人工逐文件核查函数间空行、头文件职责分组、短转发lambda、回调保存/执行目标和状态命名；未格式化第三方或无关迁入文件。`git diff --check`通过。

### 原始失败与处置

所有initial/expanded/verified日志保留。初次最终ASan执行`asan-test-verified.log`中ReuseE2E停止夹具exit -15，其余8项通过；没有ASan/UBSan诊断。夹具已主动发SIGTERM/INT，finally的close又在进程退出/恢复原信号掩码窗口发送SIGTERM。修正为显式停止后`process.wait(timeout=2)`确认自然退出（与既有GatewayE2E相同方式），不是改产品/放宽状态断言/加大关闭窗口。修正后重新跑全部三预设，结果为上述最终日志。初次阶段实现内自测修正，不冒充独立Reviewer返工或删除原失败。

## 固定初始成本结果

`python3 tests/ProxyBaseline.py --gateway build-local/builder/s3/release/ai-inference-gateway --output build-local/builder/s3/evidence/baseline-serial.json` exit0。正式串行观测在全部功能测试完成后单独执行；较早与功能验证重叠的`baseline.json`/baseline.log也保留、18/18正确，但不拿混合负载结果替换正式观测。

固定请求436线缆字节，content为256个ASCII字符，响应JSON正文1024字节；每cell20预热+200测量，三模式×并发1/4×三重复=18。客户端每次新TCP，closed-loop每worker完成后才发下一条，后端无人工延迟；不是真实推理/固定到达率。每个原始样本含ns耗时、精确响应长度/hash、成功/拒绝/错误字段；完整配置及backend逐请求connection/marker记录在baseline-serial-cells-*子目录。

全部3600测量+360预热均精确、0失败/拒绝，close模式各cell220接受/220请求，reuse并发1累计1连接、并发4累计4。测量前保留预热池，计数差量另列。10ms采样网关及后端进程RSS/FD，包含前后快照、原始采样、观察峰和网关FD上界检查；采样峰不是严格实时峰，direct无网关。关闭后自有进程及监听端口均回收。

下表为各重复cell的QPS/P99范围，不将所有样本混成另一分布。nearest-rank端到端P99，单位ms：

| 模式 | 并发 | 完成QPS范围 | P99 ms范围 | 3次累计后端连接数（含预热） |
| --- | --- | --- | --- | --- |
| direct-close | 1 | 926.8–1123.3 | 1.606–2.139 | 220,220,220 |
| proxy-close | 1 | 537.9–543.1 | 2.854–3.422 | 220,220,220 |
| proxy-reuse | 1 | 922.7–941.1 | 1.760–2.023 | 1,1,1 |
| direct-close | 4 | 1538.1–1898.0 | 4.470–5.385 | 220,220,220 |
| proxy-close | 4 | 1430.1–1694.5 | 3.895–5.854 | 220,220,220 |
| proxy-reuse | 4 | 2422.1–2713.9 | 2.342–3.822 | 4,4,4 |

proxy-close/direct（并发1）QPS比值0.48–0.58，P99比值1.43–1.97；proxy-reuse/direct（并发1）QPS比值0.83–1.00，P99比值0.93–1.10；proxy-close/direct（并发4）QPS比值0.89–1.01，P99比值0.87–1.09；proxy-reuse/direct（并发4）QPS比值1.43–1.70，P99比值0.44–0.80。这些是受合成Python后端/新建线程成本、WSL调度与采样影响的初始观察，不承诺生产收益；proxy-close并发1明显慢于直连，完整保留。没有把两组P99相减称为“额外延迟P99”，没有据此启动优化或扩阶段。

## 身份与交接

S3设计SHA-256 `2d41cb66f20750105e81dba0b6f7c1b5bce694aee0998290c100f7603a92a127`，S3审查 `ca8d3c1dc62809f728aaed083b660c13ff614e678e8dcfd6f703ab6e140e826e`，均与批准包一致。完整当前产品/测试身份文件 `source-sha256.json` SHA-256 `40d3fda7928ec272639ded0593ec8822d165d50cbf16a870f6393a3ce2afe7ee`；Release二进制 `9313a0eaf12986693ee4f89e4994213d26bcf724a19acf8acefbf797f0d71700`，与正式baseline内记录一致。最终交接再次逐项核对；原始证据为本地gitignored目录，不等于远程发布附件。

未完成：独立Reviewer全部RV验收和Leader文档收口。没有已知契约内未解决失败或新技术债、没有权限/环境阻塞。架构/路线仍由Leader拥有当前生命周期状态，Builder README明确待验收，不以测试绿标记S3或V0.1完成。

Reviewer重点：借还期间token/代次与正在执行回调副本的寿命、retired上界/cleanup、成功SHUT_WR前保守持有与之后旧closing隔离、同块/持有期/idle/借出前不同污染窗口、no retry和stop禁新派发。peek无法保证未来存活，也不能识别任意恶意后端新请求之后伪装的新响应，沿Approved限制；Runtime仍非事件外嵌入式SDK。未新增这些能力或作更强保证。
