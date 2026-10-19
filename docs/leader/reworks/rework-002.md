# V0.1/S2 返工 002：响应后的有界分阶段关闭

## 1. 权威与状态

- 状态：`Approved`；批准日期：2026-10-18；批准人：Leader (Zeus)，依据用户“你来决策吧”“推送好了，开始s2吧”及 Olympus 执行委托。
- 适用：V0.1/S2，第 **1/2** 轮统一返工，阶段 `返工中` / 编排 `Reworking`。文件序号002是全仓返工编号，不表示本阶段第二轮。S1 rework-001和历史2/2不动。
- 基线：[S2设计](../designs/V0.1/S2-design.md)，SHA-256 `a8d0206472e85bbb8facc5ba668c1aa4964803f48d7737cca659855aafc9de51`；[审查计划](../../reviewer/reviews/V0.1/S2-review.md)，SHA-256 `c8ad195e1c0a75155f91912179dc92bcd9187bf281329a063ef49b733a63c471`。保留原字节。
- 触发：[Reviewer S2-001 FAIL](../../reviewer/reports/V0.1/S2-report-001.md)的S2-F-001 Major和S2-F-002 Minor；结合[Builder S2-001](../../builder/reports/V0.1/S2-report-001.md)。当前无其他S2返工文件。
- 本文明确修订设计§5第7步“输出进入Socket后关闭”的实现时序，以及§6/7/8相关终结、计量和截止语义；保留REQ/AC-03—07的首响应完整、额外输入不派发、公平与有界资源验收。原设计其余条款全部保持，不改变API、配置或依赖。

## 2. 证据与决定

独立 `build-local/reviewer/s2/evidence/CloseWindow.py` 在后端120ms响应、客户端额外发送150ms的窗口，20次中1次首响应0字节，见 `close-window.log`。现有三套7/7测试通过不消除该反例。源码writeDownstream在提交所有输出后直接finishSession，后者关闭下游FD。将后端改为400ms只避开风险窗口。

决定采用**写半关闭后有界读排空**。正常和错误响应都走相同阶段，不把额外输入解析为第二请求；不用延长后端响应时间解决，不开启SO_LINGER=0，不引入池或无界等待。这是既有首响应保障与有限生命周期要求的局部协调，最多保留1秒关闭状态，且受下述更早截止约束；无需新增PM选择。

