# V0.4/S2 Builder 实现交接报告004

2026-10-21，**Builder自测完成，待独立Reviewer验收**。累计返工2/2；无新增轮次，无额外实验，未提交或推送。

## 目标、权威与实际交付

依据[设计](../../../leader/designs/V0.4/S2-design.md)、[审查计划](../../../reviewer/reviews/V0.4/S2-review.md)、[返工001](../../../leader/reworks/V0.4/S2-rework-001.md)、[返工002](../../../leader/reworks/V0.4/S2-rework-002.md)及[Leader004同轮B确认](../../../leader/reports/V0.4/S2-report-004.md)（SHA256 `97ac1d5ba935c38c676d737121371bbea814480e9c8df5d2a441e3dcfb6ede89`）。Builder001–003为冻结失败/诊断历史，全部保留。共享执行路线、Builder模板回退及前述技能仍适用；未修改C++。

交付三份完整Z/B/C配置、冻结21cell/2970ID计划、局部Cell配置子类runner、逐ID/队列/配对审计、新控制与操作说明，以及[完整结果](../../../performance/V0.4/S2-results.md)。S1框架全部通过import复用，无全局猴补丁、无第二套客户端/预算/采样器，无产品算法或默认改变。唯一旧文件例外为下述测试停止所有权修正。

本轮预期与实际均为：A唯一诊断→停止回报→Leader004准许B→确定性控制→同ASan目标一次→三套完整回归各一次→原唯一正式矩阵。实现范围未扩大，仍保留全部REQ/AC，Builder自审PASS不代替Reviewer独立接受。

## 两轮返工与保护例外

第1轮修正新增DetectorTests自建控制后端大小写敏感字段查找，并补finally有界取证；controls-001失败保留，controls-002一次通过。首次线程异常字符串未落盘，不能回溯声称捕获KeyError。

第2轮A使用同ASan二进制和独立证据副本，唯一诊断实测case3显式SIGTERM后finally再次SIGTERM，communicate returncode−15；trace显示queue gateway_stopping未派发、六项资源零。原首次ASan失败未记录returncode/signal，仍未知；没有把诊断回填为原始事实。A报告003及原日志冻结，Leader004才准许B。

B仅修改`tests/admission/RunAdmission.py`：Gateway新增stop_requested，显式shutdown与finally统一request_stop入口；已成功请求停止则清理不重复发送。communicate仍等待5s，超时仍kill，returncode仍严格0，sanitizer与六项资源零断言、503 gateway_stopping场景不变。错误信息增加实际returncode/stop状态/最多4096字符stderr。没有接受−15、sleep、跳过或改变产品信号语义。

`admission-repaired-001/StopOwnershipChecks.py`确定性验证重复request_stop+close只发送一次，并分别拒绝−15和1；机制验证退出0。同一ASan host定向原AdmissionE2E一次通过42checks。新工具配置/源及42个自有binary与controls-002时精确不变，故按批准身份**复用**controls-002，没有再次运行新控制或声称修后重跑。235项其他冻结文件原字节不变；唯一例外的当前SHA为`cc04f6141a569287fc5bfc58d33ea965119e18f8a687a076f685359783c02e24`。

## 修后验证

| 验证 | 实际结果 |
| --- | --- |
| 确定性停止所有权/非零退出控制 | 通过，一次停止、−15/1仍拒绝 |
| 同ASan AdmissionE2E定向一次 | 42checks，exit0 |
| Debug完整CTest | 21/21，43.07s，exit0 |
| Release完整CTest | 21/21，39.22s，exit0 |
| ASan+UBSan完整CTest | 21/21，61.09s，exit0 |
| 正式run-001 | 一次21/21，2970ID，279.169204s，exit0，自审PASS |
| 最终原始资源/身份检查 | FinalAudit.py退出0；101PID回收、235保护项不变、42binary不变 |

