# V0.3/S2：准入与有界排队

## 1. 批准与目标

2026-10-20，`Approved`，待实现 / Ready for Builder，返工0/2。用户“已推送，进行s2的工作吧”及既有技术决策委托授权本阶段；批准包为本设计、[审查计划](../../../reviewer/reviews/V0.3/S2-review.md)、[Leader001](../../reports/V0.3/S2-report-001.md)。起点b704df268e2865bda146ba4c816dd105e6c8302c，分支codex/v0.3-s2-admission-queue，初始clean。S1已本地提交，推送为用户报告事实，本轮未独立核验远端。

在显式启用准入的新模型路由模式下，限制全进程/每实例未完成上游请求，容量不足时按模型有界等待或明确拒绝；取消、deadline、健康变化、停止不漏释放/重复派发。无自动重试/改投、主动健康探测、优先级/权重/成本预测、新依赖、模型下载。S3真实综合验收、V0.4性能/公平收益实验和P1约44ms诊断不纳入。

## 2. 源码依据与所有权（REQ-01）

S1 ModelRouter::selectBackend同步选择/增加唯一inflight，RequestLease::complete在上游终态恰一次释放并更新健康；ProxySession::completeRouting处理摘除清idle。Runtime拥有router、各实例池和按稳定uint64 ID保存的Session；onCleanup在事件/任务回调结束后清退Session和pool retired。Session已有accept起总deadline及一个timer，readDownstream将完整请求后的SHUT_WR视为EOF而非取消。BufferBudget为每Session保守预约16MiB，流固定容量为子预算。

新增src/admission/AdmissionController.h/.cpp（可合理拆内部类型），拥有各模型FIFO、计数/逻辑字节账、轮转游标和调度dirty状态，不拥有Socket/请求正文/Session。Runtime唯一拥有Controller且寿命长于所有Session，稳定session ID供队列查找；Session保存原已校验requestParser/message一次、model/stream元数据、queue入队时刻及charge，新增Waiting阶段。队列条目只含稳定ID、model索引、charge/必要时间，无裸Session引用或捕获短命对象的持久回调；通过Runtime map找到仍Waiting且匹配条目的Session才操作。

实例inflight仍由Router/RequestLease唯一维护，Admission不复制第二份可漂移计数；全局active定义为各实例inflight求和（最多64项），按该和执行全局限额。Router新增受限选择入口或候选容量过滤：同一EventLoop内先检查global，再过滤health与每实例限额，按原RR/LI选择并获取RequestLease。返回typed结果区分未知model、无健康、容量不足、停止。仅真正派发增加inflight/推进RR游标/占Trial；容量检查失败不得借还虚拟route lease或改变健康。

排队无RequestLease、ConnectionLease、streamCapacity，不占推理inflight；原Session内存预约仍有效，受max_connections/max_reserved_bytes独立约束。队列charge是逻辑保留请求量，不是新增可用内存或RSS；不与16MiB相加、不重复申请同一正文预算。出队前计数/bytes恰一次解除，之后已有Session预约继续保护请求/输出。入队分配失败须强异常保证，不能先加账后丢条目；500/internal_error且无残留。

## 3. 显式配置与资源上限（REQ-02）

新顶层可选admission对象只允许models模式；legacy提供该键拒绝。省略时完全保留S1即时选择/池满语义，旧JSON与直接构造GatewayConfig均兼容。对象存在即启用，字段均可省略并用默认：

```json
"admission": {
  "max_inflight": 16,
  "max_inflight_per_backend": 4,
  "max_queue_requests_per_model": 16,
  "max_queue_bytes_per_model": 4194304,
  "queue_timeout_ms": 1000
}
```

max_inflight及max_inflight_per_backend整数1..256，后者≤前者；统一的per_backend值逐实例独立执行，不是所有实例共享一份额度。queue_requests整数0..256，0表示不等待；queue_bytes整数0..268435456，0亦禁等待；timeout整数10..300000。非整数/bool/负数/溢出/未知键/重复键拒绝，沿64KiB/depth6总配置护栏；直接构造的启用配置也应在Runtime使用前验证，不允许绕过限额。

既有全局Session≤256、每个16MiB预约上限、最多32模型64实例及池乘积≤1024保持。队列总条目不超过活跃Session上限；每模型bytes≤配置限额、全局bytes为各模型求和（uint64检查溢出），最坏有界于32×268435456且实际受Session/请求上限进一步限制。不预分配配置上限正文或巨大数组。

