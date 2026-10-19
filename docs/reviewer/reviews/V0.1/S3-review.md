# V0.1/S3 独立审查与验证计划

## 1. 权威与状态

状态：`Approved`；日期/批准日期2026-10-19；阶段待实现。Leader (Zeus)按用户“开始s3的工作吧”“你来决策吧”及Olympus委托采纳，与[设计](../../../leader/designs/V0.1/S3-design.md)和[Leader001](../../../leader/reports/V0.1/S3-report-001.md)共同批准。本文定义验证方法，不覆盖设计行为。新S3累计0/2，历史S1 2/2、S2 1/2不变；当前无S3返工。

读取S3设计/Builder最新报告、原S2设计/rework-002/Reviewer002/Leader003；所有S1/S2原断言保留。项目无专用Reviewer指南，回退全局plan-project-docs Reviewer模板；读取agent-execution-route和personal-cpp-standards相关完整规范及正反例。Reviewer不得改产品或弱化权威。

## 2. 逐项独立验证

| 检查 | 权威 | 必需方法、通过边界与证据 |
| --- | --- | --- |
| RV-01 所有权 | REQ/AC-01、§3 | 审查Socket/Channel/租约对象图与cleanup顺序；可控事件注入在同epoll批次idle→leased、leased→idle、取消后fd复用和旧timer触发。无旧会话操作新租约，无执行中函数/Channel销毁；move/异常构造/双归还/双失效不重复释放。真实Socket多轮借还+ASan/UBSan。记录对象与token/generation，不仅检查字符串；UAF/串扰Blocker |
| RV-02 容量/配置 | REQ/AC-02、§4 | 原config仍可启动；新增对象类型/未知/重复/负数/float/bool/上下界/组合，max_idle=0，省略字段语义。池总量2、下游额度≥3：N−1/N/N+1持有租约，第三请求完整503 upstream_capacity且后端收到0次该请求；释放后下一请求成功。idle满后多余连接关闭，leased不驱逐。逐项核算pool/FD/timer/退休集与16MiB预约；越界/无限缓存Blocker，策略/配置错Major |
| RV-03 消息/释放 | REQ/AC-03、§5 | 至少20个独立下游顺序请求用唯一标记验证一个上游连接和各自精确响应；并发不同连接不交叉。覆盖CL/chunked/204/304、1xx→final、普通合法4xx/5xx复用，Connection close大小写/多字段、不定长EOF、早期响应尚未写完、截断/超限/坏协议/错误/取消/写timeout都不得归池。借出后重新解析且头/body/offset不残留。独立验证同块尾随、响应后下游慢写期间迟到、idle迟到、租出前已可读污染，不把尾随当下一响应；首合法响应保留。下游成功SHUT_WR前持有租约，之后closing RST/截止不误伤新借者；资源快照与后端accept/request日志可证明。错误复用/串扰Blocker，其余契约偏差Major |
| RV-04 陈旧/期限 | REQ/AC-04、§6 | 控时验证idle期限不刷新、借还旧timer无效、已过期条目不出借；真实后端idle FIN/RST/额外字节后新请求使用新连接。接缝严格控制peek数据/0/EAGAIN/EINTR耗尽/SO_ERROR及借出后首write失败，当前请求502后端至多一次且无自动新连接重发；后续新请求恢复。新租约response/write从启用起算，total从本次accept不变。已可见污染未丢弃或重试为Major/串扰Blocker |
| RV-05 停止 | REQ/AC-05、§7 | 实际SIGTERM停止时包含idle、connecting、leased、未完成下游请求、closing，验证idle立即关闭、新派发返回503 gateway_stopping（合法请求，未取得租约）、既有租约能有界完成且不归池；停止deadline与第二信号强制清空。只idle无session也退出；热数据不饿死timer/信号。正常产品事件/计时cleanup后active/reserved/pool/timer归零，端口/自有子进程关闭。复用S2关闭窗口原120/150ms20次及输出前后握手，不以改大延迟避问题。关键资源泄漏/失控Blocker，缺关键验证Major |
| RV-06 初始成本 | REQ/AC-06、§8 | Release独立运行ProxyBaseline固定18cell（3模式×2并发×3重复），审核原始样本、预热隔离、连接计数、closed-loop和超时/进程清理。0失败/拒绝、精确字节；close接受数等于请求数，reuse并发1累计1连接/并发4≤4。记录端到端分布/QPS/RSS/FD采样边界，数值只是初始观察，无收益阈值。遗漏失败或伪造统计Major；无法执行关键矩阵BLOCKED |
| RV-07 回归/规范 | REQ/AC-07、§9—10 | 三预设独立全CTest，实际README配置/启动、Release负控exit1，clang-format18及人工命名/回调/函数分组复核。第三方hash不变，S3来源差异单独记录且历史权威不改。独立核对新报告源码身份、成本结果与声明；未实现池以外后续能力，未把设计完成当阶段完成。缺关键证据Major |

