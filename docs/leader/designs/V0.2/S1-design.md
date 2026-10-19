# V0.2/S1：SSE字节增量代理链路

## 1. 状态、批准与前置

- 状态：`Approved`；阶段：待实现；编排Ready for Builder；日期及批准日期2026-10-19。批准人Leader (Zeus)，依据用户“已推送，开始v0.2/s1吧”、既有“你来决策吧”与Olympus委托。
- 批准包：[本设计](S1-design.md)、[审查计划](../../../reviewer/reviews/V0.2/S1-review.md)、[Leader001](../../reports/V0.2/S1-report-001.md)。尚无本阶段实现或测试结果。
- 起点 `d653e9c400517783d5d33025a0b66a737c8256eb`；协调者已核验origin/codex/v0.1-s3-connection-reuse同提交，V0.1三个阶段独立接受。当前分支 `codex/v0.2-s1-streaming`，初始干净。
- 新阶段累计返工0/2；V0.1各阶段历史计数与原设计/报告保持。当前没有V0.2返工或已接受债项；后续第三轮纠正前按Olympus停止。
- 最新用户规则“以后每次工作完成都提交，不推送”：本阶段接受/收口后由协调者本地提交；Leader/Builder/Reviewer不自行提交，任何角色不得推送。旧阶段禁止提交的历史条款不覆盖此新授权。

## 2. 目标和分阶段边界

客户端发出stream=true的既有文本API请求，Gateway在验证完整最终响应头后，持续转发SSE解码正文的已到达字节，不等完整HTTP响应、完整HTTP chunk或完整SSE event。下游采用规范HTTP/1.1 chunked封装，能够分辨有确定定界的HTTP完成与中断；保留非流式代理、池和closing行为。

本S1包含协议增量接口、流式发送状态、有限硬缓存/总量/时间约束、模拟首片/片间延迟及异常验证。**不在S1实现高低水位暂停恢复、完整流空闲/写进展超时策略、细粒度全进程动态缓冲账本**，这些属于路线V0.2/S2；S1缓冲将满时直接有界失败，不能无限等待或分配。已有16MiB/会话预约和连接额度继续提供保守进程约束。S3才做真实后端/模型版本与稳定性集成。

不引入新依赖、GPU、多后端、队列、重试、SSE事件解析器、token计数、厂商转换、EventSource重连/Last-Event-ID、下游keep-alive、HTTP2/TLS或跨项目修改。SSE正文为opaque bytes，不验证UTF-8/event JSON、不识别或合成data: [DONE]，不声称完整OpenAI协议兼容。

## 3. 请求与最终响应选择（REQ-01）

`validateTextRequest`接受stream布尔true/false，metadata.stream准确反映值，省略为false；其余S1既有字段/JSON/体积/方法/路径规则不变，原body字节原样发送。stream为字符串/数字/null仍400 invalid_request，重复/未知字段仍原拒绝。只更新历史测试中“合法true必须拒绝”的预期，并增加相应真/假测试，不删除其他旧断言。

stream=false或省略：V0.1原路径与response 4MiB/wire8MiB、完整缓冲、拒绝text/event-stream及S3归池条件保持。流式请求仍先完整读完/校验受限请求，才向唯一上游派发，不做请求体流上传。

stream=true最终响应选择：

| 上游最终响应 | 行为 |
| --- | --- |
| HTTP1.1 200且唯一Content-Type为text/event-stream | 验证头完成后进入正文流转发 |
| 非SSE最终响应（含200 JSON、4xx/5xx、204/304） | 回退V0.1有界完整响应路径，原状态/正文语义保持，不强求后端必须提供流 |
| 非200且Content-Type为text/event-stream | 502 upstream_error，不发送该上游最终响应 |
| 多个Content-Type（流请求），SSE charset/参数非法，其他头/编码/定界错误 | 502 upstream_error；发送前后规则见§6 |

流请求的响应Content-Type允许缺失（归非SSE），单字段非SSE沿原规则；text/event-stream媒体类型大小写不敏感，允许外侧OWS及单个 `charset=utf-8` 或 `charset="utf-8"`，参数名/UTF-8值大小写不敏感、等号两侧OWS允许；其他参数、重复参数或charset拒绝。这是受控兼容子集，不宽泛承诺MIME全语法。

最终头检查必须在任何下游输出前完成：HTTP版本/状态、CL单值与TE冲突、编码identity、Connection危险token、trailer/upgrade、头字节/个数、SSE选择等全部沿严格策略。保留合法至多8条1xx的内部消费，不下发1xx，也不在1xx阶段选择正文模式；101拒绝。不能在去除原头后才检查冲突。

