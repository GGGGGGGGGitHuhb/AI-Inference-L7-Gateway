# V0.2/S3 Builder 初版报告001

2026-10-19；Builder (Hephaestus)。初次实现，累计返工 **0/2**。全部结果是Builder自测，等待独立Reviewer；未提交、未推送、未启动后续版本。

## 权威、路线与范围

依据Approved `docs/leader/designs/V0.2/S3-design.md`（af975691b5540600e9f8c894b0964346ba6ad3b77c30bc420eedaea74475ae5a）、`docs/reviewer/reviews/V0.2/S3-review.md`（1315d12f060048cd5706e59a552a3658e4e6d2e45e8145d7369ca06bc2b7b0b5）与Leader001。读取S2最终Builder001/Reviewer001、当前配置/Runtime/closing/预算API和根文档。无项目Builder指南，按plan-project-docs全局Builder与stage-design模板回退；已读agent-execution-route及personal-cpp-standards完整规范和正反例。

原生WSL、/bin/bash login=false，仓库/home/power/projects/AI-Inference-L7-Gateway，分支codex/v0.2-s3-integration，HEAD d933e8892033a600b68ff5ac0db950dec5abea90。角色目录build-local/builder/v0.2-s3/{tmp,cache,evidence,debug,release,asan}；下文E指evidence。所有Python/构建/测试设TMPDIR/TMP/TEMP/XDG_CACHE_HOME；Socket/loopback/LSan首次精确升级。没有下载/安装/全局配置；资产由协调者先准备并仅只读使用。无派生代理。

产品src、第三方、旧测试和历史报告/manifest不变。本阶段只新增tests/integration工具/固定输入/说明、CMake测试目标与Builder文档。Leader的根状态修改保留。测试host链接同一gateway_runtime，复用既有snapshot/pollOnce及测试friend读取停止状态，100ms输出快照，不增加产品外部管理接口、不修改Socket参数。正式gateway另行真实冒烟及活动流SIGTERM验证。

## 交付文件和行为

- `tests/integration/RuntimeHost.cpp`：同负载Runtime快照，真实事件循环/Socket/上游模型；退出时最后快照。
- `Support.py`：固定资产身份/CLI、专属进程组生命周期、配置/协议采样、同进程FD/RSS、资源排空和容量阈值。
- `WireResponse.py`：有界HTTP/1.1原始头与增量chunk/CL/EOF读取；严格终态后EOF，拒绝第二零块或尾随字节；测试客户端解析SSE，产品保持opaque。
- `RealRun.py`：M0后真实direct/proxy、长流/慢读/取消/故障恢复/正式入口及600秒实验。
- `SyntheticRun.py`：固定seed/配比、最多4个在途、每50排空及300秒实验；完成客户端须等新的Runtime快照确认会话退休才补位，closing仍占准入不是队列。worker内持锁落盘每次结果，避免其他任务失败时丢失并发完成样本。
- `DetectorTests.py`：9种负控每个子进程实际非零；普通CTest快速执行，无模型、无下载。
- `Inputs.json`、`README.md`：固定合成输入与可重现命令；长期运行显式调用，校准独立标识。

当前逐文件SHA见[变化记录](../../../references/V0.2-S3-changes.md)，拆解见[breakdown](../../breakdowns/V0.2/S3-breakdown.md)。没有把模型/服务源码迁入vendor。

## AC01：固定真实环境

llama.cpp b7481/cc0a04343e56f2decdf2a6df977ff9c9edc85ced，tar19144446字节/SHA9cbbff430e4f2d976135d68d998576530cc1bd87babe1d71db4886d8a79e7b2e；Qwen2.5-0.5B-Instruct-GGUF固定revision2ed9be962c95f7625f4963ff51ed472e4538187a，GGUF491400032字节/SHA74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db。工具将批准size/hash硬编码核对机器清单，再核验实际文件；不只相信清单自报。

共享资产build-local/integration/v0.2-s3。E/model-LICENSE.txt为协调者获取的固定revision Apache2原文，11343字节/SHA832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e；E/llama-LICENSE.txt为MIT原文。来源URL及本机CPU/内存/内核/Python/socket默认参数见E/environment.json；服务/动态库SHA见real-final-001/assets.json，--version/--help/ldd分别backend-{version,help,ldd}.log。

M0模型实际加载，直接短非流与SSE皆200（m0-direct.json/m0-backend.log/m0-exit.json），非流application/json;charset=utf-8+CL，流唯一text/event-stream+chunked。初次M0只证明启动与结构；正式raw头/逐段时间/SSE终态由后续run补齐。CPU4threads/threads-batch4、ctx2048、parallel1、ngl0、alias gateway-qwen、metrics和loopback端口由processes.jsonl逐次保存。启动RSS没有超过2GiB护栏。所有模型按顺序运行，未同时启两个模型。

