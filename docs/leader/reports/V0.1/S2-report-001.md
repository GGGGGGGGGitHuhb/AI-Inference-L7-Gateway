# V0.1/S2 Leader 设计与决策报告 001

日期：2026-10-18。角色：Leader (Zeus)。S2 编排 `Ready for Builder`，阶段 `待实现`，累计返工 **0/2**。

## 第一部分：PM 决策摘要

**当前结论：On Track，可以开始 S2 实现。** 根据用户“推送好了，开始s2吧”和此前技术决策委托，已采纳单上游非流式代理设计及独立审查计划。S1 已验收并推送，原两轮返工保持为历史；这是新阶段，不是继续 S1 返工。

**目标与范围：** 让网关首次成为可独立启动的程序，完成客户端到模拟上游的真实文本请求往返，具有连接/缓冲限额、超时、取消及有限停止。每次请求独立建连，完整校验后回传有界非流式响应。连接池、SSE、多实例调度和GPU留在原后续阶段。

**已完成与未完成：** 核查现有代码和Server固定提交的事件组件及依赖闭包；产出 Approved [S2设计](../../designs/V0.1/S2-design.md)和[审查计划](../../../reviewer/reviews/V0.1/S2-review.md)。尚未实现或运行S2构建/测试，不能启动代理。

**关键决定与风险：** 受控迁入EventLoop/Channel/Epoller六文件，保留token与回调后清理语义；单线程降低状态协调成本。使用静态IPv4配置、每会话固定保守额度，容量外直接关闭，首版不排队。完整响应缓存便于在发头前发现坏上游，但受4MiB响应上限约束，不适合流式。风险集中在短写/断连、旧事件与超时竞态，已明确独立验收。

**PM 决策：None；重大范围偏差/债务接受：None。** 这些常规选择属于既有委托，不引入收费资源、第三方大依赖、旧仓库修改或发布。S1已推送不等于main合并或正式发布；S2不自行提交/推送。

**下一步：** Builder (Hephaestus) 实现并自测，Reviewer (Athena) 独立验证，Leader据结果收口。完成条件是真实代理链路、异常路径及资源回收通过，而非仅能编译或解析器测试通过。

## 第二部分：详细工作记录

本部分供 PM 按需查阅。

### 权威、前置状态与授权

读取用户AGENTS、agent-execution-route；沿用已读personal-cpp-standards完整规则正反例、plan-project-docs与Leader通用模板（项目无角色指南），另读stage-design/review指南。原S1设计/审查/rework、Leader004和Reviewer002明确完成边界；当前ARCHITECTURE/ROADMAP作为S2范围依据。没有待处理技术债，不为新阶段创建空台账。

最新用户明确授权“推送好了，开始s2吧”，结合此前“你来决策吧”决定S2内部技术细节，批准权威为本报告引用的S2设计和审查计划。没有增加版本范围、降低验收或自行发布。S1历史文件保持原字节，S2累计0，纠正上限按本阶段重新开始。

本地核实初始工作区干净，分支 `codex/v0.1-s2-proxy`、HEAD `bb318d8c55f5851d27cd52e6cd3367f450a5d8dd`。S1远端同名分支与该提交一致来自协调者已执行的ls-remote交接；本角色补查受本机代理127.0.0.1:7890连接失败所阻，未重复尝试或将失败说成独立确认。未合并main/发布，远端状态不阻止基于已核实本地提交开展设计。

### 复用调查与设计理由

固定Server来源 `2a93aa7f492640902386677c4d901b0fd193bb09`。完整读取EventLoop/Channel/Epoller六文件固定内容；Server当前EventLoop/Channel工作区存在修改，因此不用工作区复制。源hash/includes审计存 `build-local/leader/s2/evidence/reuse-source-audit.json`，实施时Builder另交可跟踪S2来源记录。

直接依赖只有已有NonCopyable/TimerQueue和标准/Linux接口；EventLoop包含有限任务队列与control/wakeup能力，但不要求引入线程池或TcpServer。关键安全机制为单调注册token、防fd复用串扰、回调后cleanup、timer cutoff和线程归属检查。命名/注册回调需适配当前规范，源测试friend/业务注释可最小清理；保留的核心安全语义必须在Gateway重新测，未对源项目运行测试。

现有HttpParser采用完整有界消息，HttpNormalization返回拥有正文的字符串，适合非流式S2。需要明确Connection close序列化、原始/规范化副本预算，以及半关闭与RST的不同语义。采用16MiB保守逻辑存储预约和连接上限，避免在本阶段建设复杂全局调度器；不把它误写成RSS承诺。

静态IPv4配置避免DNS线程/运行期阻塞；signalfd在单事件线程处理停止，避免异步handler里管理对象。connect成功由SO_ERROR确认，发送与读响应可重叠，解决大请求早期最终错误；下游必须完整响应后才发送，以保留502错误替换能力。S3再设计连接复用，V0.2再做持续流式背压。

### 交付、检查和后续边界

新增S2-design、S2-review和本报告，7组REQ/AC/RV逐项追溯。同步README/ROADMAP/ARCHITECTURE当前阶段与S1已推送状态；CHANGELOG只追加交付状态说明，不把待实现S2写成已交付。旧S1“未提交/未开始S2”记录是当时快照，保留历史报告。

实现文件边界、低层可选项、配置接口、错误表、固定预算、deadline/停止及验证路径均在设计；审查计划规定独立目录、真正Client→Gateway→Mock、罕见syscall确定性注入与真实Socket相结合、完整三套回归和异常回收。

执行路线为原生WSL2 `/bin/bash` login=false，cwd仓库；Leader脚本TMPDIR/TMP/TEMP/XDG_CACHE_HOME指向 `build-local/leader/s2/{tmp,cache}`，证据独立保存在s2目录。Builder/Reviewer按各自s2目录隔离；Socket已知权限边界按窄范围执行。无新系统包、旧仓库修改、产品代码变更或后台任务。

交接前检查文档相对链接、围栏、尾空白、两层报告、REQ/AC/RV映射与根状态，并保护S1历史散列；证据 `build-local/leader/s2/evidence/design-doc-check.log`。本轮未编译、未运行S2测试，没有预判阶段通过。协调者核对权威后可交Builder执行，S2仍待实现。