## 4. 增量解析与输出边界（REQ-02）

`src/http/HttpParser`新增明确的响应流选项/事件接口（具体类型由Builder决定），默认保持原buffered接口行为。必须分别暴露“已验证最终头”“本次解码正文字节”“消息完成/拒绝及原始consumedBytes”。在最终头已选择SSE之后，body不追加到HttpMessage.body；以独立累计计数执行总量限制，不能用body.size()假作已收字节。非SSE回退必须在消费正文前选择原4MiB/8MiB预算。

支持CL精确长度、chunked解码和EOF定界流；chunk扩展仍沿V0.1前置有界严格校验，禁止非空trailers或Trailer声明。chunk data可在剩余chunk尚未到达时转发，不能等待chunk末尾CRLF。错误CRLF或后来发现的坏chunk可中断已经开始的下游，不回滚字节，不伪造成功结尾。原consumedBytes、wire统计、头/1xx/分块预算和终态稳定性保持。

C回调仍noexcept捕获全部异常。注册回调遵守personal-cpp-standards具名事件与短转发；在parseBytes/finishInput期间，回调只检查/复制必要的有界数据，不做Socket写入、重入解析、reset/删除parser/session或销毁正在执行回调。所有状态迁移/终结在解析调用返回后执行。借用string_view仅在回调当次有效，不存裸视图跨回调；若持久保存，先复制到受限所有者。对象寿命依原EventLoop回调后cleanup，不让parser callback成为新的销毁入口。

推荐一次recv≤16KiB，对其中onBody产生的多个碎片先合并到≤16KiB临时片，再在该parse调用返回后封装chunk/调度OUT；不要把当前逐字节llhttp馈送变成每字节分配一个队列节点。不能为了合并而等待下一recv、完整event或完整chunk。若本次parse出现错误，先按发送状态处理错误，不能把失败调用产生的候选输出当完整成功提交。

下游流式头：保留状态200与合法端到端头（包括Content-Type），沿既有hop-by-hop/Connection token移除规则；去掉上游CL/TE，生成恰好一个 `Transfer-Encoding: chunked`、`Connection: close`、Via。不同时发送CL，不复制上游chunk大小行/扩展为正文，不新增SSE消息。不按正文字符串搜索修改header。

每次chunk承载当前可用的一段解码正文，chunk划分可不同于上游；解码后的下游正文必须按序逐字节相同。只有解析器确认完整最终HTTP消息后才排入一次 `0\r\n\r\n`；此后输出排空、SHUT_WR、S2有界closing，不能在临时输出队列空时提前结束流。

## 5. 结束语义与连接租约（REQ-03）

- CL：恰好CL字节为HTTP完成，提前EOF为中断；chunked：零chunk及空trailer段完整才完成，无零chunkEOF为中断。
- EOF定界：无CL/TE时正常read=0是HTTP完成，发下游终止chunk；RST/硬错误/超时不是正常EOF。TCP正常EOF无法判断应用层SSE是否“生成完整”，因此这里只承诺HTTP定界，不声明完整事件/[DONE]/模型完成。没有[DONE]的合法HTTP完成仍成功；收到[DONE]后仍继续转发后续字节直到HTTP完成。
- 同块终态后的尾随字节沿V0.1首响应语义不作为第二响应，首条合法流可以完成，连接必关。body结束后的任何迟到数据不再喂终态parser，不生成第二响应。
- 所有stream=true请求（包括非SSE回退）都通过已有池获取一个容量受限租约，但生成上游Connection: close；结束一律invalidate，不归池。允许借用原干净idle，随后关闭，不新增无额度的专用连接。stream=false完整保留S3复用；不把stream请求回退视为原非流式复用承诺。
- 这是S1流式运输基线的保守选择，不声称本阶段实现流式池复用；后续若启用需新基线资格验证。正常流HTTP完成可以先释放上游，待下游排空期间仍保留会话16MiB预约和下游资源。
- 上游在请求尚未写完时给出最终200 SSE头：允许开始读/转发，立即停止后续请求体写入、释放待发请求输出，保持显式“未完整发送”标志；继续读取该响应，结束关闭不归池。不得因清空offset误判请求已发送完成，不重试。非SSE回退保留S2早期响应行为。
- 读取完整请求后的客户端SHUT_WR仍不是取消，照常返回流；RST/下游不可恢复写错使上游失效，不能称后端GPU已停止。停止沿S3：停止新派发、已有流有限排空、deadline/第二信号强制关闭；stream无终止chunk的强制退出不得伪造HTTP完成。

## 6. 发送状态与异常语义（REQ-04）

