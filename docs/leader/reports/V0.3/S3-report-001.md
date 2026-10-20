# V0.3/S3 Leader 规划报告001

2026-10-20，Approved / 待实现，Ready for Builder，累计返工0/2。

## 第一部分：PM 决策摘要

**结论：On Track，可以开始MVP综合验收。** 用户启动S3及既有技术委托已授权本方案，无例行待批准项。当前交付为规划，尚未完成S3或整个MVP。

**计划与实际：** 已冻结真实28次请求和模拟29次请求的有界矩阵，验证流式、路由、排队、取消、过载和故障恢复的组合。已有本地固定模型和服务程序SHA核验一致，复用资产，不下载模型。S2已本地提交d89de57，未核验推送。

**主要取舍：** 两个CPU模型进程各2线程，共享CPU/内存；真实链路验证兼容与实际排队，精确故障/拒绝通过门闩模拟。保留资源与延迟原始记录，但不重跑长性能矩阵、不宣称GPU收益或生产容量。

**风险：** 小模型可能提前完成，真实并发未产生排队时必须报未满足，不以模拟替代。CPU速度受共享资源影响，超出固定期限如实失败。新增依赖、重大偏差、债务和阻塞：None。

**PM决策：None。** Builder实施工具、固定矩阵和三预设回归，Reviewer独立复验；全部通过后Leader收口，再由协调者本地提交、不推送。V0.4及L4LB联调不启动。

## 第二部分：详细工作记录

供PM按需查阅。

依据ROADMAP S3、ARCHITECTURE、S1/S2最新收口和现有配置、AdmissionRuntimeHost/ProxySession/Router配置边界及V0.2/S3集成工具。无项目Leader指南，使用plan-project-docs全局模板；沿Olympus、agent-execution-route及个人C++规则正反例。规划起点codex/v0.3-s3-mvp-acceptance / d89de57eb6be0106bccd24432b2559d342ed8b79，初始clean。无债务清单且无新债，不创建空文件。

[Approved设计](../../designs/V0.3/S3-design.md) SHA256 `b0d9fd9a518436631ecfd189d3bb50488b4edb3c7d6fb7cde24c81520901e49d`；[Approved审查计划](../../../reviewer/reviews/V0.3/S3-review.md) SHA256 `2b3e3ce3d1a030c25b1b08800a942d41107ee0ebf04173b4f3d281ac30ae62f4`。该包是本阶段实施与独立验收依据，历史设计不覆盖。

只读确认llama-server SHA45938e…2d081与历史Reviewer asset-check一致，模型SHA74a4da…7a9db与资产清单一致；不启动真实后端、不运行负载。固定b7481/Qwen0.5B许可证与来源沿旧设计，各执行角色复核全部资产与库。新增双进程布局仅用于本阶段，每实例2线程/GPU0；不迁入外部源码、不扩协议。旧单进程稳定性与P1测量保留各自历史边界。

R0–R3总28attempt，2取消、26成功（含2预热）；M1–M5总29attempt，19成功/2取消/2后端失败/1队列超时/5拒绝。按真实/模拟/预热/正常/计划失败分别统计，TTFT只流首content，E2E只正常HTTP完成，queue_wait只实际入队并派发；不从失败分母删样本。Gate控制模拟时序，实际目标/健康状态证实故障选择，避免依赖线程顺序或未验证RR前提。

工具复用现有只读friend/snapshot和标准库，不增加产品公开接口。资源以同负载账本与排空FD为硬证据，RSS采用预热B+32MiB门槛，后端资源独立；全部输出有上限、run不覆盖、attempt finally留存，独立负控检验遗漏/伪成功/额度残留。实际功能缺陷交协调者统一返工，不能改工具掩盖。

执行路线：原生WSL `/bin/bash` login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway；各角色build-local/<role>/v0.3-s3/{tmp,cache,evidence,debug,release,asan}，Python前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。socket/LSan已知边界首次窄升级，Reviewer独立构建/进程/数据，资产只读共享。Leader规划仅修改本三件包及README/ROADMAP/ARCHITECTURE；保护/链接/diff结果见build-local/leader/v0.3-s3/evidence/planning-check.log，身份见planning-identity.json。

当前阶段0/2，未实现/验收/提交/推送；交Builder，不启动额外模型实验、长soak或P1诊断。独立PASS及Leader关闭全部AC后才能称为路线图定义的独立网关MVP。
