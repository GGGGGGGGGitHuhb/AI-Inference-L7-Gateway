# V0.2/S3 Leader 规划报告001

2026-10-19；Leader (Zeus)。基线Approved，阶段待实现/真实启动待验证，Ready for Builder（M0先行），返工0/2。

## 第一部分：PM 决策摘要

**结论与健康状态：On Track，可以进入真实集成实施。** 用户已授权启动S3并由我们选择后端；固定资产已准备，但模型加载/接口尚未验证，不能宣告阶段完成。

**计划与实际：** 选择本机CPU llama-server b7481与Qwen2.5-0.5B-Instruct小模型，约511MB下载已由协调者核验，不需要全局安装/CUDA或远端付费。已交付协议、取消、故障恢复和持续运行的固定验收基线；真实运行与独立审查待完成。

**已验证成果：** 当前S2本地提交d933e8892033a600b68ff5ac0db950dec5abea90、初始工作区干净。只读确认本机约8GiB内存、20逻辑CPU和8GiB RTX4060；无现成推理栈。官方资产版本/体积/SHA与许可证已核对；协调者完成下载、解压、动态依赖及--version检查，没有模型后台服务。

**重要取舍与风险：** 用真实CPU小模型验证接口与生命周期，避免为协议测试部署GPU栈。计划真实连续运行至少10分钟/60请求，模拟混合至少5分钟/300请求；实际资源/失败原样记录，不做性能收益承诺。模型若无法启动或协议不匹配，真实部分保持未完成，模拟不能替代。重大未解决范围/成本冲突或接受债务：None。

**PM决策：None。** 选型与隔离准备在当前授权范围，协调者已处理必要资产下载；本方案不涉及额外付费或全局安装。需要变更资产、产品兼容范围或验收阈值时另报具体影响，不要求PM逐项读技术矩阵。

**下一步：** Builder先完成M0模型加载及直接接口探测，再实现可复用测试工具、真实集成与持续运行；Reviewer独立进程/构建/数据复验。全部AC通过后Leader关闭S3/V0.2，协调者按既有授权本地提交、不推送；V0.3不自动启动。

## 第二部分：详细工作记录

本部分供PM按需查阅。

### 权威与环境身份

[设计](../../designs/V0.2/S3-design.md) SHA256 `af975691b5540600e9f8c894b0964346ba6ad3b77c30bc420eedaea74475ae5a`；[审查计划](../../../reviewer/reviews/V0.2/S3-review.md) SHA256 `1315d12f060048cd5706e59a552a3658e4e6d2e45e8145d7369ca06bc2b7b0b5`。Leader依据用户“开始s3工作”“没有现成后端，请你选方案”及既有技术委托批准；尚无本阶段实现或验收结果。

读取根路线/架构/当前状态、S2最终Builder001/Reviewer001/Leader002接受链，复核TextRequest/HttpParser/SessionIo及现有配置。S2已本地提交d933e8892033a600b68ff5ac0db950dec5abea90，远端未核验。新分支codex/v0.2-s3-integration初始clean，S3新0/2，历史计数/权威保持；没有已接受债或需建立的空台账。

应用agent-execution-route、personal-cpp-standards完整规范正反例、plan-project-docs/Olympus；无项目Leader指南，继续回退全局Leader模板及其PM/两层报告契约。路线原生WSL、/bin/bash login=false、cwd /home/power/projects/AI-Inference-L7-Gateway。Leader的tmp/cache/evidence在build-local/leader/v0.2-s3，脚本前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。

本轮只读硬件/常见模型缓存目录/监听及库存在性，没有扫描个人文档/读取凭据。首次NVML和ss因沙箱权限失败，保留为环境边界，精确require_escalated查询后成功；GPU为RTX4060 Laptop 8188MiB、当时空闲7212MiB，驱动592.82；主存7787MiB、当时可用5615MiB。常见缓存路径未发现，Python torch/transformers/vllm/llama_cpp不存在，无nvcc；已具备cmake/ninja/c++/curl。没有8000/8080监听，不探测其他现有服务内容。

### 选型理由与可保证边界

选llama.cpp固定b7481的CPU预构建tar，减少依赖和环境变化；Qwen官方0.5B Instruct Q4_K_M兼顾小体积与真实ChatML文本推理。固定版本不是最新版本承诺，只用于loopback受控实验。llama.cpp MIT与模型Apache2.0由官方固定身份核验，许可证随资产保存；不将资产/模型加入仓库vendor。

一手依据为[官方release metadata](https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b7481)、[固定server说明](https://github.com/ggml-org/llama.cpp/blob/cc0a04343e56f2decdf2a6df977ff9c9edc85ced/tools/server/README.md)、[官方模型固定revision](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/2ed9be962c95f7625f4963ff51ed472e4538187a)。本地只读副本E/llama-release-b7481.json、model-metadata.json、llama-server-README.md、llama-LICENSE.txt（E=build-local/leader/v0.2-s3/evidence）。选型不是从第三方帖子推断。

协调者资产证据 `build-local/integration/v0.2-s3/asset-verification.json` 固定两文件：tar19144446字节/SHA9cbbff430e4f2d976135d68d998576530cc1bd87babe1d71db4886d8a79e7b2e；模型491400032字节/SHA74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db。协调者报告安全展开至backend/llama-b7481、ldd完整、--version7481成功；Leader读取资产清单，未重复下载/启动或冒称模型接口已通。

当前网关严格JSON字段不含seed/stream_options/tools，只有文本messages与固定stream等子集；真实客户端用原始标准库HTTP避免SDK增加字段。响应SSE参数/重复头、CL/chunked/EOF及非SSE回退仍严格；实际头必须M0采样。直接/代理不能因模型输出ID/created不同就判丢字，也不能靠最终全文就证明增量。模型侧[DONE]/finish_reason仅测试客户端观察，产品继续opaque。CPU模型取消按本地资源/上游连接/后端slot三层报告，不声称GPU任务停止。

### 实施与验收交接

设计五组AC与RV对应：固定资产与真实启动、协议/长流/慢读差异、取消/故障恢复、两种稳定性实验、独立回归/规范保护。真实600s且至少60、模拟300s且至少300，均有最大运行护栏；失败样本不删，配置先冻结。真实CPU实验按单并发/单slot，不称为网关多实例调度实验。

资源以同负载测试Runtime host的唯一快照与FD为主，RSS每秒单列；预热后排空RSS≤B+32MiB及末5点跨度≤8MiB为本次固定负载诊断门槛，不能等同通用RSS保障。正式gateway进程仍须真实接口冒烟，不以test host代替产品入口。模拟混合场景做严格全文相等和高水门控，真实小模型慢读不强求触发高水，避免把不可控生成速度包装为压力证据。

共享资产只读、各角色自有服务/PID/端口/日志，顺序启模型避免内存争用；普通CTest不下载/不要求模型，长运行单独显式执行。M0缺环境可继续工具/模拟但S3不完成；不接受以模拟替代真实集成的完成债务。若实际4xx或长流不符合预期，报告差异并由Leader处理，不事后调阈值或放宽协议。

本轮仅新增三个S3权威/报告及更新README/ROADMAP/ARCHITECTURE阶段入口；CHANGELOG不加入未实现能力。S2提交事实纠正当前根描述，旧报告保留快照。planning-protected.json保护所有原非根状态文件，planning-doc-check.log记录保护/链接/围栏/空白及当前基线检查，planning-identity.log列输出SHA。未修改产品/测试、未跑产品回归、未派agent、未commit/push。待协调者核对后交Builder实施。
