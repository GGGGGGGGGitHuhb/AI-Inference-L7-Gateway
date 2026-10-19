# V0.2/S1 Leader 规划与决策报告001

日期2026-10-19；Leader (Zeus)。阶段待实现；编排Ready for Builder；本阶段累计返工0/2，历史阶段计数保留。

## 第一部分：PM 决策摘要

**当前结论：On Track，可以开始流式链路实现。** 已按用户“已推送，开始v0.2/s1吧”和“你来决策吧”批准本阶段基线，无需新增常规技术确认。

**计划与实际：** 目标是让客户端在上游尚未完成响应、甚至尚未完成一个SSE event时就收到正文前缀。设计和独立审查计划已完成，当前实现仍为已验收V0.1，尚无S1流式运行结果。将支持stream=true、严格最终头检查、增量正文/分块输出和确定的正常结束或中断，保留非流式行为。

**已验证成果：** 当前分支codex/v0.2-s1-streaming、HEAD d653e9c，初始干净；协调者已核验该V0.1提交推送到阶段分支。源码确认当前HttpParser累积body、TextRequest拒绝true、ProxySession等待完整响应；这些是本阶段必要变更点。

**取舍与风险：** 首阶段采用固定硬缓存/总量/时间上限，慢客户端可能被中断；高低水位暂停恢复留S2。流请求结束关闭上游，不归池；既有非流式复用保持。只转发SSE字节，不识别[DONE]、不承诺模型生成完成；已发出任何响应字节后发生错误只中断，不伪造成功尾块。重大范围偏差、成本或需接受债项：None。

**PM决策：None。** 采纳[S1设计](../../designs/V0.2/S1-design.md)与[审查计划](../../../reviewer/reviews/V0.2/S1-review.md)为当前实施/验收基线；没有新依赖、GPU或外部服务成本。用户新规则“以后每次工作完成都提交，不推送”适用：接受收口后由协调者本地提交，禁止推送。

**下一步：** Builder (Hephaestus)实现并提供首片握手、异常/资源与三预设证据，Reviewer (Athena)独立验证，Leader收口后协调者提交。S1完成不代表V0.2完成，不进入S2/S3或发布。

## 第二部分：详细工作记录

本部分供PM按需查阅。

### 输入、基线与权限

已读取/复用当前适用Olympus、agent-execution-route、personal-cpp-standards完整规范/正反例、plan-project-docs及Leader模板PM/两层报告契约、阶段/根文档指南；项目未发现新增AGENTS/专用角色指南，继续回退全局模板。没有已接受技术债或债台账。

读取当前根README/ROADMAP/ARCHITECTURE及先前V0.1设计/返工、S3最新Leader002/Builder002/Reviewer002与原独立接受链；新读HttpParser完整增量/头/body/终态路径、TextRequest字段验证、HttpNormalization、ProxySession读写/closing/租约与ConnectionPool接口。V0.1设计中的非流式限制是已完成阶段范围，本V0.2/S1按路线增加stream=true，不篡改旧权威。

当前原生WSL `/bin/bash` login=false、cwd `/home/power/projects/AI-Inference-L7-Gateway`；分支codex/v0.2-s1-streaming，HEAD `d653e9c400517783d5d33025a0b66a737c8256eb`。协调者交接明确已核验origin/codex/v0.1-s3-connection-reuse同SHA，本角色不重复远端查询。角色临时/缓存/证据为build-local/leader/v0.2-s1，脚本前显式设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME；Builder/Reviewer使用独立同结构目录，不覆盖V0.1证据。

用户最新明确授权每次工作完成后提交、不推送，优先于旧阶段“不提交”条款；由协调者收口后执行，角色不得抢先提交，当前规划完成不代表产品阶段完成。无跨项目写入、新依赖下载或发布授权。

### 决策及实现依据

