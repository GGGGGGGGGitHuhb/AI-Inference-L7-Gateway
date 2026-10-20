# V0.3/S1 Leader 规划报告001

2026-10-20；Leader (Zeus)。Approved / 待实现，Ready for Builder，累计返工0/2。

## 第一部分：PM 决策摘要

**结论与健康状态：On Track，可以开始实现。** 用户已明确“开始v0.3/s1的工作”，并保留“你来决策吧”的技术委托；本方案只落实已规划的模型路由与健康，不需要重复例行批准。

**计划与实际：** 已冻结静态模型映射、轮询/最少在途请求选择、每实例隔离连接池和失败摘除/恢复方案，完成独立验收计划；功能尚未实现。P1已本地提交e231fda，未推送；V0.2验收保持完成。

**重要选择：** 保留旧单上游配置行为。新路由模式只向一次选定实例发送，无重试/队列；失败达到阈值后摘除，冷却后借一次真实用户请求试探，完整HTTP成功才恢复。初始可用只是配置许可，TCP连通不作为模型健康证据；本阶段不验证生成语义或GPU状态。

**取舍与风险：** 被动恢复需要后续流量，试探请求本身可能失败；最少在途统计上游未完成请求，不包含上游完成后的慢客户端排空。旧请求不能撤销新摘除，取消/本地容量不足不误记后端失败，这些列为独立验收重点。需新增接受的重大偏差、债务、成本或阻塞：None。不会顺手优化P1约44ms，也不提前实现S2排队/S3综合验收/V0.4收益实验。

**PM决策：None。** Leader建议直接依本基线实施。下一步由Builder实现并完成三预设回归，再由Reviewer独立验收；通过后Leader收口、协调者本地提交不推送。当前不声明V0.3或MVP完成。

## 第二部分：详细工作记录

本部分供PM按需查阅。

### 权威、身份与路线

[设计](../../designs/V0.3/S1-design.md) SHA256 `8f3aeeee2d137bf484a008630021218da418824f5dfefa2edc05bc61e1a64740`；[审查计划](../../../reviewer/reviews/V0.3/S1-review.md) SHA256 `79e390d108d1686056956462e01bd3b6ad3f49f2876998dae0364281f6dceafc`。批准依据为本轮明确启动与既有技术委托，范围来自ROADMAP V0.3/S1；没有新PM决策或rework。Approved基线交接后冻结，实质变化走正式变更。P1最终[Leader002](../V0.2/P1-report-002.md)和[Reviewer001](../../../reviewer/reports/V0.2/P1-report-001.md)均保留原字节。

分支codex/v0.3-s1-routing-health，HEAD e231fda25879060fcd730f562982f06448f2ba11，规划前工作区clean。原生WSL /bin/bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway；Leader目录build-local/leader/v0.3-s1/下tmp、cache、evidence，执行Python前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。下游各角色独立构建/测试目录，socket及LSan已知边界首次精确升级。无下载、安装、网络请求或真实模型负载。

使用agent-execution-route、plan-project-docs及Olympus，已读个人C++规则与正反例。项目无专用Leader指南/AGENTS，以用户跨项目规则及全局Leader模板为回退；无现存技术债清单且最新独立验收无债，不创建空文件。本轮仅源码读取和文档规划，没有实现或测试通过声明。

### 源码驱动决策

检查GatewayConfig解析/深度、TextRequestMetadata、GatewayRuntime装配/停机、ProxySession建连/非流完成/流终态/错误/超时和ConnectionPool租约。现有model已校验但未路由；Runtime单池及Session直接读取全局upstream地址需改为固定实例目录与池集合。

选择最小被动健康，避免主动探测的额外请求语义、计时器和模型费用；只以当前模型请求的完整协议结果作为观察。模型目录不碰Socket，Runtime持池，Session同步报告结果；健康epoch与连接generation分工，避免旧事件把新摘除状态恢复。请求inflight独立于ConnectionLease的生命周期，使多个idle和下游慢读不会冒充上游负载。

路由模式采用models数组，每model策略和实例清单；最多32模型、64实例，池额度乘积≤1024，既有全局session/缓冲预算保持。旧地址模式不启用新摘除，保存旧配置/任意model兼容；新模式未知model404、无候选503，pool满保持容量错误且不改投。被动试探无需新增健康timer，冷却按既有单调时钟在选择时检查；中立试探退回冷却并释放资格，避免取消后卡死。

具体字段、状态表、epoch与归池条件、响应status/取消/timeout分类及所有AC见设计§3–7。模型语义不解析、SSE仍透明代理，不为健康扩张业务协议。下游已提交流错误维持断流规则；新配置示例与文档在Builder实现后验证。

### 验证与交接

六组AC/RV覆盖配置兼容、RR/LI与模型隔离、健康状态、双租约生命周期、端到端错误/恢复、格式/三预设/文档身份。确定性时钟与socket门控负责关键边界；新增Routing/RoutingE2E作为CTest入口，Reviewer必须独立检查旧epoch、Trial取消、多idle情形。实际格式化工具为仓库clang-format-18，范围限本次C++，另做人读职责分组。

不重跑完整P1矩阵、旧600/300秒soak或另设真实多模型实验；当前改动需三预设完整CTest，旧所有受影响断言保持。既有真实CPU协议接受记录仅作历史，不冒充本轮路由验证。未来S3负责真实综合验收，V0.4另设性能收益实验。

本轮新增设计、审查计划、本报告；README/ROADMAP/ARCHITECTURE追加当前阶段权威节，标明旧P1待提交/V0.3未启动文字为前次快照，P1实际已提交e231fda，S1现为待实现。没有改CHANGELOG验收记录、功能源码、历史Approved或报告。规划保护快照161项、链接/围栏与diff检查证据见build-local/leader/v0.3-s1/evidence/planning-check.log；三份权威和根文档SHA见planning-identity.json。

下一门槛为Builder实现，不提交推送。当前无实质权威冲突、无未解决规划问题；返工从本阶段0/2计数，不能重置历史阶段计数。
