# V0.2/S3：固定真实后端集成与稳定性

## 1. 状态、授权与执行门槛

2026-10-19；状态 `Approved`，阶段待实现/环境准备中；编排Ready for Builder（真实验证须先满足M0）。Leader (Zeus)依据用户“开始s3工作”“没有现成后端，请你选方案”及既有技术决策委托，采纳本方案。协调者确认固定约511MB资产的隔离下载属于必要可逆准备，负责精确权限路线。本设计不授权全局安装、任意模型下载或远端付费。

批准包：[本设计](S3-design.md)、[审查计划](../../../reviewer/reviews/V0.2/S3-review.md)、[Leader001](../../reports/V0.2/S3-report-001.md)。起点S2本地提交 `d933e8892033a600b68ff5ac0db950dec5abea90`，初始干净，分支codex/v0.2-s3-integration；不推断远端。S2经[Reviewer001 PASS](../../../reviewer/reports/V0.2/S2-report-001.md)与[Leader002](../../reports/V0.2/S2-report-002.md)完成，历史0/2保留。本S3独立返工0/2，最多两轮，不覆盖任何旧Approved/报告/manifest。

**M0真实环境门槛**：固定资产大小/SHA、许可证、动态依赖、启动版本、模型加载、直接非流式和SSE探测都成功，才允许把真实集成用例计为已执行。下载/启动失败可继续离线工具与模拟稳定性建设，但真实部分BLOCKED，阶段和V0.2不能收口；不能用模拟结果替代。M0证据后补到角色报告/环境清单，不静默修改本设计指定的资产或验收标准。用户规则完成后协调者自动本地提交、不推送。

## 2. 范围与非目标

在一个固定真实文本推理后端上验证现有HTTP/JSON/SSE子集、直接与代理行为、取消分层证据、持续运行和故障恢复；以可控模拟器补齐真实模型难以制造的长流、高水、错帧及快慢混合压力。默认不修改产品语义；发现契约内缺陷走有限修复与独立复验，真实后端存在差异先记录，不能放宽安全解析或添加厂商字段绕过。

不引入多实例/模型路由、等待队列、重试、下游keepalive、新依赖库、厂商格式转换、TLS/认证服务、GPU性能或计算停止保证。CPU真实模型推理满足本阶段“一种真实后端”协议验证，不替代真实多实例GPU调度证据。没有SSE event语义处理移入网关；测试客户端可解析事件验证后端契约。

交付建议：tests内独立集成host/probe与Python标准库驱动、固定输入、人工运行命令及来源/环境/结果清单；真实模型和后端二进制只在ignored build-local，不加入vendor或普通CTest下载。标准CTest保持离线与无模型依赖，新增快速自测可注册；长时间真实/模拟运行用显式命令，不默默拉长每次普通回归。

## 3. 环境选择和固定资产（REQ-01）

只读已核验Ubuntu24.04.3/WSL，20逻辑CPU，MemTotal约7787MiB、当时可用5615MiB，RTX4060 Laptop 8188MiB显存。无现成ollama/llama-server/vllm/docker或torch/transformers/llama_cpp及常用模型缓存；未发现8000/8080监听。初次NVML/netlink被沙箱阻止，窄升级只读成功，不把权限失败称作无GPU。无nvcc，因此选CPU轻量后端而不安装CUDA/PyTorch。协调者已完成两资产下载与size/SHA核验，后端ldd依赖齐全、--version成功；记录build-local/integration/v0.2-s3/asset-verification.json。尚未启动模型、无后台服务，不能把资产准备等同M0接口通过。

| 资产 | 固定身份 | 大小和校验 |
| --- | --- | --- |
| llama.cpp CPU服务器 | b7481，commit cc0a04343e56f2decdf2a6df977ff9c9edc85ced；MIT | llama-b7481-bin-ubuntu-x64.tar.gz，19144446字节，SHA256 9cbbff430e4f2d976135d68d998576530cc1bd87babe1d71db4886d8a79e7b2e |
| Qwen官方GGUF | Qwen/Qwen2.5-0.5B-Instruct-GGUF，revision 2ed9be962c95f7625f4963ff51ed472e4538187a，qwen2.5-0.5b-instruct-q4_k_m.gguf；Apache-2.0 | 491400032字节，SHA256 74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db |

