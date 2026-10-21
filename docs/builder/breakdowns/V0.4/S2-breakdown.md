# V0.4/S2 Builder 实施拆解

2026-10-21，依据[Approved设计](../../../leader/designs/V0.4/S2-design.md)、[审查计划](../../../reviewer/reviews/V0.4/S2-review.md)、[返工001](../../../leader/reworks/V0.4/S2-rework-001.md)与[返工002](../../../leader/reworks/V0.4/S2-rework-002.md)，S2返工2/2。

| 里程碑 | 范围及依赖 | 验证 | 当前状态 |
| --- | --- | --- | --- |
| M1 | 新增tests/queue_budget；复用S1原机制，局部Cell配置覆盖；Z/B/C完整JSON、审计、负控、说明 | 计划21cell/2970ID、真实配置加载、占位100ms超时、统计反例及失败ID/PID闭合 | 返工001修正控制头名及取证后，controls-002一次通过；controls-001失败保留 |
| M2 | 自有三预设构建/回归；M1通过后一次完整冻结实验，结果和实现报告 | 各21项完整CTest、逐ID与资源/预算/配对审计、历史hash | 返工002 A取证后经Leader004批准B；机制/同ASan定向/修后三套21/21通过；唯一正式run001完成21cell/2970ID、自审PASS；发压限制触发、不推荐替换基线，Builder004交接 |
| M3/M4 | 独立Reviewer、Leader收口、协调者提交 | 独立结果；文档一致；本地提交不推送 | 非Builder职责，待交接 |

原生WSL `/home/power/projects/AI-Inference-L7-Gateway`，bash login=false，分支`codex/v0.4-s2-evidence-driven-improvement`，HEAD `752987a0564e8a99c0833c7f2af7e65ad561e491`。无项目Builder指南，回退plan-project-docs Builder模板。使用agent-execution-route约定的`build-local/builder/v0.4-s2/{tmp,cache,evidence,debug,release,asan}`与显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX。loopback与LSan已知边界首次窄权限；不下载依赖/模型。

保护src、既有tests/CMake/S1权威与报告，使用Leader `planning-protected.json`逐项核对。尚不声明完成或候选获益；首次实际失败保留、报告后等待返工授权，不自行重测修补。