[RFC 9112 §9.6](https://www.rfc-editor.org/rfc/rfc9112.html#section-9.6)说明立即全关闭可能使最后响应丢失，并描述分阶段关闭。这里只用它解释修正方向；没有抓包，不能把实际RST包序列写成已观测事实。

## 3. Builder 要求

### RW-01：明确关闭阶段（S2-F-001，REQ/AC-03/04）

当一次完整正常或错误响应所有字节成功提交下游Socket：

1. 停止应用层发送，只执行一次成功的 `shutdown(fd, SHUT_WR)`；EINTR可在既有每事件操作预算内重试，重试不重置时刻/截止，硬错误按终结处理。不得先close再补shutdown。
2. 转入独立closing状态，释放不再需要的输出/解析器；上游已结束并关闭，不因closing重建上游。移除OUT兴趣，仅保留需要的读取/错误/关闭观察。
3. 继续按原每回调64KiB/最多64次调用有界读取并丢弃额外数据。EAGAIN只是当前无数据，**不是允许提前全关闭的证据**；保持状态直到EOF或期限。不得因短暂空闲、一次读空、已提交字节或假定ACK完成而提前finish。
4. 对端EOF（含先前已观察到的SHUT_WR）且本地响应已提交并完成写半关闭，可以全关闭；不能在响应写完前仅因下游FIN终结。RST/不可恢复Socket错误或强制停止直接终结。Channel仍按回调后cleanup销毁，终结幂等。
5. closing期间不得调用prepareError生成第二个响应；也不得把释放后输出offset=0误认为“尚未发头”。应有明确状态/标志保证异常只关闭，不再次发送。

窄SessionIo测试接缝可新增shutdown操作以测试顺序、EINTR/失败及一次性，不新增产品配置或故障开关。

### RW-02：固定截止与优先级（REQ/AC-05/06）

定义 `outputCompletedAt` 为最后一个响应字节成功提交时的单调时钟时刻，只写一次。closing上限不配置化，固定1000ms。

| 路径 | closing绝对deadline |
| --- | --- |
| 正常响应 | `min(acceptedAt + total, outputCompletedAt + 1000ms)` |
| 已生成错误响应 | `min(原errorDeadline, outputCompletedAt + 1000ms)`；原errorDeadline仍为创建错误响应时的 `now + min(downstream_write,1000ms)` |

错误输出与随后读排空共享原错误窗口，不新增第二个1000ms宽限，不重新套已过期total使原错误窗口失效。正常响应的downstream_write负责**提交响应期间**，完成后由closing deadline取代，total仍不可跨越。任何读取/事件/EINTR/EOF观察都不刷新deadline；检查deadline不得在closing到期时生成504，只终结。

优先级：第二停止信号/运行时强制停止、RST或不可恢复错误可立即终结；首次停止的shutdown绝对截止对所有阶段（含closing/错误窗口）生效且优先；否则按上述最早deadline或对端EOF终结。正常total和关闭窗口到期时允许强制释放，不等待任意客户端确认。

客户端若持续发送、拒绝关闭、停止读取或出现网络故障，有限期限不能保证其应用层已消费全部响应。SHUT_WR与成功send不等于应用层确认；本文不承诺在RST、强制停止或期限耗尽后仍必然收到完整消息。**这不豁免原120/150ms有限额外输入场景**：客户端正常读取、无主动RST，且总/停止/关闭预算未耗尽时，第一条响应必须完整，第二条绝不派发。

### RW-03：资源、公平与恢复（REQ/AC-04/05）

closing会话仍占activeSessions和完整16MiB预约，直到真实终结后的cleanup一次释放；保持下游Socket/Channel与最多一个会话deadline计时器，不提前归还额度允许无限堆积closing FD。可提前释放大字符串但不能据此减半预约。没有新队列、后台线程或额外上游。最终active/reserved/upstream/timer/FD均回到基线。

新的closing状态可让不主动关闭的客户端占槽最多1000ms；低额度拒绝策略保持，测试应区分响应已提交与资源已释放，而不是删除容量断言。热额外数据仍受公平预算，其他会话和计时器/信号必须推进。每方向读取次数/字节及异常分配行为沿原设计；不缓存额外数据。

### RW-04：规范及范围（S2-F-002，REQ/AC-07）

本轮行为修改限ProxySession、必要的SessionIo接缝/Runtime停止集成、RuntimeTests、GatewayE2E/必要Mock夹具。另对**S2新增或修改的自有C++文件**补相邻函数间空行、头文件职责分组；重点ProxySession、GatewayRuntime、GatewayConfig、SignalSource、SessionIo、RuntimeTests，并检查本阶段迁入/适配文件。保留语义与断言，不对S1无关文件或第三方作全仓排版。

实际clang-format18格式化并检查全部本轮受影响C++后，人工逐文件复核规范要求；工具绿不能代替函数边界/成员分组检查。修改S2来源清单内目标文件时，只更新S2目标hash和差异理由；固定sourcehash、S1记录和第三方不变。

Builder新增 `docs/builder/reports/V0.1/S2-report-002.md`，记录关闭状态/预算/deadline表的对应实现、真实回归命令/结果、人工排版复核文件清单和原始证据；更新breakdown/README真实状态。不得改原Approved设计/审查或历史报告，不提交/发布，不进入S3。

## 4. 独立复验要求

原RV-01—07和完整三套回归继续有效；对本轮补充以下必需项，不能仅将旧FAIL改文字PASS：

- **RV-03/04：** 原CloseWindow.py原120/150ms不改的探针至少运行原20次；另以握手控制验证输出前、输出提交后仍有额外写入，客户端随后完整读取并SHUT_WR。正常200和一种生成错误响应各覆盖。断言精确首响应正文/长度、单最终状态行、上游仅一次（请求在校验阶段拒绝时零次）。无主动RST且预算充足的用例不得允许空/截断响应。
- **RV-04/06：** 可控IO/时钟验证最后send→SHUT_WR→读排空→EOF/截止→close的顺序；shutdown EINTR/错误、EOF先到、EAGAIN不能提前关闭、closing异常不能二次响应、同时就绪与期限触发不重复终结。
- **RV-05/06：** 客户端不关闭并持续发送，固定截止不刷新；正常total较短、错误窗口部分耗尽后写完、错误由total触发、首次shutdown截止较短及第二信号均按优先级释放。观察closing期间额度仍保留、结束后归零，其他请求/计时器进展。真实Socket验证有限时间退出，精确时间边界用可控时钟，避免sleep时序成为唯一证据。
- **RV-07：** 独立构建Debug/Release/ASan+UBSan完整CTest，保留S1和S2全部原断言；新增对照探针和格式工具检查，人工逐项检查函数边界与分组。证据新命名，不覆盖初次失败；日志中明确是接缝还是真实Socket，不虚构TCP包序列。

Reviewer新报告 `docs/reviewer/reports/V0.1/S2-report-002.md`，明确两发现关闭与否。任一仍未满足则FAIL；关键环境验证不可执行则BLOCKED。不存在预批准债务，不以网络保证有边界为由豁免原反例。Leader只能在独立接受后收口。

## 5. 路线和累计边界

继续原生WSL `/bin/bash` login=false、仓库根目录、分支 `codex/v0.1-s2-proxy`，HEAD `bb318d8c55f5851d27cd52e6cd3367f450a5d8dd`。各角色使用 `build-local/<role>/s2/{tmp,cache,evidence}` 并设置临时/缓存变量；独立构建/进程，已知Socket边界按窄范围执行。同级仓库只读，脏文件保留。

本次Leader澄清→Builder修复→Reviewer复验共第1轮，不因文件编号002加一。若以后还需修正最多第2轮，第三轮开始前必须停止；S1计数/成果不动。当前两发现未关闭，阶段未验收。
