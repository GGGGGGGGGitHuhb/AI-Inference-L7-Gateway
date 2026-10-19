# V0.2/S3 Builder 受限纠正报告003

2026-10-19；Builder (Hephaestus)。第2轮、累计 **2/2**，最后允许一轮。唯一目标是Reviewer001的Major **V02-S3-F-001：异常attempt未形成原始样本**。本轮自测完成，等待独立复验；不自行开启第三轮，不代Reviewer判断接受，不提交推送。

## 权威与边界

读取Reviewer001全文，尤其第2节根因/要求与第7节最小复验范围。报告SHA6e2530c1ec09b4fd93e269ed30c5ed44bc8894100f017657abffc93c7063e313；原Approved设计af975691…和审查1315d12f…不变。001/002是历史快照，本003补充，不覆盖。无项目Builder指南，继续使用plan-project-docs全局Builder模板；执行路线沿agent-execution-route。

原生WSL、/bin/bash login=false，cwd /home/power/projects/AI-Inference-L7-Gateway，branch codex/v0.2-s3-integration、HEAD d933e8892033a600b68ff5ac0db950dec5abea90。显式TMPDIR/TMP/TEMP与XDG_CACHE_HOME仍在build-local/builder/v0.2-s3/{tmp,cache}，本轮证据均evidence/r2前缀。已知Socket/loopback首次精确升级，无安装/下载/派生代理；共享模型/许可只读，自有模型始终最多一个。

## 实际修复

1. Support.exchange把请求编码及create_connection纳入原try/finally，socket从None开始；连接拒绝/超时也形成起止、请求身份、0字节hash和错误后继续原异常传播。HTTP/SSE/JSON/结构/回调/BaseException错误携带同一个partial结果，已有网络/HTTP错误仍保持原失败结果返回语义。
2. finally保留已收正文长度/hash、已知状态/原始头；即使content最终join抛TypeError也记录并在嵌套finally关闭socket。KeyboardInterrupt/实际SIGTERM保留interrupted标志与原异常，不改为正常完成。
3. 新recorded_exchange是唯一逐attempt落盘出口，提供进程内唯一attempt_id及既有label/index。exchange或既有成功校验抛错时，在finally只append一次，再传播。RealRun协议与soak均使用；SyntheticRun worker持原SAMPLE_LOCK独立记录，即使协调循环因首个future失败退出，其他实际开始的worker仍落盘。模拟预热和unsupported-field探测也走此出口。
4. 原validate_real/validate_sample判据保持；把已有检查纳入记录作用域，使完整HTTP但无效JSON等校验失败也有error字段。complete仍表示HTTP完成，不把error非空视为成功，计划取消/坏帧的既有分类不改。追加attempt_id/error_type/interrupted仅为证据字段。

精确修改为Support.py、RealRun.py、SyntheticRun.py、CMakeLists.txt，新增AttemptTests.py。产品src、RuntimeHost.cpp、WireResponse.py、Inputs.json、模型CLI、配置/超时/水位、正常send/recv与原始解帧、时钟采样位置、慢读节奏、seed/配比/4并发退休门、资源采样和RSS门槛均不改。CMake只新增短IntegrationAttempts测试入口；没有C++变更，未重格式化或重建产品。Python人工检查异常传播、finally、锁与恰一次落盘，py_compile通过，git diff --check通过。

## 本轮实际执行

E=build-local/builder/v0.2-s3/evidence。原Reviewer探针复制为E/r2-*.py，仅将输出根与二进制路径改为Builder独立目录，Reviewer原失败文件不动。

| 检查 | 本轮实际结果 |
| --- | --- |
| 原SampleLossProbe | 3个异常各1条，LOST_FAILURE_SAMPLES 0 OF 3，exit0 |
| 原LateFailureProbe | 4个future实际异常、4条唯一记录，exit0 |
| 原FailureCleanupProbe | 注入run失败，子进程exit1、FAIL结果保存、2个自有进程reaped且PID不存在；外层exit0 |
| 原WireProbe | 原8项解帧/尾随对照通过，exit0，WireResponse本身未修改 |
| 新AttemptTests | 13类异常每类恰好1条，明确异常类型、起止/partial bytes/hash、socket关闭，子进程全部非零；首失败后4个晚到future全部记录；顶层exit0 |
| 旧9项负控和新增负控快速CTest | IntegrationDetectors与IntegrationAttempts **2/2，2.48s，exit0** |
| 短真实完整校准 | **CALIBRATION_PASS，87条协议样本，exit0**，含direct/proxy、长/慢、5取消/3SHUT_WR、3轮故障重启、正式入口活动停止；没有跑soak |
| 短模拟校准 | **CALIBRATION_PASS，50请求，24.154s，exit0**；40正常/5取消/5故障，资源回基线；不是300秒验收 |