## AC02/03：真实协议、取消与恢复

正式原始证据E/real-final-001/protocol-samples.jsonl、cancellation.jsonl、backend-faults.jsonl及各backend日志；E/protocol-summary.json为索引，不替代原样本。

warmup每种direct/proxy和流/非流各2次不计。正式direct20、proxy20，各自10非流+10流交错，状态/类型/非空assistant文本/唯一finish_reason和[DONE]全部满足。3条max_tokens512长流各观察512个非空content增量，首content早于HTTP结束；3次1秒后再每20ms读1024字节慢读和3次完整请求SHUT_WR均正常。模型ID/created/timings及潜在文本差异不用于跨推理字节相等断言。长短输入均固定合成文本。

合法超context输入实际4830 tokens>2048，direct/proxy均400；195字节JSON error结构与正文完全一致，未伪造错误/添加后端专有字段/修改网关解析。Header大小写/Connection/Via规范化属于现有行为。模拟另证unsupported seed字段400且后端计数不增。

5次首content后RST：L1同负载session/timer/lease/pending/预约/数组/paused全归0、FD7回基线，观测清理约0.151–0.156s。L2本地upstream/leased/pool=0、FD回基线，并有后端cancel task/slot release日志。L3每次/slots都先is_processing=true、后false，随后新短请求在取消后约0.51–0.53s成功；这是固定CPU后端slot释放证据，不声称GPU内核停止。

3轮自有后端故障分别请求前TERM、首content后TERM、首content后KILL；前者明确502/503错误，后两者已提交200截断、没有DONE/成功零块。每轮先本地排空，再用相同资产/参数/端口重启，各2非流+2流恢复。正式gateway另正常流/非流200，并在活动长流首content后SIGTERM：3秒期限有限截断，进程exit0，无假终态。S2首/第二信号、期限竞争继续由三套原Backpressure/Runtime覆盖。

## AC04：固定持续运行

| 实验 | 正式结果 | 资源与原始证据 |
| --- | --- | --- |
| 真实CPU | 1240请求，620流/620非流；样本首开始至末完成602.829s，含最后排空/恢复收尾的summary604.480s；0意外失败 | real-final-001/{real-soak.jsonl,real-soak-summary.json,resources.jsonl,drains.jsonl,host-snapshots.jsonl}，exit0 |
| 模拟混合 | 650请求，260快流+130慢流+130非流+65取消+33坏chunk+32截断；样本跨度310.091s、summary310.314s；520预期正常/130预期取消或错误，0意外失败 | synthetic-final-002/{synthetic-soak.jsonl,summary.json,resources.jsonl,drains.jsonl,retirement-gates.jsonl}，exit0 |

真实预热排空B=4,321,280字节；末5点跨度0，采样Gateway峰值同为4,321,280，模型峰值624,398,336字节。真实每10条共124次soak排空，加协议/预热等共134点，全部FD7/账本0。模拟B=4,349,952字节；末5点跨度327,680字节，全部后续排空低于B+32MiB；Gateway每秒采样峰值5,390,336字节。模拟13次soak排空加预热共14点，全部FD7/账本0。模拟累计3173次pause/resume，峰值预约67,108,864、数组1,048,576、pending818,460字节，最终全部活跃账本0。峰值包含本进程预热，原始记录可分段核算。

模型与模拟是分开的host、原始样本和资源文件，部分墙钟时段重叠，没有用模拟替代真实请求，也不从CPU速度推出代理性能。每秒Gateway/模型RSS和FD分开采样；100ms账本快照与累计容量峰值共同检查边界，不宣称采样覆盖每个瞬时状态。每个排空点等待≤5秒，包含上游idle到期，全部活跃账本0/FD7。真实小模型未触发高水，这不冒充压力证据；实际高水由确定字节模拟实验验证。

## AC05：回归、负控、格式

三套各自cmake --preset mode -B build-local/builder/v0.2-s3/mode、cmake --build目录-j4、ctest --test-dir目录--output-on-failure：Debug **13/13 26.05s**、Release **13/13 23.11s**、ASan+UBSan **13/13 39.63s**，exit0。E/{mode}-configure-final.log、{mode}-build-final.log、{mode}-test-initial.log、{mode}-LastTest-initial.log；initial为第一次完整CTest的保留命名，不是少跑或旧阶段复用。产品/原12入口保持，新增IntegrationDetectors离线快速入口。无sanitizer诊断。

