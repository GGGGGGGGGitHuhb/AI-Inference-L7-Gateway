# V0.3/S1：模型路由与被动健康

## 1. 批准与范围

2026-10-20，`Approved`，待实现，Ready for Builder，累计返工0/2。用户明确“开始v0.3/s1的工作”，结合既有“你来决策吧”技术委托，Leader批准路线图S1范围内的本基线及[审查计划](../../../reviewer/reviews/V0.3/S1-review.md)，批准包为[Leader001](../../reports/V0.3/S1-report-001.md)。起点e231fda25879060fcd730f562982f06448f2ba11，分支codex/v0.3-s1-routing-health；P1已本地提交、不推送。历史权威与报告不改。

目标：按请求model选择静态实例组，支持RR/Least Inflight，按请求结果摘除及冷却后试探恢复；模型隔离、错误和资源生命周期可复现。保留旧单上游配置/协议/测试入口。无队列、每实例推理准入额度、自动重试、模型别名改写、服务发现、后台健康探针、管理API或多Worker。V0.3/S2准入排队、S3真实多实例综合验收、V0.4收益实验均不提前；P1约44ms不顺手优化，无模型下载/新依赖。

## 2. 源码依据与模块责任（REQ-01）

当前GatewayConfig仅upstream_address/port且JSON嵌套护栏depth2；Runtime拥有单ConnectionPool；ProxySession::beginUpstream在validateTextRequest后直接用单地址归一化Host/建连。TextRequestMetadata已提供model/stream，无需再次解析请求。池唯一拥有Socket，ConnectionLease以id/generation管理一次传输使用权；completeResponse可能保留lease到下游排空，stream在完整HTTP时关闭上游。健康和请求inflight不能直接复用池leased/idle或FinishReason粗分类。

新增src/routing中的模型目录、路由选择与请求派发租约；具体合理文件拆分由Builder决定，建议ModelRouter.h/.cpp。该层不操作Socket，只保存静态路由、每实例唯一inflight/健康真值及RR游标，提供有类型选择结果和有类型结果报告。单EventLoop中同步选择并增加inflight，成功派发持有不可复制可移动的请求租约；其幂等终结负责恰一次减计数并提交健康观察，析构兜底中立释放。Counter不可按TCP连接数更新。

Runtime拥有router和固定实例池集合，池生命周期长于所有Session/请求租约；每个配置实例按(model,id)独立ConnectionPool，即使不同模型地址相同也不得跨池复用。upstream模块继续持有传输；添加有限的清空idle操作供摘除使用，不借stopAcquisition永久关闭可恢复实例。Session负责编排选择、目标Host/地址、ConnectionLease与请求租约，并将已知终结原因显式映射为健康结果，不能依靠字符串error code或FinishReason猜测全部原因。HTTP/parser/net不依赖路由。

Runtime测试快照可追加每实例id/model/inflight/state/failureCount/epoch及pool计数，只作同进程测试观察，无产品HTTP端点。既有RuntimeSnapshot字段和legacy行为保留；聚合pool数量/累计计数求和，peakTotal如求各池峰值和须注明是上界非同时峰值，legacy单池值不变。测试fixture确需装配新依赖时局部适配，不删除旧断言或批量改旧运行输入。

## 3. 配置与兼容（REQ-02）

旧模式：仅upstream_address/upstream_port，与现有upstream_pool/timeouts等共同使用，保持任意有效model透传、单池选择、原错误与deadline行为；不新增被动摘除，避免改变既有单上游失败/恢复测试。程序内直接构造GatewayConfig且只填旧字段同样有效，不强迫既有测试转JSON。新增路由模式与旧地址两字段互斥；旧字段缺一、两模式都无/都出现均拒绝启动。新模式示例：

```json
{
  "listen_address": "127.0.0.1",
  "listen_port": 8080,
  "models": [
    {
      "name": "model-a",
      "policy": "round_robin",
      "backends": [
        {"id": "a1", "address": "127.0.0.1", "port": 9001},
        {"id": "a2", "address": "127.0.0.1", "port": 9002}
      ]
    }
  ],
  "health": {"failure_threshold": 2, "cooldown_ms": 1000}
}
```

