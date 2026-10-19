# V0.1/S3 Leader 规划与决策报告 001

日期：2026-10-19；Leader (Zeus)。阶段：待实现；编排：Ready for Builder；S3累计返工0/2。S1历史2/2、S2历史1/2保留。

## 第一部分：PM 决策摘要

**当前结论：On Track，可以开始S3实现。** 用户已要求“开始s3的工作吧”，Leader沿用技术决策委托批准阶段基线，常规内部取舍无需再次确认。

**计划与实际：** 本阶段让多个下游请求顺序复用唯一后端的连接，设置总容量、空闲容量/期限与安全归还规则，补齐直连/代理初始成本记录。设计与独立审查计划已完成，产品代码尚未改动；下游继续S2每连接单请求，不加入队列、多后端、自动重试或流式。

**已验证成果：** 当前HEAD为S2本地提交3cb6524、S3分支已建立；已核读S2独立PASS、关闭修正与实际源码，确认现有会话总在完整响应后关闭上游，需要在S3显式增加租约生命周期。这里是源码/权威核对，尚无S3运行或性能结果。

**重要取舍与风险：** 只有完整响应、干净连接且下游成功提交输出并写半关闭后才归池；慢客户端因此暂占上游槽，满池立即503，换取清晰的取消/所有权边界。陈旧连接可被探测，借出后仍可能失效，当前请求报错且绝不重试。成本实验只建立可复现观测，不承诺更快；不声称能识别任意恶意后端在未来伪造的响应。重大范围偏差、成本或需接受的技术债：None。

**PM决策：None。** 本次按现有S3路线和“你来决策吧”授权采纳[S3-design](../../designs/V0.1/S3-design.md)与[S3-review](../../../reviewer/reviews/V0.1/S3-review.md)，授权Builder实现、Reviewer独立验证及通过后Leader收口。不包含提交/推送/正式发布，S2提交远端状态本轮未核验。

**下一步：** Builder (Hephaestus)完成有界池、会话接入及测试/成本证据，然后Reviewer (Athena)独立验收。必须所有AC满足、无阻塞发现且文档收口后才可标记S3和V0.1完成；当前V0.1未完成。

## 第二部分：详细工作记录

本部分供PM按需查阅。

### 输入、授权与路线

已读取用户跨项目AGENTS规则、agent-execution-route、orchestrate-olympus-stage、personal-cpp-standards完整规范/正反例、plan-project-docs及Leader模板PM/两层报告契约，相关设计/审查/根文档指南。仓库及祖先未发现额外AGENTS/项目角色指南；继续回退全局Leader模板。无TECH-DEBT-TRACKER或已接受S2债项，不为本次计划创建空债务台账。

当前分支 `codex/v0.1-s3-connection-reuse`；HEAD `3cb65244312d2feef563c2fd755ae8447d4589c5`；开始时工作区干净。WSL2原生 `/bin/bash` login=false、cwd `/home/power/projects/AI-Inference-L7-Gateway`；Leader临时/缓存/证据为 `build-local/leader/s3/{tmp,cache,evidence}`，脚本前设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME。Builder/Reviewer须使用各自同结构目录与构建，不复用旧S2可变证据。无需依赖下载；精确Socket/LSan测试按已知权限边界窄升级。

核读README/ROADMAP/ARCHITECTURE、S2-design/review/rework-002、Leader003、Builder002、Reviewer002，及ProxySession/GatewayRuntime/GatewayConfig/SessionIo/HttpParser/HttpNormalization/Channel/EventLoop接口与实际主路径、RuntimeTests/GatewayE2E入口/CMake配置。旧memory只用于复用边界和实验方法提示，当前事实以本次仓库核验为准。

### 决策与源码依据