原S1 DeadlineMatrix/TotalDeadlineMatrix使用S2已有constructor-only预算owner适配副本，原件与patch一并复制，当前Debug库重新编译，**18/18+18/18**；原CloseWindow.py SHA158de752e714596bbdacf5e0e5c351d098d74239faf95d3b7f4d63ec8b58b425在当前Release gateway运行原120/150ms **20/20**。对应E/*-build.log、DeadlineMatrix.log、TotalDeadlineMatrix.log、CloseWindow.log。没有重跑旧18cell成本矩阵。

9项工具负控：缺资产/坏hash、端口冲突、进程启动失败、坏HTTP、CL少字节、读取超时、容量越界、RSS超限；每个子进程都实际非零，顶层汇总exit0，检测器自身资源清理路径经过执行。原始trace见detectors-initial.log/detectors-final.log及三套LastTest。它们不是生产故障，不从正式样本分母删除。

唯一新增C++ RuntimeHost.cpp实际clang-format-18 -i后--dry-run --Werror，format-version.log/format-check.log；git diff --check通过。人工逐函数核对writeSnapshot/runHost/main及friend方法的函数空行、职责、生命周期；没有回调业务lambda/嵌套lambda，也没有新增产品状态字段。Python人工复核异常/信号finally、私有PID组、帧边界、样本保存、资源判据和时间护栏。模型取消解释没有超出观察层级。

## 初次失败与身份差异

1. real-calibration-001/002在首轮故障重启前bind端口遇TIME_WAIT，exit1。模型早已wait回收，无活监听；单纯SO_REUSEADDR不足以复用该旧连接状态。最终只在后续重启遇无活listener时最多等65秒，包含120秒总启动护栏；不改上游端口/实验配置，初次占用仍立即拒绝。calibration003完整87协议/恢复样本通过且全进程回收，才启动正式真实run。
2. synthetic-final-001约88秒第208号快流未见头就RST，exit1。快速补位在客户端HTTP完成与网关closing退休之间可超实际准入额度。原100ms快照不能锁定瞬时拒绝点，报告不把推断当精确事件证明；独立ClosingAdmission-002明确复现4个已完成HTTP但未FIN客户端仍占4session/4timer/64MiB、零上游/流容量，第5RST；客户端关闭后全归零。诊断首轮误要求reason phrase为OK，而产品原本Gateway Response，单独保留closing-admission.log失败，次轮按状态码检查通过。
3. 仅修模拟驱动补位：每次完成后等新的snapshot确认实际session≤仍在途客户端数，再补到最多4。配置、seed、配比、正文、300秒与300计数门槛不变，不提高max_connections，不接受正常失败。另将结果落盘移入worker并持锁，使故障时尚在途完成样本也保存。旧失败run的协调循环在首断言抛出后没有保存所有晚到future结果，该run明确无效/失败，不计验收；已经存在的全部样本/失败与快照保留。新run002完整独立重做。

真实正式run开始后只改变未被RealRun导入的SyntheticRun.py，共用Support/WireResponse/RealRun和所有产品/host二进制完全不变。E/SyntheticRun-before-retirement.py逐字节hash匹配真实manifest旧身份，synthetic-retirement.patch与real-run-source-delta.json为唯一差异证据；正式模拟002记录最终身份。三套CTest不执行SyntheticRun（长run独立），此改动由完整新模拟run覆盖，未无谓重跑原功能回归。

## 审计、限制与交接

E/source-final-sha256.json共64项、binaries-final-sha256.json共33项，最终逐项核对当前文件一致；批准设计/审查hash保持。E/protected-audit.json核对100项已跟踪产品/第三方/历史文档与HEAD逐字节相同。最终E/final-audit.json核对两个正式run样本数量、唯一index、全部快照容量上界、每个资源排空、终态和所有保存processes记录：自有进程全部reaped且当前无存活，已计划KILL退出-9单列，其余正常退出0。M0另有m0-exit.json明确wait回收。总证据约57.46MiB，低于128MiB；原始样本和初次失败没有覆盖。E/command-exits.json汇总命令实际退出码。

没有扩大硬件/许可/协议范围、没有真实兼容阻塞，已完成本次全部AC自测。真实run的604.480s summary包括最后恢复请求/排空，因此另用原始样本602.829s跨度证明600秒门槛，不拿收尾时间补足。模拟同理样本跨度已超过300秒。

请Reviewer重点检查：原始HTTP终态检测器及负控真的非零、真实/模拟与校准/正式分离、同负载排空/RSS判据、closing退休补位约束、取消分层，以及真实run仅未加载模拟文件的身份差异。无已知产品缺陷或契约未完成项；独立验收与Leader收口尚未执行。完成后按用户规则由协调者本地提交，Builder不代提交/推送。