models必须1..32组，总实例1..64，每组至少1；name非空合法JSON字符串、UTF-8字节≤256且无ASCII控制字节/NUL，组名唯一且字节精确匹配请求model，无大小写/空白折叠。policy可省略，默认round_robin；仅支持round_robin/least_inflight。backend必含id/address/port，无未知键；id为1..64字节ASCII字母数字或_.-，组内唯一；组内重复(address,port)拒绝，跨model重复地址允许但池/健康/inflight隔离，不冒称物理服务器容量隔离。address沿现有数值IPv4规则、禁止0.0.0.0；port1..65535。所有实例检查self upstream，listen_port=0在bind得实际端口后再次检查全部地址。

health仅路由模式可提供，省略用failure_threshold=2/cooldown_ms=1000；阈值整数1..16，冷却整数10..300000ms。upstream_pool仍一份参数应用于各实例池，沿原1..256 connections、0..256 idle及idle≤connections；新增路由模式要求实例总数×max_connections≤1024（安全乘法），从而传输对象/idle timer总量有限。其上限是既有连接资源边界，不是S2推理容量或队列额度。Session全局上限和内存预算不变，不按backend数放大。

配置仍≤65536字节，重复键/未知字段/错误类型/负数/溢出严格拒绝。为models嵌套只将配置解析深度护栏扩大至6，不接受任意深度；所有新对象显式白名单。空数组、空对象、非法policy、缺字段均有负控。README列旧模式兼容与上述上限；新示例配置放config/routing-example.json，不得改变已有默认单上游样例。

## 4. 选择、请求租约与传输池（REQ-03）

请求协议/JSON校验通过后，先按model查组。路由模式未知model返回404，稳定error.code=model_not_found；组内无可选实例返回503/no_available_backend。均不触发上游连接、不改变任何inflight。legacy维持原校验。

候选是Available或已到冷却期限且无在途旧请求的Ejected实例；Trial实例不可再选。无socket probe。模型内一个游标初始0，按配置顺序循环：RR从游标起找首候选；Least Inflight先取候选最小请求inflight，平局按同一游标循环顺序。成功取得请求租约后游标移到选中项下一位；未知/无候选不动游标。Available的inflight包括connecting、请求发送、等待响应和未完成上游流；不含idle、客户端接收请求阶段、已完整上游响应后的下游排空。

选择并增加inflight在同一EventLoop操作中完成，随后只向该实例的池取ConnectionLease。取池失败返回503/upstream_capacity（停止为gateway_stopping），请求租约中立释放；不将pool满认定不健康，也不改选其他实例。无自动重试或一次请求多实例投递；失败当前请求沿原502/504语义，后续独立请求才重新选择。路由选择本身不是容量预约策略，S2另行定义。

请求inflight在以下最早上游终态恰一次释放：完整HTTP响应被解析/既有校验接受时（非流和流均如此）、明确上游失败、客户端取消/本地终止导致上游不再继续时。成功报告应在当前deadline检查与内部输出准备成功后、responseParser.reset之前读取响应status；流成功在HTTP终态确认后、关闭上游之前。下游慢读可以继续占用session/buffer或旧非流ConnectionLease，但不再占请求inflight；这有意衡量尚未完成上游请求，而不是活跃客户端数。下游随后取消不能覆盖已记录成功。每Session健康报告至多一次，反复finish/错误/drain/析构不重复。

路由租约携带实例稳定索引与健康epoch。连接归池除旧S3资格外，还需该请求epoch仍等于当前实例epoch且实例仍Available；否则invalidate。已摘除实例的现有idle立即清空，旧在途请求允许自然完成但不得重新污染idle或恢复新epoch健康。即使请求inflight已释放而ConnectionLease仍等下游发送，归池时也需重新检查此资格；pool本身不持悬空Session回调。

## 5. 被动健康与恢复（REQ-04）