所有必需用例保留实际命令、输入、退出码、期望与实际，关联具体AC。不以测试计数替代覆盖证明。单元接缝保证少见竞态可重复，真实进程/Socket证明链路；两者不能互相替代。

## 3. 攻击性边界与防误判

- 将完整响应和第二个响应同read返回、分批在下游写完前到达、idle期间到达、lease选择时已在Socket缓冲等窗口分别控制。peek之后未来到达的数据无法被预知，不要求验证任意恶意后端响应因果，但不能借此豁免所有已可见窗口。
- HTTP final早于请求发送完成：有意制造EAGAIN，不能仅以write offset在清空后为0判断写完；应见显式完成状态与禁止归池证据。
- 消费完整响应但同轮带RDHUP/HUP、Connection多头含close、最终204/304，分别验证正确响应及归池资格；不能只测200/CL。
- 归池发生在成功下游SHUT_WR后；该函数EINTR用尽、硬错误和旧closing错误回调须在接缝覆盖，原S2固定closing/error窗口断言保持。
- 发生失败或停止时没有隐式retry/抢占/队列。容量拒绝的请求在后端日志中不存在，重试用精确计数/连接尝试而非最终状态推测。
- 生成错误后不再发第二状态行，不回显prompt/响应/凭据。所有数据使用合成标记。
- 单个请求/事件的64KiB/64次IO公平边界与有限pool扫描保持；停止/到期应在持续活跃连接下推进。退休集在无后续业务流量时也须由本轮cleanup收口。
- Runtime requestShutdown事件外调用仍非产品SDK契约；不能用该方式替代实际signalfd/计时停止验收，也不能把历史限制当新的已修复成果。

## 4. 命令与独立证据

Shell `/bin/bash` login=false；cwd `/home/power/projects/AI-Inference-L7-Gateway`；分支codex/v0.1-s3-connection-reuse，初始HEAD3cb65244312d2feef563c2fd755ae8447d4589c5。先记录当前分支/HEAD、权威hash、工作区及产品/测试hash；代码变化后旧结果不可冒充新身份验收。

```bash
mkdir -p build-local/reviewer/s3/{tmp,cache,evidence}
export TMPDIR="$PWD/build-local/reviewer/s3/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/reviewer/s3/cache"
for mode in debug release asan; do
  cmake --preset "$mode" -B "build-local/reviewer/s3/$mode"
  cmake --build "build-local/reviewer/s3/$mode" -j 4
  ctest --test-dir "build-local/reviewer/s3/$mode" --output-on-failure
done
build-local/reviewer/s3/release/FoundationTests --intentional-failure
python3 tests/ProxyBaseline.py --gateway build-local/reviewer/s3/release/ai-inference-gateway --output build-local/reviewer/s3/evidence/baseline.json
```

负控应exit1，其余应0。实际新增CTest名称以 `ctest --test-dir build-local/reviewer/s3/debug -N` 与Builder清单核对，不能缺池/真实复用入口。每条命令日志分别保留exit；上面循环不是允许中间失败被最后成功覆盖。成本脚本不放入每次三预设CTest重复运行，Release独立矩阵单独验收。

格式：从实际S3修改列表列出自有C++，运行 `clang-format-18 --dry-run --Werror`；人工逐文件核查职责分组，查看Builder实际-i证据。不得格式化third_party或借检查修改产品。

Socket/loopback和LSan ptrace为已知环境边界，精确验证命令窄升级，不牺牲一次已知失败或禁用检查；失败日志与批准后重跑分开命名。Reviewer使用自有tmp/cache/构建/端口/进程，不直接使用Builder可变二进制当独立结果。原S2关闭探针若仅存本地，核对原hash/内容后在Reviewer s3目录复制并执行；若缺失，按原120/150ms、20次以及握手条件建立独立等价探针并明确来源，不能忽略必需回归。

## 5. 结论与交接

报告新建 `docs/reviewer/reports/V0.1/S3-report-001.md`，之后递增不覆盖。逐项RV结论、失败最小复现/严重度/AC、原始证据路径、源身份、成本统计与限制齐全。PASS要求全部AC独立满足；任何核心资格/容量/生命周期/真实链路或sanitizer缺口不可债务化。实现不满足FAIL，关键环境不具备BLOCKED；PASS WITH DEBT须先有明确批准、owner/目标/退出条件，当前没有预批准债项。

S3当前0/2，后续按Olympus跨原因累计，第三轮前硬停。Reviewer只给独立验收，不代Leader同步完成或创建提交/推送。Leader获得PASS且文档收口后才可宣称S3或V0.1完成；版本完成也不等于发布。