三套21项不包含新QueueBudgetDetectors；它单独记录controls-002。修前Debug/Release通过、ASan20/21以及诊断失败全部保留，不拼接成修后通过。无额外重测。

正式2760ID为2282success+323queue_full+155queue_timeout；预热210为198+9+3。所有2970唯一ID闭合，无not_sent/not_started或协议/传输/deadline错误。每个超时验证host入队、未dispatch、后端无请求，终态无重复或取消异常。两rate有效三元组各3/3，低负载5req/s B/C全部成功，实际无拒绝/超时；完整长短类计划数/终态/SLO数/全窗口goodput和等待分布见结果文档及每cell queue-audit.json。

60req/s候选−基线goodput差+21/+23/+20req/s，数值门槛满足；T吞吐1272.096022/1719.435837/1141.136120 req/s，机器漂移false但发压敏感true、CPU≥0.85 true。**不推荐替换基线**，只报告受限描述性观察，无因果/容量/真实推理收益声明；产品默认1000ms不变。

179直接文件预留93847552bytes，managed累计7849557、emergency34872bytes，符合原分区预算；101PID全部回收。gateway峰reserved184549376/capacity524288/pending2506，inflight2、perbackend≤1、queue_count8、queue_bytes12416。所有drain资源0、FD回基线；最大RSS4554752bytes、相对预热增长163840bytes。实际gateway/process采样最大间隔0.120140262/1.007174053s，不将100ms/1s称硬实时。

## 复现与身份

路线：WSL bash login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`，分支`codex/v0.4-s2-evidence-driven-improvement`，HEAD `752987a0564e8a99c0833c7f2af7e65ad561e491`。环境TMPDIR/TMP/TEMP指向`build-local/builder/v0.4-s2/tmp`，XDG_CACHE_HOME指向cache，PYTHONPYCACHEPREFIX指向cache/pycache。已知loopback/LSan首次窄权限，不禁检查/下载/调系统。

```bash
python3 build-local/builder/v0.4-s2/evidence/admission-repaired-001/StopOwnershipChecks.py
python3 tests/admission/RunAdmission.py /home/power/projects/AI-Inference-L7-Gateway/build-local/builder/v0.4-s2/asan/AdmissionRuntimeHost
ctest --test-dir build-local/builder/v0.4-s2/debug --output-on-failure
ctest --test-dir build-local/builder/v0.4-s2/release --output-on-failure
ctest --test-dir build-local/builder/v0.4-s2/asan --output-on-failure
python3 tests/queue_budget/RunQueueBudget.py --host /home/power/projects/AI-Inference-L7-Gateway/build-local/builder/v0.4-s2/release/ExperimentRuntimeHost --output build-local/builder/v0.4-s2/evidence/run-001
python3 build-local/builder/v0.4-s2/evidence/FinalAudit.py
```

证据根`build-local/builder/v0.4-s2/evidence/`：admission-diagnostic-001保留A、admission-repaired-001保留B差异/机制/目标日志，ctest-*-repaired.log及last-test-*-repaired.log保留完整回归；run-001/含计划/清单/逐ID/时钟/后端/预算/资源/进程/分析，run-001-raw-sha256.json为逐文件身份；pre-matrix-identity.json与final-audit004.json记录源/binary/保护证明，最终handoff-builder004-identity.json汇总交接身份。所有输出目录不覆盖，旧记录保留。

## 未完成、限制及Reviewer关注

Builder范围完成，尚待Reviewer自有三套构建、独立控制及唯一21cell矩阵/自写复算，随后Leader收口和协调者本地提交不推送。重点核查A/B证据与条件例外、非零退出仍拒绝、controls复用身份、完整计划分母及类分组、超时不派发、配对数值与T限制。零/负实验可接受，工具限制不能删除，当前数据不构成一般配置推荐。无待Builder继续修改的已知缺陷；累计2/2后新阻塞必须停止，不启动第三轮。