状态名称Available/Ejected/Trial。初始Available表示配置允许运行、尚无请求健康观察，不代表启动时已验证模型加载。静态model映射声明服务能力，实际健康证据来自该model请求在既有协议下完整HTTP 2xx结果，TCP connect、收到头、流首片都不算成功。此为模型请求服务的协议级健康，不解析生成文本/SSE业务事件来验证模型语义，不保证GPU可用/模型质量；完整2xx中的应用错误或伪成功不在S1识别范围。该边界在用户文档明示。

| 完成观察 | 健康处理 |
| --- | --- |
| 请求完整合法HTTP 2xx，包括既有SSE HTTP终态 | Success，当前epoch重置失败计数；Trial恢复Available |
| 完整HTTP 401/403/404、所有3xx和5xx | Failure；前者视为该配置目标不可服务（含缺模型/凭据配置），不靠TCP成功复活 |
| 完整其他4xx，含400/408/409/422/429 | Neutral，不用输入/限流类状态摘除或证明健康；按原协议转发响应 |
| connect/socket/send/recv上游故障、HTTP解析/定界截断错误；明确connect/upstream_write timeout；未处背压暂停期间的response/stream_idle timeout | Failure，当前请求按既有错误返回；无重试 |
| 下游RST/取消、shutdown、请求输入错误、本地分配/预算/输出上限、pool满、total deadline、下游写超时、背压暂停期间到达response deadline | Neutral，不能把客户端/本地容量原因算实例失败 |

响应status健康判定只在完整HTTP完成后作出；如5xx正文中途断开，按一次传输Failure处理，不先记status再重复记错。若已知明确上游故障先终结，后来取消不得覆盖；同时就绪事件按EventLoop实际先处理的终结为准，禁止事后补第二份观察。所有本地保护性stream_buffer_limit按Neutral；不改变其已有客户端错误。

Available当前epoch的Failure使连续非中立失败计数+1（饱和于阈值）；Success清零，Neutral不变。达到阈值时进入Ejected，epoch递增、记录eligibleAt=now+cooldown，清空idle。若其它旧epoch请求随后完成，只减自己的inflight，不变失败计数/状态，不清新冷却期限；仍可把其结果交给各自客户端。

冷却到期不自动变健康。新的路由选择发现Ejected且now≥eligibleAt且inflight=0时，可将它作为候选；真正选中后原子进入Trial并占唯一试探资格/inflight=1。试探就是一次正常用户请求，原请求可能失败；不能先向其他实例成功再复制试探。Trial Success→Available、失败清零；Trial Failure→Ejected、新epoch、新冷却；Trial Neutral（含取消/pool满/total deadline）也返回Ejected、新epoch/新冷却，但不增加失败计数，释放试探资格。从不因取消卡死Trial或直接标健康。

没有额外健康timer或后台探针，deadline在下一次请求选择时比较SessionIo单调时钟，空闲期间保持Ejected是正常被动语义；恢复需要后续流量。即使仍有健康实例，RR/LI候选也包含满足条件的试探项，遵守相同选择规则，无独立优先权。epoch溢出不得绕回可匹配旧请求，采用不可再路由的终态/停止并明确错误；受现有生命周期限制正常路径不可发生，测试可注入边界。

## 6. 生命周期、错误和有界性（REQ-05）

Runtime构造router/池再建立Session；销毁时先中立终结/清空Session及其两类lease，再取消池timer/移除channel、清理池和router，最后EventLoop。停机先禁止新路由和pool acquisition、清idle，已有请求沿旧有限排空；强制停止使Trial释放、中立终结所有未完成请求。cleanupRetired覆盖每池，不能在事件回调中删除正在执行的channel。不得新增捕获短命对象的延迟observer；健康报告优先显式同步调用，若新增回调必须符合个人规范并记录owner生命期。

既有请求/总deadline从accept起算且路由不重置；上游选中后connect等沿原语义；背压暂停/恢复保留。流响应已向下游提交时遇错误只终止/关闭，不拼第二HTTP错误、不伪造成功零块；未提交可按原规则返回502/504等。请求未知模型/无健康返回非流JSON错误，即使请求stream=true。原Session保守预约、流capacity、timer上限/退出条件继续成立；新routing状态规模为配置上限O(64)，无无界事件历史/日志/请求排队。