1. **只复用上游。** 路线S3明确上游池；目前ProxySession::readDownstream丢弃第二请求并且响应强制close。保留下游契约可保持S2关闭窗口与预约不变量，避免同时建设长连接请求重置/队列。设计§2写明，不依赖含糊“keep-alive”推断两端都复用。
2. **稳定所有权与代次。** Channel::registerEventCallback拒绝注册中更换目标；EventLoop已有唯一token与cleanup。设计§3要求池空闲/租用转换重新注册、退休后析构及稳定租约身份，不把fd当请求ID，也不在回调中替换/销毁执行对象。具体低层类型由Builder实现，必须提供数量上界与独立竞态证据。
3. **保守归还。** 现有completeResponse总closeUpstream，writeUpstream完成后清空string并offset归零，不能据此直接判断早期响应是否可复用。设计要求显式写完成标记、原始Connection token、定界/消费量、关闭事件和下游提交检查；§5明确SHUT_WR后租约已经提交，旧closing不再影响新租约。
4. **容量、污染和no retry。** 默认总/idle各16、idle5s，max_idle=0为关闭对照；满池503，无排队。§6清理已可见污染、归还/借出peek、idle事件监视；借出后失败不换连接重发。边界坦诚：peek不是未来存活或恶意响应因果保证，不能据此宣称无限条件防串扰。
5. **停止与S2限制。** 现有Runtime仅遍历sessions终结。引入池后首次停止还需关闭idle/禁止新派发，第二信号和deadline清空所有租约；cleanup必须含退休池对象。事件外直接requestShutdown仍非SDK契约，既有限制保留，真实产品信号/计时路径必测。
6. **初始成本先定义方法。** 固定三模式、并发1/4、20预热+200样本、三重复，共18cell；闭环、固定文本和1024字节响应、Release、连接/RSS/FD/端到端分布。验收绑定正确性与资源/连接规律，不设事后挑选的速度阈值。完整原始失败保留，不将P99差值当额外P99。

### 基线与交接身份

本轮新增：

- [S3设计](../../designs/V0.1/S3-design.md)，Approved，SHA-256 `2d41cb66f20750105e81dba0b6f7c1b5bce694aee0998290c100f7603a92a127`。
- [S3审查](../../../reviewer/reviews/V0.1/S3-review.md)，Approved，SHA-256 `ca8d3c1dc62809f728aaed083b660c13ff614e678e8dcfd6f703ab6e140e826e`。
- 本报告001。7组REQ/AC分别对应RV-01—07，涵盖所有权、容量/配置、消息资格、陈旧/期限、停止、成本、回归/证据。

同步根README/ROADMAP/ARCHITECTURE：按用户阶段启动及已授权文档治理记录S3待实现，明确上游复用范围、修正S2已本地提交事实；不改版本顺序或扩大架构，不写S3实现/验收/发布。CHANGELOG暂无新实现，不追加虚假交付项。

保留原权威SHA-256：S2-design `a8d0206472e85bbb8facc5ba668c1aa4964803f48d7737cca659855aafc9de51`；S2-review `c8ad195e1c0a75155f91912179dc92bcd9187bf281329a063ef49b733a63c471`；rework-002 `fd8165b4251ca748f179fa9a683fb05ec35588ba7db90823f1f3f5a70a3bdbcf`。S1/S2所有历史报告/权威/来源清单均无修改。

### 文档验证与未完成项

本轮仅执行仓库/源码读取、文档编写、hash与文档检查，不运行产品构建/测试，不替代Reviewer。检查证据 `build-local/leader/s3/evidence/planning-doc-check.log` 与 `planning-identity.log`：新增链接/REQ/AC/RV一致、历史文件对HEAD一致、批准身份与根状态、git diff --check。新权威与本报告内容形成完整交接包；文件hash在协调者交接时再次核验。

Builder应新增 `docs/builder/breakdowns/V0.1/S3-breakdown.md`、报告001、S3变化来源记录和原始验证；Reviewer新报告001。S3实现/全部测试/独立验收/收口仍待完成。当前没有未解决设计冲突、额外PM决策或已接受债项，未启动后台任务、子代理、提交或远程发布。