1. TextSax当前stream=true直接unsupported_stream，metadata.stream未设置；本阶段准确设置布尔值并保持body原样，原字段校验不扩展。响应200 SSE才走流，其他非SSE结果完整缓冲回退，避免后端忽略stream或返回错误JSON被误当事件流。
2. HttpParser当前handleBody只append，bodyLimit依赖body.size；新增sink模式必须使用独立累计量，回调临时视图不能逃逸。最终头选择先完成全部严格校验，1xx不触发外发；默认buffered解析不放开SSE。
3. 当前逐字节deliverByte可能产生大量body回调，设计要求每次recv有界合并，不按每字节建立队列/HTTP chunk，也不等待整event/chunk。最终头/正文事件不直接IO或销毁对象，parse返回后再处理状态，保留C异常边界和cleanup寿命。
4. 当前ProxySession输出从完整响应构造且用offset识别发送。新流要独立responseStarted标志：首字节send才commit，已排队但未send的头可撤回，offset压缩归零不撤销commit。HTTP完成才入零chunk，暂空仅关闭OUT兴趣；错误后无零chunk、无第二状态行。
5. 流请求沿pool容量获取但生成Connection close、最终失效不归池；nonstream S3复用不变。early SSE头停止未发完请求体，显式写完成状态不能因释放string而伪真。半关闭仍不等取消，正常完成/中断与上游GPU计算结束严格区分。
6. pending256KiB、暂存16KiB、解码总8MiB/wire16MiB、原header/chunk数限制，常驻逻辑存储仍落16MiB/会话预约；原response全程绝对期限及total保持，写期限按连续非空输出批次固定、不按每次部分进展刷新。满缓冲有限失败是S1基线，S2才增加高低水位/完整动态预算与写进展协同。
7. 模拟后端门控等待客户端确实收到未完成event/chunk前缀才发尾部，单看最终文本/粗延迟无法验收真正增量。独立测试覆盖正常CL/chunked/EOF、[DONE]透明性、发前发后错误、部分写、坏chunk尾/截断、期限/停止/资源归零。

一手规范核读：[RFC9112 HTTP定界/分块与不完整消息](https://www.rfc-editor.org/rfc/rfc9112.html#section-6.3)、[HTML SSE解析层](https://html.spec.whatwg.org/multipage/server-sent-events.html#parsing-an-event-stream)。规范解释HTTP与事件层不同，项目不实现EventSource派发，不把正常EOF解释成模型完成；受限参数与硬预算由本阶段设计规定。

### 输出与身份

新增：

- `docs/leader/designs/V0.2/S1-design.md`，Approved，SHA256 `11ecb703242f5c1077e3205ed2de5ab43f7b53d619e81c1b6dea5b6507d02711`。
- `docs/reviewer/reviews/V0.2/S1-review.md`，Approved，SHA256 `272ed417a6b8aeb4fab819fd7f288c13bb7c7729a7f0a6f2bea1301149e1e1f9`。
- 本报告001，两层合同；AC01—07与RV01—07逐项对应。

根README/ROADMAP/ARCHITECTURE同步V0.1已提交推送事实、新V0.2/S1待实现0/2与已批准增量方向；README明确用户新提交政策。未追加CHANGELOG未实现功能，未改变V0.2/S2/S3边界、版本顺序或原历史文档。

### 检查、交接和未完成项

只进行了读取、文档编辑、身份/链接/围栏/空白/旧文件保护检查；未运行产品测试或声称性能。证据 `build-local/leader/v0.2-s1/evidence/planning-doc-check.log`、`planning-protected.json`与`planning-identity.log`。原产品/测试/第三方/历史文档未改。

Builder新增V0.2/S1-breakdown、变化来源记录和报告001，Reviewer独立报告001；独立三预设完整回归与首片门控为必需。Socket/LSan已知边界精确窄升级，不跳过。没有新性能矩阵或真实GPU集成要求；既有V0.1初始成本结果保持其原工作负载身份。

当前没有待澄清技术冲突、额外PM决策或已接受债项。阶段0/2，实施/验证/接受/收口尚未完成，不能提前标记V0.2/S1或V0.2完成。未派生代理、提交/推送或启动后台工作。