## 7. 实现顺序与验证（REQ-06）

Builder先拆解：配置/纯路由状态与租约→每实例池及Runtime生命周期→Session结果分类/归池防护→针对性端到端与旧回归→用户配置/报告。遵循personal-cpp-standards及正反例，实际clang-format-18格式化/--dry-run --Werror覆盖本次所有C++文件并人工检查职责空行；不全仓重排/改工具配置。

新增CTest入口Routing（确定性C++时钟/状态/租约单测）和RoutingE2E（标准库Python/受控多实例真实socket），Builder记录实际target/源码路径与命令。沿已有测试注入SessionIo和测试访问缝，不向产品配置加入故障开关；必要可用现有Runtime测试host扩展内部快照而不增加管理API。

| AC/RV | 必须验证 |
| --- | --- |
| 01 配置与旧兼容 | 上述类型/重复/深度/数量/乘积/自指/模式互斥负控；合法RR/LI与旧JSON及直接构造配置；旧全部CTest断言保持，旧model任意透传 |
| 02 路由与隔离 | 2模型×至少2实例：RR固定循环；LI持有长流/非流使负载不同，平局轮转；预先存在多个idle仍按请求inflight而非pool total；同地址跨model独立池和状态；未知404/无候选503无上游派发 |
| 03 健康状态 | 阈值前后、成功清零、中立不清/不增、时钟冷却前后、唯一Trial、Trial失败/中立回冷却、成功恢复；旧epoch成功/失败不能覆盖新状态；connect成功但404/503不恢复；输入400/429不摘除 |
| 04 请求/连接生命周期 | 正常非流及流HTTP完成即释放inflight，下游未排空仍为0；RST/超时/坏定界/预算不足/pool满/停止均恰一次归零；摘除清idle，旧lease不能再归池；构造失败/析构/多次终结及Trial取消无泄漏；停止含活动trial/idle/stream |
| 05 端到端边界 | 同时2模型不串请求/Host/正文；已提交流故障截断无二次状态/伪零块；未提交保持502/504、未知/全摘除503路径精确；单请求后端计数≤1，无重试；至少3次摘除→试探恢复循环/实例 |
| 06 交付与证据 | 三预设完整CTest含新增Routing/RoutingE2E，格式与人工检查，独立Reviewer同关键场景和历史/源身份，中文配置/状态/局限文档完整；所有自有进程回收、活动inflight/lease/timer及预算排空 |

新增路径以确定性门控而非长sleep验证；健康时钟单测精确推进，socket测试用短合法cooldown与有限等待断言。三预设每套完整CTest独立执行；无需完整P1矩阵、旧600/300秒soak或再次加载真实模型，S1协议/健康通过多受控实例模拟即可，真实综合验收属于S3。任何旧断言与新路由模式冲突应分类legacy与新语义，不能修改旧预期掩盖回归。

## 8. 路线、文档与验收门槛

原生WSL /bin/bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway。各角色build-local/角色/v0.3-s1/{tmp,cache,evidence,debug,release,asan}，Python/构建前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME；独立构建/端口/进程，不共用可变测试状态。Socket和LSan已知边界首次精确升级，无下载或全局安装。具体构建命令为cmake --preset debug -B build-local/builder/v0.3-s1/debug，cmake --build该目录 -j4，ctest --test-dir该目录 --output-on-failure；release/asan分别替换相应preset和目录，Reviewer替换角色路径；禁止关闭检测器规避沙箱。

Builder新增breakdown/报告、来源变化及配置说明；Reviewer输出独立报告、逐AC证据/源及binary SHA。Leader待PASS再同步CHANGELOG和最终阶段状态，当前规划不写已实现。无现存债务清单/债项，不创建空文件。范围/接口/验收实质变化须Leader正式变更，不静默修改Approved；P1/S3所有历史保护。用户完成后本地提交不推送，由协调者执行。无未接受发现且所有AC证据/文档齐全才完成；不以单测数或文档存在代替行为验收，不宣称MVP/性能收益。