官方来源：[release metadata](https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b7481)、[固定server说明](https://github.com/ggml-org/llama.cpp/blob/cc0a04343e56f2decdf2a6df977ff9c9edc85ced/tools/server/README.md)、[固定MIT许可](https://github.com/ggml-org/llama.cpp/blob/cc0a04343e56f2decdf2a6df977ff9c9edc85ced/LICENSE)、[模型固定revision与许可](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/2ed9be962c95f7625f4963ff51ed472e4538187a)。选择可核验固定旧版本作为局部测试依赖，不声称最新或建议公网部署。

精确下载URL：

```text
https://github.com/ggml-org/llama.cpp/releases/download/b7481/llama-b7481-bin-ubuntu-x64.tar.gz
https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/2ed9be962c95f7625f4963ff51ed472e4538187a/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

合计510544478字节（约487MiB），准备阶段预留2GiB磁盘空间，实际展开量记录；预估后端RSS不超过2GiB作为启动护栏而非已测事实，超出先停止查明。4 CPU线程、无远端服务费，实耗CPU/内存与时间随运行记录，不保证推理速度。现有8GiB GPU不使用、不报告GPU吞吐。

资产只读共享于 `build-local/integration/v0.2-s3/backend/`、`models/`，下载临时文件校验后原子rename；先检查tar路径无绝对路径/..及逃逸链接，不解压到仓库源码或系统目录。不执行curl|sh、不sudo、不apt/pip，不自动追latest或-hf拉模型。启动前检查动态库依赖；缺依赖或不兼容回报协调者，不默默全局安装。保存许可证原文、metadata、下载大小/SHA、展开后llama-server与依赖库SHA、--version/--help和完整命令。

每角色自有端口、PID/process group、日志和tmp/cache；不能杀死另一角色或用户服务。临时端口显式探测，禁止占用已有监听；仅绑定127.0.0.1。同一时间只跑一个模型服务以控制内存，Builder结束清理后Reviewer启动自己的进程，绝不接管仍活的Builder服务。

冻结启动参数（路径/端口替换为角色实际值，先以固定--help核验）：

```text
llama-server -m <absolute-local-gguf> --host 127.0.0.1 --port <role-port> --alias gateway-qwen --ctx-size 2048 --parallel 1 --threads 4 --threads-batch 4 --n-gpu-layers 0 --metrics
```

健康探测只访问自己服务/health；/slots、/metrics仅测试工具直接观察，不经Gateway、不扩网关路由。启动最长120s；正常退出TERM后最多5s再KILL所属进程组，wait回收。后端的单slot内部等待不等于网关新增队列，常规真实负载限制一个在途请求。

## 4. 协议契约与差异采样（REQ-02）

Gateway只支持HTTP/1.1明文IPv4单上游、POST /v1/chat/completions；请求字段model/messages/stream/n=1/max_tokens1..8192/temperature0..2，message仅system/user/assistant字符串content。模型固定alias gateway-qwen，temperature=0；短请求max_tokens=32，长请求512，固定合成prompt与哈希，无真实个人数据。禁用seed、stream_options、tools、response_format、max_completion_tokens等额外字段，即使后端支持；不要让客户端SDK偷偷增加它们。正文UTF-8 JSON、Content-Type application/json，显式CL，不发送Expect或压缩。

冻结Gateway真实测试配置：连接额度4、总预约64MiB，上游池max_connections4/max_idle1/idle_timeout_ms1000；stream高/低192/64KiB、容量1MiB。timeouts_ms request10000/connect3000/upstream_write5000/response120000/downstream_write10000/total150000/shutdown3000/stream_idle30000。这是预先为CPU推理选的实验配置，不更改产品默认；若超过期限如实失败，不在结果后延长。模拟配置沿S2默认时间（专门故障用例可预先设短期限并单独记录）。

M0先各发1条直接短非流与流，记录原始最终头、HTTP定界、逐段到达时间、解码长度/hash、JSON结构/SSE终止。非流需200与有意义的assistant文本，流需200且唯一合法text/event-stream及允许UTF-8参数；llama.cpp文档提供该端点同步/流式能力，但实际版本头/帧必须实测，不凭文档宣布兼容。

直接与代理各10次非流+10次流（warmup各2次不计），相同输入与配置交错运行。验证状态、类型、合法终态、非空assistant文本；流客户端识别JSON data、finish_reason及一次[DONE]作为**后端协议观察**，网关仍opaque，不能在产品中合成/依赖[DONE]。stream ID/created/timing可能不同，temperature0也不保证跨请求逐字节相同；直接与代理不做全响应字节相等要求。合成压力同一确定字节流才做严格全文相等。响应字段差异记录，不自动视为网关丢字。

非SSE错误：发送合法网关请求但超出2048 context的固定合成messages，直接记录后端4xx，再通过代理确认状态/结构保留且完整终结；输入总量须在网关限制内。若后端行为不同，先报告实测并给对应差异结论，不临时伪造后端错误。额外验证网关拒绝未支持字段400时后端请求数不增加（此项模拟可精确计数）。

长流至少3次max_tokens512，要求每次≥16个非空content增量且第一个content在HTTP结束前被客户端观察，记录头/首body/首content/完成时间；若模型提前EOS不足16则报告长流用例未满足，不靠补造事件通过。选择固定“逐项列出1到200并简要解释”的合成prompt，不检查模型正确数数。真实慢读3次：请求完成后暂停读1s，再每20ms读1024字节，要求HTTP完整和有意义输出；不要求小模型实际触发256KiB高水。高水与数据完整保证由独立合成矩阵验证。

## 5. 取消、故障和恢复（REQ-03）

真实取消5次：长流收到首个非空content后客户端RST，记录取消时刻和后端/网关状态。分层结论：L1网关自己的session/timer/lease/pending/预算归基线；L2网关上游连接结束的证据来自网关FD/租约与后端连接/日志（有则记录，不用客户端RST推断）；L3后端slot从processing到idle且新短请求成功，只说明固定CPU后端任务/slot释放的观察，不等同GPU内核停止。若/slots暴露的信息不足，L3标未证实，不能宣称计算已取消；L1和连接释放是必需通过项，L3仍须如实记录。这不是跳过真实取消测试。

取消后本地资源应在5s内归零活跃基线，backend slot至多10s恢复；若无法取得明确slot状态但新请求10s内成功，记录较弱证据而不冒充slot证明。迟到HTTP完成不得假零chunk/第二头。另3次客户端完整请求SHUT_WR应获得完整真实流，防取消误判。

仅操作本角色创建的模型服务：3轮后端故障，分别请求前关闭、流首content后TERM、流首content后KILL。请求前错误应为网关502/503确定失败；已提交流必须截断、不能伪造正常尾块。受控关闭后先完成本地清理，再用同一固定资产/参数重启、等健康，每轮至少2个非流+2个流请求成功。不得由Gateway自动retry；重启后的请求为测试新请求。正常结束/超时/取消与首信号/第二信号交错由模拟精确覆盖，真实shutdown至少一次有流活动时SIGTERM并确认有限收口。

## 6. 预先固定稳定性契约（REQ-04）

分开两个实验，不把模型速度混入代理资源结论：

| 实验 | 时长、样本、负载 | 通过条件 |
| --- | --- | --- |
| 真实CPU连续运行 | 预热5条后至少600秒；单在途、短请求stream/nonstream严格交替，完成≥60条且各≥30；每条间隔0.1s，最长1800秒总护栏 | 无计划外失败/超时/崩溃；每条按协议完整；每10条等idle池过期后检查资源基线；结束恢复普通请求 |
| 模拟混合稳定性 | 至少300秒且≥300个完成请求；最多4个在途，固定seed=20261019；每10请求4快流、2受控慢流、2非流、1客户端取消、1坏chunk/截断交替；每50请求全排空 | 正常请求全文严格相等/唯一终止；故障分类全部符合预期；高低水位有实际触发；无意外失败；每轮资源回基线、capacity不越界 |

所有样本包括计划失败/取消均保留，报告预期与实际分类，不从分母删除。真实运行不能为了满足60条而在600秒前提前停止；达到600秒但不足60，继续至1800秒，仍不足则未通过本固定工作负载。模拟护栏900秒；机器负载导致未完成则记录Blocked/未通过，不能写通过并缩短时长。操作系统休眠/测试进程被外部中断作为无效run保留，重新执行须新前缀。

资源证据优先在测试专用Runtime host运行同一产品库与真实Socket/真实后端，提供有界只读snapshot给驱动；可另做正式gateway二进制直接/代理冒烟。不得为方便测试新增产品管理API、输出prompt日志或改变事件循环。Snapshot包含S2预约/数组/pending/paused/session/timer/pool值；每50或10条排空后等待≤5s（池idle1000ms到期）回启动基线，后端进程和监听FD分别计数。若使用进程形式无法读快照，必须结合测试host补同负载资源证据，不拿RSS替代唯一账本。

每秒采样Gateway RSS/FD及后端RSS，样本存有界文件，限制日志总量128MiB/role；停止时保存峰值和最后5个排空点。硬验收是受控账本每时刻≤配置、排空点活跃/预约/数组/pending/paused/leased/请求timer=0、FD返回启动基线（listener/signalfd允许常驻）。RSS额外检查：预热排空RSS为B，后续排空RSS不得超过B+32MiB，且最后5个排空点最大值−最小值≤8MiB；不满足需要解释与诊断，不能无条件PASS。该实验阈值只针对固定gateway负载，不宣称通用RSS上限，内核Socket内存另记配置；后端RSS仅启动护栏与诊断，不计入gateway预算。

## 7. 实施、验收与受阻规则

M0协调者准备固定资产并完成环境身份，Builder复核启动直接冒烟；M1实现离线可复用驱动/测试host/固定输入和机器可读run manifest；M2真实协议/取消/故障；M3两类稳定性与三预设回归；M4 Reviewer独立重建/独立进程与数据复验，Leader收口。报告必须关联source SHA、二进制SHA、资产SHA、参数、命令、时间、退出码、样本计数、失败分类、取消层级和限制。来源变化只记新增自有测试/工具，不迁入模型服务源码作为网关依赖。

| AC | 必须交付 | 对应RV |
| --- | --- | --- |
| AC01 | 固定资产、许可、版本/模型/CLI/平台可重现，无隐式下载或全局安装，M0真实冒烟成功 | RV01 |
| AC02 | 直接/代理各20正式样本、长流3、慢读3、非SSE错误差异真实记录；现有子集不被放宽 | RV02 |
| AC03 | 取消5/SHUT_WR3、3轮自有后端故障与恢复、真实有限停止；分层证据不越界 | RV03 |
| AC04 | 真实≥600s且≥60、模拟≥300s且≥300，预定义分类/容量/资源/RSS阈值满足，原始样本完整 | RV04 |
| AC05 | 独立三预设全部CTest及旧S2关键期限/关闭/暂停回归，规范/来源与历史保护通过；正式程序启动/协议也实际验证 | RV05 |

真实环境未满足时可交付工具但阶段保持未完成；不把正常未完成工作记接受债。真正协议兼容冲突、资产变化或验收阈值调整先交Leader新权威，不用报告静默覆盖本设计。通过所有AC且独立PASS后才允许S3/V0.2生命周期关闭；V0.3仍不自动启动。

路线为原生WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`；各角色build-local/<role>/v0.2-s3/{tmp,cache,evidence,debug,release,asan}，脚本前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。下载与socket/loopback/LSan已知边界首次精确窄升级，不禁检查/重复沙箱失败；共享资产只读，各角色构建和进程独立。Leader只规划，不跑产品回归、不派agent、不commit/push。
