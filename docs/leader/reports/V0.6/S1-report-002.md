# V0.6/S1 启动报告002

## 第一部分：PM 决策摘要

2026-10-29，On Track。用户以“开始s1点工作”授权执行已规划的V0.6/S1容量摸底与瓶颈归因。当前进入测量设施实现与校准，尚无新容量结论，也未开始产品优化。执行基线为[S1设计](../../designs/V0.6/S1-design.md)与[审查计划](../../../reviewer/reviews/V0.6/S1-review.md)。

本阶段比较直连后端、单网关、双网关与L4组合，先验证发压/后端能力，再冻结正式测试档位，完成独立复验后给出容量区间或下界及瓶颈证据。工具或环境限制将如实标记，不据此宣称网关性能上限。

PM必需决策：None。Builder负责工具与采集，Leader负责正式清单冻结及证据收口，Reviewer独立审查与复验；压力采集串行运行。完成验证后按用户现行要求提交并推送。S2/S3仍待S1证据，不在本次修改产品。

## 第二部分：详细工作记录

起点b9a12d46e13ff937947e72c5e7ddb173a22e3be9，启动时工作区干净，执行分支`codex/v0.6-s1-capacity-baseline`。规划报告001保留为历史记录。本报告记录启动，不构成阶段验收。

采用plan-project-docs角色流程及agent-execution-route原生WSL路径；Builder/Reviewer分别拥有`build-local/<role>/v0.6-s1`的构建、临时目录、缓存和证据。Gateway与L4实际源码指纹、构建产物及环境由各角色独立取证；L4仓库有既有用户改动，只读使用，不修改或提交。

实施采用Python标准库异步客户端/模拟后端、开环调度、逐请求有界记录、累计资源/证据账本及完整L4日志轮转。先完成E0和负控，再在批准预算内E1探索；E2控制实验根据探索证据选择，E3正式清单由Leader冻结后才能采集。Reviewer可以并行阅读和构建，不与Builder并行压测。

环境初查：Linux WSL2，20逻辑CPU，已有strace/taskset，无perf命令。不安装依赖或修改全局系统参数；工具不可用时记录取证边界。产品源码、旧工具、CMake和既有性能历史均保护。

同步README/ROADMAP/ARCHITECTURE、版本计划和S1设计的当前实施状态及报告入口；仅作状态性编辑，不改变既定范围、架构或验收要求。

指标语义澄清：核对旧tests/l4lb_cost/Analyze.py，e2e_ms对应http_ns，close_ms单列。S1继续以完整HTTP framing及正文校验完成的观测时刻作为端到端终点，起点为scheduled；EOF/close单列，排空仍是独立硬要求。该澄清不改SLO阈值或引入关闭成功前即忽略协议异常的捷径。

E1采集中发现完全空响应EOF被初版解帧器归为protocol_error。Leader批准仅对rx=0且wire/body/http均为空的情况归transport_failure；部分HTTP响应截断仍为protocol_error。保留原始逐ID记录及原结果，用版本化离线复审记录具体分类变化，不能覆盖首次结果；正式选档采用一致分类后的派生结果。此修正不删除失败、不改变goodput分母或SLO，避免将入口关闭误称收到损坏HTTP。

E1执行26个cell后，S/G在480、960连续未过筛选而停；观察到默认stream_buffer总额4MiB、每流256KiB形成约16流的配置约束。保持探索基线，正式G显式同值、M/L按聚合4MiB均分，不让实例数量隐式增加流缓冲预算。先批准四个E2：A/G1920与3840双发压、A/B3840双发压（总槽数仍128），S/G480仅将流缓冲总额4MiB改8MiB。其余控制与正式档位待这组证据决定；该额度控制不视作产品代码优化。

正式冻结：校准与控制累计44cell（27E1、7E2、10diagnostic）后，Leader对manifest执行validate、verify_sources及全矩阵最坏预算复算通过，Frozen SHA256为81877a406c767b66fb90422a79b805f53c3c77a13869219b4f967ee5116358f4。A双发压960/1920/3840，S单发压240/480/600；72cell，正式1,929,600请求，含预热2,219,040请求。工具源码哈希一并冻结，Builder获准串行正式采集，Reviewer等待后独立复验。最坏证据预算约2.085GB（十进制），低于2GiB；请求排空5秒与随后FD确认2秒区分，均在45秒cell活动硬限内。

