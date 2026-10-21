# V0.4/S2 Builder 返工报告002

2026-10-21，S2累计返工1/2；**本轮控制修正通过，但ASan旧AdmissionE2E失败，已停止；阶段未完成。** 未启动正式21cell run，未重复任何全量CTest，不提交或推送。

## 输入、修改与预期

沿用[原设计](../../../leader/designs/V0.4/S2-design.md)、[审查计划](../../../reviewer/reviews/V0.4/S2-review.md)、[Builder001](S2-report-001.md)，按[Approved返工001](../../../leader/reworks/V0.4/S2-rework-001.md) SHA256 `87a4aa4eb633c7a0710c0c9393a43c015a9f1a85b4aa83c1668c420b808d5eb4`及[Leader002](../../../leader/reports/V0.4/S2-report-002.md) SHA256 `6bf26c71d97d491e59cc4aa572d4a5d87f0759ddf361dd413052312d25f4c72e`执行。执行路线/工具与Builder001相同，无专用Builder指南，继续使用全局模板。预期控制通过后三预设全量与一次冻结实验。

实现源仅修改`tests/queue_budget/DetectorTests.py`：HTTP字段名统一lowercase/trim，小写和混合大小写控制覆盖Content-Length及实验ID；finally在回收后保存有界forensic.json，记录原异常、gate、后端接收/异常、客户端结果、host状态和线程数，取证写失败不覆盖原异常。真实占位/入队/504/drain时间条件未放宽。其余新增Python/三配置与首次失败快照一致，旧源码/测试/S1完全未改；说明、拆解和本结果记录按实际同步。

## 控制结果

`build-local/builder/v0.4-s2/evidence/controls-002`一次退出0，保留controls-001失败原始文件。离线ID/时钟/分母/终态/有效三元组/低负载误杀/5%边界/零基线/工具限制及大小写控制均通过；三份配置实际Host加载、drain成功。

real-timeout/proof.json及forensic.json证明两个实际后端请求已接收且host inflight=2，第三会话有入队事件、无dispatch；持有两个slot期间第三返回504 queue_timeout，实测enqueue→finished 0.101528402秒；后端请求集合只有前两ID。之后释放gate、两请求成功、drain全零，线程0，无后端/清理异常。child-exit和budget-exhausted各闭合8当前+8未来ID，当前失败和未来not_started保留、所有PID回收；budget控制继承Cell最终错误为cell cleanup failure，内部预算错误仍保存在对应cleanup-errors.json，不能误称产品故障。

## 全量回归首次结果与新失败

| 预设 | 构建 | CTest结果 | 时间 | 退出 |
| --- | --- | --- | --- | --- |
| Debug | 成功 | 21/21 | 42.10s | 0 |
| Release | 成功 | 21/21 | 39.13s | 0 |
| ASan+UBSan | 成功 | 20/21 | 60.47s | 8 |

失败为已有AdmissionE2E，用时1.63s，不是120s CTest超时。`tests/admission/RunAdmission.py:241`在shutdown负控finally调用Gateway.close，`:141`断言子进程returncode==0失败，stderr为空。其余20项含新的历史ExperimentDetectors通过；这里21项不包含本阶段新QueueBudgetDetectors。

**现有证据不能确定子进程具体退出码或信号。** 原Gateway.close只把stderr作为断言detail；TemporaryDirectory异常退出后删除，原trace/config也未留存。CTest/LastTest日志没有ASan或UBSan诊断文本。只读源码显示该路径先显式发送SIGTERM，再在finally的close中若poll仍为None再发送SIGTERM；这只是需要验证的候选机制，不能冒称本次实际发生重复信号导致退出。未运行诊断复测或修改受保护旧测试。

原始`ctest-asan.log`、`.exit`及`last-test-asan-001.log`保留；自有Debug/Release相应日志亦归档。ps只读检查未发现S2 host/client/RunAdmission残留。需要Leader批准下一有限诊断权威，明确如何记录实际子进程returncode/signal和保持临时trace，再依证据判断是否需要修改；不能把偶发重测通过等同关闭。

## 可复现命令与身份

原生WSL bash login=false、当前分支`codex/v0.4-s2-evidence-driven-improvement`、HEAD `752987a0564e8a99c0833c7f2af7e65ad561e491`；使用独立tmp/cache/evidence和显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX。loopback/LSan首次窄权限，不关闭检测。

```bash
python3 tests/queue_budget/DetectorTests.py --host build-local/builder/v0.4-s2/release/ExperimentRuntimeHost --output build-local/builder/v0.4-s2/evidence/controls-002
cmake --preset debug -B build-local/builder/v0.4-s2/debug
cmake --build build-local/builder/v0.4-s2/debug -j4
ctest --test-dir build-local/builder/v0.4-s2/debug --output-on-failure
ctest --test-dir build-local/builder/v0.4-s2/release --output-on-failure
cmake --preset asan -B build-local/builder/v0.4-s2/asan
cmake --build build-local/builder/v0.4-s2/asan -j4
ctest --test-dir build-local/builder/v0.4-s2/asan --output-on-failure
```

`handoff-builder002-identity.json`保存源及42个可执行产物SHA、控制PID记录。236个Leader冻结项全部原字节不变；对比failure001源清单唯一变化为新DetectorTests。controls-002总11个Host/backend/worker子进程均start/reaped闭合。原controls-001、Builder001及批准权威不覆盖。

## 未完成与独立审查关注

新ASan失败未解决，正式矩阵及统计结果未执行，候选不可推荐。缺少退出码的原始事实必须保留，不将猜测写成根因。Leader/Reviewer须关注允许范围是否需例外、诊断取证不改变现象、旧测试保障不降低、首次失败留存及新工具全部AC仍待独立验证。阶段没有完成，尚不能提交最终交付。
