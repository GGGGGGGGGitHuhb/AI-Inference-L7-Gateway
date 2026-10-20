# V0.2/S3 独立集成验收计划

2026-10-19；`Approved`；Leader (Zeus)依据用户启动S3、委托选择后端及既有技术授权采纳。[设计](../../../leader/designs/V0.2/S3-design.md)规定行为，本文件只规定验证；批准包见[Leader001](../../../leader/reports/V0.2/S3-report-001.md)。阶段待实现/真实启动待验证，返工0/2。

## 1. 身份和独立性

起点d933e8892033a600b68ff5ac0db950dec5abea90，分支codex/v0.2-s3-integration，S2已本地提交，远端不推断。读取S3设计、Builder最新报告/工具/来源/环境清单和S2最终接受链；核验实际代码/二进制/输入/模型/服务SHA，不用Builder数字代替结果。适用agent-execution-route、personal-cpp-standards完整正反例、plan-project-docs；项目无Reviewer指南则回退全局模板。

使用原生WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`。Reviewer独立build-local/reviewer/v0.2-s3/{tmp,cache,evidence,debug,release,asan}，显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。固定资产可只读共享，但端口、PID、运行目录、构建、日志与结果必须独立；Builder全部停服后Reviewer才启自己的模型服务。禁止连接Builder可变后台进程作为独立证据。已知socket/LSan边界首次精确窄升级；不联网安装/自动换模型/禁检测。

## 2. AC/RV矩阵

| RV / AC | 独立验证 | 建议证据 |
| --- | --- | --- |
| RV01 / AC01 | 核对固定2个资产size/SHA、llama版本/库、模型revision/许可、命令/CPU配置；启动≤120s、直接各1短流/非流M0成功，正式gateway程序亦冒烟；无外部费用/全局安装/后台遗留 | environment.json、asset-check.log、server-version.log、direct-preflight.json |
| RV02 / AC02 | 原始请求只允许现有字段。warmup排除后direct/proxy各10非流+10流交错；HTTP原始头/定界、JSON/SSE、非SSE错误直接/代理差异；长流3至少16content增量且首片早于完成；慢读3完整；不比较不稳定ID/timing或强求跨推理逐字节相同 | protocol-samples.jsonl、compatibility.md、long-slow.jsonl |
| RV03 / AC03 | 真模型首content后RST5、SHUT_WR3、真实有流SIGTERM；自己的后端3轮请求前关/流中TERM/流中KILL，重启后各2非流+2流恢复；核对L1/L2/L3分层和计时、无retry/假零chunk/二次头 | cancellation.jsonl、backend-faults.jsonl、shutdown.log |
| RV04 / AC04 | 独立执行真实≥600s≥60且各模式≥30（护栏1800s），模拟≥300s≥300（护栏900s），严格按固定负载/seed和配置；每轮账本/FD基线、RSS阈值/样本完整，无意外失败 | real-soak.jsonl、synthetic-soak.jsonl、resource-samples.csv、soak-summary.json |
| RV05 / AC05 | 独立三预设完整CTest，S2关键水位/分配/期限/关闭回归、规范/来源/权限与历史保护；核查新工具检测器真的会对失败返回非零、模型缺失不能skip为PASS | {debug,release,asan}-{configure,build,test}.log、probe-regression.log、tool-negative.log、source-sha256.json |

## 3. 必须审查的协议和观察边界

后端是固定CPU llama-server+Qwen权重实际推理，不能仅模型文件存在或/health 200就算真实集成。保存模型加载日志、版本及至少真实输出结构；不得将合成模拟器的响应冠名真实模型。M0支持的最终响应Content-Type/CL/TE/Connection及错误格式要实测；客户端不自动解压/重试/添加未支持字段，不使curl行为掩盖错误帧。

直接/代理请求内容与参数相同，但生成ID/created/timing或实际文字未必相同。核查结构/状态/终结，不用去字段后“相等”冒充完整字节透明证明；透明完整性来自同一确定模拟字节流的严格对比。测试客户端可验证SSE data/finish_reason/[DONE]，产品不可新增event拼接或模型完成判断。长流真实首content必须在终态前有时间顺序证据；最终完整文本不够。

后端context超限4xx应以现有网关合法大messages输入触发，不添加厂商专有参数。若后端自动截断或另有行为，必须记录直接/代理一致性与限制，交Leader判断是否需要调整测试权威，不能编造4xx结果。发现重复头/压缩等不兼容不得降低HTTP验证强度通过。

取消L1检查实际网关资源，L2依网关租约/FD与后端连接证据，L3依据后端slot/日志和新请求恢复，不从RST或GPU利用率推断计算已停止。真实模型CPU执行不能产生GPU取消/调度结论。无法明确L3时标未知并给出已证实层级；L1/连接释放及真实取消操作仍必须通过。

## 4. 稳定性与检测器验收

Reviewer复核run manifest包含预先固定的时长、数量、并发、seed、timeout、buffer和连接模式，且执行没有缩短或事后扩大期限。真实实验单slot/单在途是协议稳定性，不能作吞吐或多实例容量比较；模拟4并发才控制快慢混合。分别报告期望成功/期望失败/意外失败数量，所有尝试留存，避免幸存者偏差。

snapshot必须来自本次运行的同一产品库及真实Socket，不能以另一低压fixture证明主运行资源；正常正式二进制冒烟仍必需。每个资源排空点等至多5s并计入idle到期，活跃/预约/流数组/pending/paused/leased/请求timer归0，FD归启动listener/signalfd基线。RSS每秒采样，按设计B+32MiB和末5排空点跨度≤8MiB检查，超阈值如实FAIL/诊断，不把allocator常驻直接判成泄漏或直接豁免。后端RSS与网关分别统计，不能把模型驻留算网关泄漏。

至少对新驱动运行快速负面对照：缺模型/坏资产hash、端口冲突、后端启动失败、坏HTTP/少字节、超时、资源计数非零或RSS阈值超出中的可控情况；确认返回非零及清理子进程。无需真实模型为每个检查器错误重复600s，允许短检测器自测，但不能拿其结果替代正式soak。所有后台服务在try/finally或RAII清理，信号/异常/测试失败也回收自己的进程组；不得按进程名pkill用户服务。

## 5. 回归、权限和接受结论

每mode分别运行cmake --preset对应构建到Reviewer自有目录、cmake --build、ctest --output-on-failure，保存单步退出码和日志；实际CTest数量按本轮记录，不预填。长时间run显式单独调用，普通构建/CTest不能下载或要求模型。新增C++实际格式化与clang-format-18 dry-run、命名/短回调/成员分组/函数空行人工检查；Python工具检查资源与计时边界，不能只看最终汇总PASS。

S2原Backpressure和Runtime矩阵由三套回归；原S1 response/total18+18与CloseWindow20脚本在当前Reviewer库/程序上复跑，保持探针时序与断言，构造如需窄适配另存patch。无产品改动也须跑本阶段要求回归；若确实相同身份复用其他诊断，要明示原身份与执行日期，不能冒充新执行。

PASS需全部AC独立证据满足且无未解决发现；真实模型环境或长期run不可用则BLOCKED/未完成，不能只凭模拟PASS收口。只有明确授权接受延期才PASS WITH DEBT，本基线不允许把真实后端跳过作为完成S3/V0.2的债务。产品/工具/规范缺陷按严重度FAIL；只有未接受Minor也不能PASS。初次及返工日志独立保存，最多2轮。Reviewer不改产品/Approved、不提交推送、不代Leader关闭阶段。