charge精确为已解析message.method.size + target.size + body.size + 每个header(name.size + value.size + 4)，再加固定1024字节协议/元数据保守额度，全部按UTF-8字节与安全加法。不计未来响应、不声称包含allocator/RSS；它与现有checkOutputBudget的保守思路一致。每个request只算一次并保存，后续normalization不改queue charge。单请求charge大于byte上限且需排队返回队列字节拒绝；可立即派发的请求不受queue byte阈值阻拦。

新增config/admission-example.json，保留旧两个样例与默认模式，README写明opt-in、预算含义和连接上限与推理限额差别。

## 4. 进入、FIFO与派发（REQ-03）

请求完整合法后保留元数据，尚未生成绑定某Host的upstreamOutput。优先检查total/停止、未知模型和健康候选；未知404/model_not_found，无健康候选503/no_available_backend（包括所有Ejected未到期、Trial忙、Exhausted），不为纯健康不可用新建等待。global已满但有健康候选属于容量不足；健康候选Available可inflight已满，需与无健康区分。冷却可试探仍受原旧inflight=0条件和S2限额。

若所有模型队列都空且存在容量，允许直接派发。否则按模型FIFO尾部排队，防新请求绕过已有等待者；排队前先检查count，再检查bytes。count不足返回503/queue_full，bytes不足返回503/queue_bytes_exceeded，零等待配置用同样明确错误；无需添加Retry-After。所有请求错误体沿既有格式。Session级连接/预约拒绝发生在解析前，保持既有直接关闭语义，不谎称每种过载都能JSON503。

每次调度按模型配置顺序的持久轮转游标遍历，仅看每模型FIFO头，一个模型每轮至多一次派发；成功处理（派发或移除过期/无健康头）推进轮转，循环至无进展或本次预算32个头处理。阻塞某模型不能阻塞有容量的其他模型；同模型不跳过仍有效但暂时容量阻塞的队头。新请求在已有队列时也入队，由同一调度规则处理。无严格墙钟公平或跨模型绝对FIFO保证。

出队每次重新核对Session存在/Waiting、total和queue deadline、当前模型健康/限额。容量不足保留头；无健康立即移除并503/no_available_backend，不等待健康冷却、不增加主动健康timer；这是S2容量队列，不是故障重试队列。满足健康与限额才选择当前实例并取得RequestLease，解除队列账、进入原连接/发送路径；不绑定入队时实例、不要回退旧epoch。精确时刻now等于截止也不得派发。

取得route lease后取该实例ConnectionLease，若池仍被已完成上游但尚未下游排空的租约占满，则503/upstream_capacity、中立释放route lease，不重新排队或改投；这保持一次选定目标、无重试。S2每实例限额不是传输池额度。成功/失败/取消的请求inflight释放仍在S1最早上游终态，仅通知调度有容量变化，不再次维护独立容量lease。

## 5. 期限、取消、通知与停止（REQ-04）

Waiting只保留Session一个timer，期限=min(acceptedAt+total, enqueuedAt+queue_timeout)；完整请求后不再使用接收request timeout。total从accept起跨排队不重置；相同时total优先，返回504/total_timeout，否则504/queue_timeout；均无上游健康观察。出队开始connect/response沿原起算点，total仍旧。队列计数/字节在超时、取消、错误、正常派发、停止或析构中恰一次解除。

Waiting保持下游读取/错误监测。RST、明确socket错误或用户端关闭导致可观测错误时取消并移除；只收到完整请求后的EOF/SHUT_WR是合法半关闭，保留排队并最终响应，避免EPOLLRDHUP误删。TCP有序FIN与仅写半关闭不可区分时不得声称检测所有客户端离开，最终由deadline/写错误收口。第二请求沿旧有界丢弃且不再次派发。取消队中/队头后其余FIFO顺序保持。

释放/入队/取消/健康变化只标记需要调度，不在RequestLease析构或Session I/O栈里递归调用另一个Session。Runtime onCleanup在Session清理前或后用稳定ID安全处理队列，再清retired，保持回调后销毁不变。选择具体顺序需保证finished会话已解除队列引用。若32预算用尽且仍有可推进工作，通过至多一个合并的EventLoop task唤醒下一轮；任务只短转发具名Runtime方法、捕获寿命受Runtime保障的owner。纯容量阻塞不得反复自唤醒忙转，等待真实释放/新事件/已有queue timer；通知丢失也不得导致可派发头等到无关请求才启动。所有处理循环有界，调度guard禁止重入；停止时未执行task只作空操作，销毁前取消/排空相关捕获或采用明确有效期token。

停机先禁新准入/路由；已有Waiting全部解除队列账并返回503/gateway_stopping，走原有限错误输出，不再派发。运行中上游按既有shutdown期限排空，强制停止中立释放所有lease。重复SIGTERM/析构幂等，队列/bytes/inflight/lease/timer最终清零，无已销毁Session回调。Runtime寿命长于通知/Controller/Session；不添加公开管理HTTP端点。