冻结后文字勘误（不改清单SHA或测量）：http时间戳在完整HTTP framing解析后取得；success还要求随后EOF及正文校验通过，后续校验CPU不计入http时延。manifest中“HTTP framing and body validation observed complete”短句及上文“及正文校验完成”不精确，正确含义为framing完成时刻加最终校验成功条件。REQ05与工具均使用HTTP framing完成作为计时边界，阈值、原始记录、分类和测量实现未变。

正式首停与恢复：第7项F-A-L-1920-r0触发L4日志审计失败，按[返工001](../../reworks/V0.6/S1-rework-001.md)修复多词reason解析。原始数据/首错/failed ledger和v1清单保留，独立全量复算7/7、负控11/11后，冻结v2 SHA256 292cbafde4460b1af038e909cf82b2d4c6d804022494dc3c9d5286705b698f0e并授权续采余65个新ID。所有速率、配置、顺序和SLO保持，不重新发压前7项。恢复时预算预估1,978,955,422B、116cell、活动保守预留3472.381秒，均在既定上限内。

第二次首停与恢复：第18项F-S-M-480-r0在请求窗口结束后的资源采样报PermissionError。两角色依据最后完整样本与100ms等待源码证明错误晚于formal_end至少83.714568ms、晚于最后client close至少46.517916ms，具体PID/根因未知。按[返工002](../../reworks/V0.6/S1-rework-002.md)补确认退出边界与有界错误取证；18/18独立审计、15/15负控和全部原始指纹通过后冻结v3 SHA256 66b57cde541599fcc8e2666b618d7f5910913a7b9c025a6319cac5db4d026198，授权余54项。原第7/18 failed状态及原result保持，v1/v2清单均保留。恢复预检曾发现S/B两进程与旧>=3门槛不匹配，已按冻结拓扑改为完整名称/数量/PID唯一性校验；未发压或产生新cell。r3恢复预算1,780,090,836B、116cell、活动含保守预留3270.198秒；若再遇未知采集错则受限交付，不继续扩大恢复框架。

第三次首停与新增安全方案：第33项F-A-L-3840-r1在request-drain读取generator-0的/proc/PID/fd报PermissionError，当时poll无退出码，随后退出0。runner按规则停在33/72；事件明确晚于formal_end16.364018ms及最后client close9.708117ms。Reviewer独立33/33审计通过，并提出仅窗口外无信号wait≤100ms、实际退出才跳过的安全确认方案；窗口内、控制器和仍活进程错误仍fatal。Leader因此批准[返工003](../../reworks/V0.6/S1-rework-003.md)，在剩余预算内完成必要测量器修复，而不因未知状态直接继续或降低标准。第三点85.2461%达标与采样收口错误分别保留，未执行39点保持计划状态；具体内核根因不作推断。

返工003恢复：独立33/33原始/派生审计、17/17最终负控及版本链/源码/二进制/时序核对通过；Leader冻结v4 SHA256 a559456acd9851c51a14b877fcfb42bdfe829c144bd4c61efdf71ebc245fe692，授权余39项新ID续采。恢复时最坏证据预算1,562,024,116B、总116cell，活动含cell预留3000.595秒（另预检45秒仍充足）。前三次失败原始结果与各版本清单保持，正常测量参数和33项原始性能结果不变。

独立复验首停与返工004：Reviewer已完成Release21/21及33/33原始审计，但第33项cleanup阶段L4的/proc/PID/stat消失、即时poll无退出码，v4仅PermissionError等待，故FileNotFoundError分支正确停止。精确事件晚于formal_end43.195092ms及lastclose37.035458ms，6进程最终exit0。经独立安全判断，批准[返工004](../../reworks/V0.6/S1-rework-004.md)将三类退出读取异常统一为仅窗口外真实退出确认，不忽略存活/窗口内错误；为Reviewer唯一v4前缀33项增加严格恢复，余39正式及反序2诊断不变，Builder原72项不重发。

返工004独立恢复：三类退出读取异常统一窗口外确认，Builder与Reviewer最终19/19负控通过；Reviewer自有33项r5派生逐字段保持原metrics。Leader冻结v5 SHA256 f059fc20bf38d0c7f333440d925f1ff70316cd19beac7769b5fdc9bc49018e9a，独立最终readiness全部通过后按条件授权续39项及反序2诊断。预算最坏1,541,593,046B、完成83cell、活动含41cell保守预留与45s预检2811.140秒，仍在上限内。v4原始清单及Reviewer唯一failed保留，不重发原33项。