13类为连接拒绝、连接超时注入、坏HTTP状态转换、坏CL转换、非法SSE、JSON解析、JSON结构、content TypeError、回调RuntimeError、KeyboardInterrupt、实际SIGTERM、读取超时、完整非流HTTP的JSON校验失败。每类负控都校验具体error_type，避免用别的失败冒充覆盖；持久原始记录/child stderr/退出码在E/r2-attempt-records，晚到记录late.jsonl。旧反例原始输出在r2-{SampleLossProbe,LateFailureProbe,FailureCleanupProbe,WireProbe}.log和r2-probes/。

初版新fixture曾在发送完整CL后等待客户端关闭而未先SHUT_WR，导致最终JSON验证案例先读超时；该次顶层负控虽然非零检测通过，却不足以证明预期JSON异常。保留r2-attempt-tests.log，修正仅fixture的SHUT_WR，并加入逐例具体异常类型断言；r2-attempt-tests-final.log及增加实际SIGTERM后的r2-attempt-tests-complete.log通过。没有改工具/产品超时来绕过该问题。最终持久记录完整覆盖13类。

命令：`python3 E/r2-<探针>.py`；`python3 tests/integration/AttemptTests.py`；`cmake --preset release -B build-local/builder/v0.2-s3/release`后`ctest --test-dir build-local/builder/v0.2-s3/release -R '^Integration(Detectors|Attempts)$' --output-on-failure`；`python3 -m py_compile tests/integration/*.py`。短校准使用原RealRun.py/SyntheticRun.py命令、原Release host/gateway与固定资产，加`--calibration`并分别输出E/r2-real-calibration、E/r2-synthetic-calibration。配置/CLI/源身份与逐样本由各manifest记录。详细CTest为r2-fast-ctest.log/r2-fast-LastTest.log，原日志不覆盖。

## 明确复用的旧结果

严格按Reviewer001第7节条件复用其原身份结果：真实原始样本跨度 **601.662秒/1270请求**、模拟 **310.192秒/650请求**、独立三套 **13/13**、原截止 **18+18**、关闭 **20/20**及该轮完整协议/取消/故障证据。原64项源manifest SHA72eee933535c0f66a19279d4b33d936c0a7b9e31200a0797fd3dcadc6a330d34，原36项Reviewer binary manifest SHAbecb5a2bd132d5590ba9bdbdc97e3a4e621267b471ac152f0da5a2e934c80992，记录E/r2-reused-evidence.json。

本轮没有运行600/300秒长run、三套全量产品CTest或原18+18/20。当前新增注册后CTest共有14个入口，仅实际跑2个快速入口；不能说本轮14/14或新源码全量长期验证。复用理由是唯一差异为异常携带/记录/传播和必要采样包装及负控：未改变成功协议、正常IO、负载或资源判据。成功校验的既有谓词进入唯一记录作用域，不放宽条件；本轮正常短校准验证未重复落盘或改变分类。若独立复验认为超出上述条件，由协调者处理，Builder不自行扩大第三轮。

## 身份、保护与交接

E/r2-source-sha256.json **65项**：原64项中4修改、60不变，另1新增；r2-before-*和r2-diff-*.patch逐文件与旧hash核对，r2-source-delta.json给出映射。E/r2-binaries-sha256.json **36项**均与原Builder产物逐项一致（每模式9 executable+3 static libraries，3模式）。src、host、WireResponse、输入均有旧新相等证据。原source-final/binaries-final清单保留，不改写历史。

本轮更新breakdown累计2/2和当前来源表；001/002/Reviewer001/Approved字节保护见r2-authority-protection.json。最终校准样本唯一ID/计数/资源以及进程清理核对见r2-final-audit.json；所有自有模型/host/gateway及清理对照进程已wait回收，无后台遗留。剩余仅独立Reviewer复验及Leader/协调者后续门槛，本轮到此停止。