显式记录 `responseStarted`（首个最终响应字节被send接受即true，包含只发了状态行片段）、HTTP消息完成、终止chunk排入/发送完成、pending输出和终结原因；不能用可压缩/清空的offset==0替代是否已发头。上游读取、下游写入可同时激活；流模式输出空只禁用OUT，仍继续读IN，绝不提前SHUT_WR。

| 异常 | 尚未send任何最终响应字节 | 已send至少一字节 |
| --- | --- | --- |
| 上游头/帧错误、截断、body/wire/chunk超限、IO失败 | 清理未发送流候选，502 upstream_error | 失效上游并终结连接；无第二状态行、无终止chunk、无伪造SSE错误/[DONE] |
| response/total超时 | 沿原504分类（接收期total仍408） | 终结，不追加HTTP错误 |
| streaming pending硬上限 | 502 stream_buffer_limit | 同样中断，不追加内容 |
| 下游写期限、RST/写错、强制停止 | 沿原关闭规则，无交付承诺 | 关闭，无成功结尾 |
| 内部可恢复异常 | 尽力500 internal_error，无法分配则关闭 | 关闭，无二次响应 |

未发送的候选200头可以被清理并替换为一个错误；一旦有任何final字节提交不可替换。错误输出沿V0.1错误窗口与closing规则，不能重置errorDeadline；正常输出仅在HTTP完成且所有输出（含终止chunk）成功写完后进入closing。中断可以直接finish，不能为伪装成功而半关闭前补零chunk。期限/RST等边界不承诺客户端一定消费已提交的前缀。

## 7. 有限资源和期限（REQ-05）

无新增产品配置键；原timeout和连接/预约配置继续生效。流模式固定预算：

| 资源 | 硬上限 |
| --- | --- |
| 当前流待发送线缆字节（头+chunk封装+正文+终止块） | 256KiB |
| 单次解码暂存片/recv scratch | 分别≤16KiB；不得为每字节分配节点 |
| 单流累计解码正文 | 8MiB |
| 单流累计上游wire（含头/1xx/chunk开销） | 16MiB |
| 其余头/1xx/chunk大小行/非终止chunk数 | V0.1原限制（含65536块） |
| 每会话协议存储预约 | 原16MiB，进入closing仍保留 |

append前溢出安全检查，计量包括chunk封装。已发送前缀及时消费/压缩，不能保存整个流历史，container节点/capacity增长亦须有界；若使用string，其capacity上界须说明实现约束，不能仅“size≤limit”而允许历史增长。流总8MiB不是常驻缓冲，不得让parser还存body副本。Builder列同时存活请求/元数据/解析/输出/暂存的保守上界，仍≤16MiB；allocator/RSS/内核buffer不混称为精确预约值。

S1不暂停上游等待下游降水位；遇硬上限按§6结束，测试明确慢消费者可能被中断。保留每方向64KiB/64次每事件操作额度，输出有数据才启用OUT；不要通过删去硬限制或增长buffer消除慢读失败。可测试streamPending/peakStreamPending/decodedTotal/wireTotal或等价内部快照，无管理HTTP端点/无prompt日志。

时间仍steady_clock：connect/request/upstream-write/total保持；流response deadline=本次连接启用（含租约复用启用）+现有timeouts.response，覆盖整个响应到HTTP完成，不因首片/片间流量刷新；HTTP完成后移除此response期限，total继续。默认response30秒/total60秒，因此本S1不声称无限时长推理流。

流下游写期限采用**连续非空输出批次**：pending从空变非空时固定now+timeouts.downstream_write，直到pending完全排空才撤销；部分写进展不刷新；下一次空→非空可创建新批次期限。它限制持续积压，不是S2的写进展超时策略。response/total、shutdown期限依然同时有效；headers也是输出批次，不能用一直读片段推迟旧写期限。非流式downstream_write保持V0.1从完整输出开始的语义。新流状态必须在checkDeadline里明确优先级：强制shutdown最高，其他取最早；同刻total沿既有规则。closing/error窗口继承V0.1 rework-002，不新增无限宽限。

## 8. 实施与必需证据（REQ-06/07）

推荐顺序：请求metadata和解析事件/预算→头选择/流输出编码→会话读写并行与提交标志→期限/错误/租约停止→模拟流E2E和回归。变更范围为src/http、TextRequest、ProxySession/必要SessionIo/Runtime快照、测试支持/新增流测试、CMake/README；pool仅必要装配，不重写net或第三方。具体类拆分由Builder决定，不能另起整套HTTP解析器或把业务SSE语义放net。