## 6. 验收与有限混合负载（REQ-05）

新增CTest Admission（确定性时钟、Controller/Session门控）及AdmissionE2E（标准库多实例socket），可以合并合理fixture，但以下AC必须逐项可追溯：

| AC/RV | 必需证据 |
| --- | --- |
| 01 配置兼容 | opt-in默认与各边界、负数/溢出/bool/未知/重复/legacy拒绝；省略时旧S1及legacy全部断言不变；直接构造验证 |
| 02 容量与选择 | global=2/perbackend=1至少双模型四实例，任何瞬间和≤2、各≤1；无容量选择不推进游标/Trial；多个idle/保留下游lease与请求计数分离；出队重新选健康实例；pool满503中立且不重排/重发 |
| 03 队列账 | 单模型count/byte恰等于上限可入、超1拒绝；单请求过大、0等待；队首/中间取消、正常出队/超时/停止恰一次减账；排队无两类上游lease/streamCapacity，原16MiB预约无双计；入队异常/多次finish不泄漏 |
| 04 时间/健康 | 精确queue/total边界及同时到期total优先，已耗总时长不重置；队列中backend摘除/恢复/更低inflight后重新选择；全不可用出队503；Trial容量限制/取消中立、旧epoch保护保持 |
| 05 事件与停机 | 仅写SHUT_WR排队后完整获响应；RST移除；release即唤醒、无外部事件依赖；>32排队预算续轮全部进展、阻塞不忙转；shutdown含等待/活动流/idle/待执行task，最终FD/所有账/计时器回基线 |
| 06 有限混合观察与交付 | 下述固定混合运行、等待/顺序/失败样本与饥饿限制；三预设完整CTest、格式/人工规则、独立Reviewer关键组合、源/binary/旧权威保护 |

固定混合负载每角色Release运行一次，不做性能收益比较：两模型各2实例，global=2、perbackend=1、每模型queue_count=16/bytes=4MiB、queue_timeout=5000、total=10000ms、全局session=64且保守reservation≥64×16MiB（仅测试配置，不改默认）。预定义24请求：两模型各12条，按model交替发送，模型内每第1/5/9条为长流（受控目标200ms完整），其余短非流（目标10ms）；统一门闩启动且记录实际入队顺序，不假装线程编号就是FIFO。同模型实际入队→派发顺序验证，全部在护栏30秒内收口；目标sleep是负载参数非精确服务时长。

测试host内部观察每请求ID/model、accepted/enqueued/dispatched/upstream-complete/finished时间、结果/拒绝原因及最大inflight/队列count/bytes，记录所有已开始请求与实际退出；不添加产品日志API。按模型与长短分别列排队样本数、等待median/max、完成/超时/拒绝/取消，未排队单列，不用0混淆缺记录；记录同模型FIFO头阻塞、跨模型轮转局限。有限样本通过不证明长期无饥饿、开放负载SLO或公平收益；主场景预期24成功、无超时/拒绝，单独过载/取消负控不得混入主场景改分母。负载/状态不可信则不能以限制声明通过。

## 7. 实施、路线与交付

顺序：配置与纯有界queue/受限Router选择→Session Waiting/原请求所有权→Runtime调度/通知/停止→门控与socket负控/混合观察→文档。typed Selection/Admission结果区别容量/健康/队列错误，不靠错误字符串猜状态。个人C++规则正反例已读，clang-format-18实际格式化和检查覆盖所有受影响C++，人工相邻函数空行/回调/职责复核，避免S1漏检；不全仓重排。

各角色原生WSL /bin/bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway；build-local/角色/v0.3-s2/{tmp,cache,evidence,debug,release,asan}，脚本前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。构建cmake --preset debug -B build-local/builder/v0.3-s2/debug；cmake --build同目录 -j4；ctest --test-dir同目录 --output-on-failure，release/asan分别替换；Reviewer使用独立角色路径。新增预期Admission/AdmissionE2E及显式混合入口由Builder记录真实CLI；不能在计划中假称已执行。Socket/LSan已知边界首次精确升级，不关闭检测器。无需模型、P1矩阵或旧长soak。

Builder记录拆解/来源/报告、固定混合原始样本和中文配置说明；Reviewer独立三套完整回归和混合一次、关键生命周期补充，Leader仅PASS后收口。未接受发现必须按Olympus纠正，最多2轮。旧Approved/报告/P1/第三方保护，无新债务默认接受；完成后协调者本地提交、不推送，V0.3整体仍待S3。
