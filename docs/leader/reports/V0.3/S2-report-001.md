# V0.3/S2 Leader 规划报告001

2026-10-20，Leader (Zeus)。Approved / 待实现，Ready for Builder，累计返工0/2。

## 第一部分：PM 决策摘要

**结论与健康状态：On Track，可以开始S2实现。** 用户“已推送，进行s2的工作吧”及既有技术委托授权路线图内的准入与有界排队，无需重复例行审批。

**计划与实际：** 已冻结全局/每实例请求限额、每模型FIFO与count/byte上限、排队取消/超时及跨模型轮转方案。功能尚未实现；S1已本地提交b704df2，推送为用户报告、本轮未独立核验远端。

**主要选择：** 新增显式admission配置，仅用于models模式；不启用时保持旧行为。排队继续使用原Session内存预约，不持上游连接或请求额度；出队重新检查健康和容量，总期限从接收时起不重置。无健康实例或选定传输池满明确拒绝，无自动重试。采用回调结束后的有界调度避免释放时重入。

**取舍与风险：** 同模型FIFO可能让短请求等长请求，跨模型轮转只提供有限调度规则，不保证长期无饥饿；排队保留Session预约，实际容量也受原内存/连接限制。SHUT_WR保持等待，TCP有序关闭不能总被识别为取消，最终以deadline收口。计划通过固定24条长短混合及独立边界测试记录这些现象，不扩大为性能项目。重大新增依赖、债务、成本或阻塞：None。

**PM决策：None。** 建议依此最小方案实施。Builder完成三预设回归和有界混合记录，Reviewer独立验收，Leader收口后协调者本地提交、不推送；S3/V0.4与P1约44ms诊断不启动。

## 第二部分：详细工作记录

供PM按需查阅。

### 权威与当前身份

[Approved设计](../../designs/V0.3/S2-design.md) SHA256 `002b00cdb5501d1e86326e02160dc9eaf785e4b11ed56fd116174a8c3078ded3`；[审查计划](../../../reviewer/reviews/V0.3/S2-review.md) SHA256 `a3adaec952fcf85c4942827af108354784f3c063a3476ad3c5afd51e4b60f8c7`。批准依据当前明确启动和既有技术委托；无例行待批准项，无新rework。起点b704df268e2865bda146ba4c816dd105e6c8302c，codex/v0.3-s2-admission-queue，规划前clean。S1[最终Leader002](S1-report-002.md)/[Reviewer002](../../../reviewer/reports/V0.3/S1-report-002.md)及其1/2历史保持。

沿agent-execution-route、plan-project-docs Leader模板回退及个人C++规则正反例。无项目专用Leader指南，已读取用户跨项目规则；未发现需要接受的新债项，不创建空清单。原生WSL /bin/bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway；角色build-local/leader/v0.3-s2/{tmp,cache,evidence}，脚本前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME；下游各自独立构建与证据，socket/LSan首次精确升级。

### 源码依据与决策理由

实际读取ModelRouter/RequestLease、GatewayConfig、Runtime onCleanup、Session读取/选择/终结/deadline和BufferBudget。S1已有唯一请求inflight与epoch，不增加第二套可漂移容量账；global求最多64实例计数和。现有Session16MiB预约与一个timer足以承载有界等待；新增Controller仅管理稳定Session ID/FIFO/逻辑字节和轮转，不拥有Socket/正文或队列专属上游lease。

请求入队前完成原协议校验但不绑定Host，队列逻辑charge固定字段字节加1024，与实际内存预约区分；出队才生成选定上游请求。采用显式opt-in避免改变已有S1/legacy测试和部署。容量候选过滤先于Router选择，排队不借Trial资格/推进游标；global和perbackend在单EventLoop同步检查并取得RequestLease，终结沿S1恰一次释放。

队列是容量等待，不是故障重试：现有项遇全无健康立即503，因而无需健康冷却唤醒timer。容量释放/取消/超时/健康结果标dirty，cleanup点调度最多32头，必要时单合并task续轮；阻塞不忙轮。入队或等待者超时已有Session timer负责唤醒，精确deadline在派发前再核；stop先排空等待者错误路径，活动上游沿原有限排空。

### 验收、文档与交接

六组AC/RV覆盖配置、容量/选择、队列账、时钟健康、事件停止、有限混合与证据。debug/release/asan完整CTest加新增Admission/AdmissionE2E，固定Release24条混合每角色一次；独立补充队头取消、deadline与释放同刻、请求额度释放但池仍满、超过32续轮与停止等序列。实际记录等待和FIFO而不依赖线程启动编号，不重跑完整P1/旧soak/真实模型。

本轮新增设计/审查/本报告，更新根README/ROADMAP/ARCHITECTURE当前S2规划与S1提交事实，不写已实现或修改CHANGELOG历史接受。保护快照177项和链接/围栏/diff检查见build-local/leader/v0.3-s2/evidence/planning-check.log，文件SHA见planning-identity.json；未改源码、旧权威/报告/测试/第三方。暂无实质权威冲突或未解决规划问题。

交Builder实施，无提交推送；当前0/2，只在实现证据和独立PASS后收口。V0.3整体/MVP仍待S3。