新建 `docs/references/V0.2-S1-changes.md`记录修改的既有文件d653e9c基线hash、当前hash和原因；旧来源manifest/权威/报告只读。Builder写 `docs/builder/breakdowns/V0.2/S1-breakdown.md` 与报告001，记录实现/预算、真实证据、格式化和人工检查，保留失败日志，不自行提交。

测试必须有独立CTests入口覆盖增量解析和真实StreamingE2E（具体目标名由Builder报告，ctest -N可发现），Debug/Release/ASan+UBSan完整回归；Release负控exit1；实际clang-format18 -i和dry-run，人工逐函数边界/回调/职责分组复核。原V0.1功能与S2 closing窗口20次及正常/错误握手回归保持。旧stream=true拒绝断言是本设计唯一主动更新的请求语义；默认buffered响应拒SSE保持。

首片证明使用真实loopback后端和显式控制通道：后端发送合法最终头及SSE未结束前缀（例 `data: hel`，连空行都没有，且HTTP chunk也尚未完整），**等客户端实际读到该正文前缀并通知控制器后**才发剩余内容/HTTP结束。否则超时失败，不以固定sleep或最终文本等价代替增量证明。另测头先到/body未到时客户端已读到最终头；chunk/CL/EOF三种流均覆盖，chunk分段跨CRLF/扩展，UTF-8多字节/BOM/注释/多行data作为字节透明样本。

流结束分别验证：有/无[DONE]、[DONE]之后继续数据、正常EOF、CL欠长、无终止chunkEOF、非法后续chunk、非法trailer、RST、timeout。显式先收到正文再触发错误，客户端须识别chunked未完成；绝不把TCP EOF当所有下游chunked流成功。发送前错误用可控IO保证send=0，之后错误用部分状态行发送/全部头发送两种，测offset压缩归零后异常仍无第二状态行。

资源验证用接缝精确触发pending边界（limit−1/limit/limit+1，包含封装）、所有总量/期限、异常分配和清理；真实慢客户端/混合非流式/长流>4MiB（≤8MiB）证明无整流缓存、终态资源归零及正常请求不被拖死。不要求slow-reader恢复，那是S2。首次/二次信号覆盖活动流、等待首片、待发输出、closing，无僵尸/端口残留。真实后端/GPU和新性能基准非本阶段要求，不重复旧18cell当新增流性能证明。

| 需求/验收 | 通过条件 | 独立验证 |
| --- | --- | --- |
| REQ/AC-01 | stream metadata与最终响应矩阵正确；非流式兼容，非法头/模式不提前输出 | RV-01 API/头选择单元和E2E |
| REQ/AC-02 | 回调寿命/异常安全，body不累计；最终头和不完整event/chunk前缀可立即送达，解码字节完全一致 | RV-02 任意分片+首片门控 |
| REQ/AC-03 | CL/chunked/EOF结束正确，不依赖[DONE]；stream租约不归池，非流式继续复用，早期响应/半关闭/停止清理 | RV-03 定界/租约/真实Socket |
| REQ/AC-04 | 发前一个错误、发后中断且无第二状态行/假终止块；临时输出空不终结，部分写不丢字节 | RV-04 故障接缝和已读前缀后故障 |
| REQ/AC-05 | pending/总量/对象/16MiB约束和固定deadline生效；慢读溢出有限关闭，无泄漏/热事件饿死 | RV-05 边界/资源/超时 |
| REQ/AC-06 | 三预设完整回归、旧池/closing与新真实流验证、格式/来源证据完备 | RV-06 回归和规范 |
| REQ/AC-07 | 状态/README支持矩阵与实际一致；原权威保护、独立接受后才收口提交，不推送 | RV-07 交付审计 |

## 9. 执行路线与标准依据

原生WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`。角色独立 `build-local/<role>/v0.2-s1/{tmp,cache,evidence,debug,release,asan}`；构建/Python前创建并设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME；构建用preset加显式-B，Reviewer独立构建/端口/进程。Socket/loopback及LSan ptrace已知边界直接精确窄升级，不重复失败、不关闭检查；无需联网下载或安装依赖。

项目无角色指南/AGENTS新增资源，回退全局plan-project-docs角色模板；没有已接受债项，不创建空债台账。重大范围/兼容变化须回Leader建立新权威。阶段0/2、最多两轮纠正，不能以文件编号重置。

一手规范只用于解释分层：[RFC9112 §6—8](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3)定义HTTP长度、分块和不完整消息；[HTML SSE解析](https://html.spec.whatwg.org/multipage/server-sent-events.html#parsing-an-event-stream)定义事件层处理。Gateway不执行后者的事件派发，不因事件尚未凑齐而延迟传输。规范读取日期2026-10-19；具体受支持子集与限制以本设计为准。
