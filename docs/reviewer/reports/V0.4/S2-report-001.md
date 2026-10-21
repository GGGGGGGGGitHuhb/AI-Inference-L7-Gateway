# V0.4/S2 独立审查报告001

2026-10-21，**PASS**。累计返工3/3；无剩余发现或待接受债务。Reviewer停止实现/测量活动，交Leader文档收口与协调者本地提交、不推送；未启动V0.5。

## 范围、权威与独立性

依据[Approved设计](../../../leader/designs/V0.4/S2-design.md)、[Approved审查计划](../../reviews/V0.4/S2-review.md)、[返工001](../../../leader/reworks/V0.4/S2-rework-001.md)、[返工002](../../../leader/reworks/V0.4/S2-rework-002.md)、[Leader004条件B确认](../../../leader/reports/V0.4/S2-report-004.md)、[返工003](../../../leader/reworks/V0.4/S2-rework-003.md)、[Leader005](../../../leader/reports/V0.4/S2-report-005.md)与[Builder004](../../../builder/reports/V0.4/S2-report-004.md)。已读取早期失败/诊断记录、S1结果及当前README/ROADMAP/ARCHITECTURE。用户AGENTS与agent-execution-route适用；无项目Reviewer指南，回退plan-project-docs Reviewer模板；C++语义查看遵循personal-cpp-standards及示例。保护历史权威与失败证据，不覆盖早期报告。

检查tests/queue_budget全部四Python工具、三配置、README；精确检查RunAdmission.py例外diff，核对GatewayConfig默认1000ms、ProxySession Waiting期限和SignalSource析构源码。独立源码/构建/控制/矩阵及自写复算位于`build-local/reviewer/v0.4-s2/`，没有调用Builder统计函数复算数据、没有复用Builder样本。自写RawAudit.py只用标准库。

路线为原生WSL bash login=false、cwd `/home/power/projects/AI-Inference-L7-Gateway`，分支`codex/v0.4-s2-evidence-driven-improvement`，HEAD `752987a0564e8a99c0833c7f2af7e65ad561e491`。TMPDIR/TMP/TEMP=自有tmp，XDG_CACHE_HOME=cache，PYTHONPYCACHEPREFIX=cache/pycache；socket/LSan首次使用窄权限，未禁sanitizer、下载模型或变更系统。各角色串行发压，全部输出新目录。

## 实际命令与回归

以下E为`build-local/reviewer/v0.4-s2/evidence`，P为debug/release/asan，命令均在显式环境下执行：

```bash
cmake --preset "$P" -B "build-local/reviewer/v0.4-s2/$P"
cmake --build "build-local/reviewer/v0.4-s2/$P" -j4
ctest --test-dir "build-local/reviewer/v0.4-s2/$P" --output-on-failure
python3 tests/queue_budget/DetectorTests.py --host "$PWD/build-local/reviewer/v0.4-s2/release/ExperimentRuntimeHost" --output "$E/controls-001"
python3 "$E/SuperviseRun002.py"
# supervisor内部启动的实际runner命令：
python3 tests/queue_budget/RunQueueBudget.py --host "$PWD/build-local/reviewer/v0.4-s2/release/ExperimentRuntimeHost" --output "$PWD/$E/run-002"
python3 "$E/IndependentControls.py"
python3 "$E/ControlAudit.py"
python3 "$E/RawAudit.py"
python3 "$E/Identity.py"
```

三套各独立配置/构建一次，完整CTest各一次：Debug21/21、43.61s；Release21/21、39.80s；ASan+UBSan21/21、64.06s，全部exit0。保留configure/build/ctest/last-test日志；新QueueBudgetDetectors单独一次PASS，不能计入21项。本轮按返工003核对精确身份后复用此前已过三套/控制证据，未重跑上述测试；没有额外S1矩阵或择优样本。

## 返工关闭与负控

返工001：HTTP字段小写/混合大小写控制与真实代理路径通过；finally取证有界保存后端错误、线程、客户端/host状态且原异常不吞。Builder首次controls-001没有捕获线程KeyError原文，保留其未知边界。独立真实控制实际两个后台连接占用inflight2，第三请求可见入队；保持占位至504 queue_timeout，等待101.673933ms、无dispatch和该ID后台请求；释放后账本全零。forensic无异常、无线程残留。

返工002：独立核读A的diagnostic.diff/events/trace。case3在73344221880845ns由显式路径发SIGTERM，close又在73344224490388ns向同PID24621发SIGTERM，communicate于73344226743962ns返回−15；资源六零、queued gateway_stopping未派发。诊断仅观察而不改原控制决策，但有仪表开销；SignalSource恢复oldMask解释退出期窗口，精确内核时点未测。首次ASan失败没有returncode，仍不能追溯定为−15。Leader004允许B后，精确例外仅统一request_stop幂等所有权，保留5s communicate/超时kill/严格returncode0/sanitizer/六零/503断言；产品完全不改。

独立IndependentControls用确定性进程替身验证两次request_stop再close只发一次SIGTERM，−15及1仍抛断言，0正常接受。实际AdmissionE2E在三套全量均通过。独立SLO/分母反例证明以send起点会误计成功、删除拒绝分母会将2.5虚增为5；另验证5%边界、零基线绝对不降和“配对比率中位”与“中位数比率”不同。新DetectorTests同时覆盖漏/重ID、超时伪成功、错误派发、缺入队、提前超时、有效三元组不足、低负载误杀、工具限制。子进程退出和预算耗尽真实负控各保留16唯一ID（含未来not_started），分别回收4/3个子进程；ControlAudit独立核验，故障未被记为成功样本。

## 第三轮执行边界与历史保留

原独立run001完成14/21后外层session62465返回143，result/exit缺失，两个遗留后端已核对路径回收。Python具体信号及发送者仍未知；原await正确，不能宣称900s耗尽、工具默认超时或未await是根因。保留Stop001、原14cell及只读诊断，不用于本次比较。

用户新增一次批准后，返工003允许证据目录中有限supervisor：自身subreaper、runner独立session、收到的信号/精确returncode持久化、960s外层及10s清理、事件64KiB/console1MiB独立上限；原runner900s/cell60s/client16s/1GiB分区均不变。连续await persistent session84086直到完成。新run002从头完整执行一次，无拼接。

实测supervisor总278.907137s，runner278.780588s、returncode0；未收到外部信号，未进入超时/异常清理，无收养残留，剩余子进程0。supervisor自身CPU0.098449s，console1251bytes，完整事件文件866bytes、小于64KiB；它只转存少量控制台/生命周期事件，仍属于已记录的测量开销。正常路径没有生成请求或额外采样。未实际触发的外层中止/强杀分支不冒称经过故障注入验证；本轮未授权额外运行。run002通过不回填原143根因。全部旧测试身份和原失败历史保留。

## 独立矩阵、分母和资源

唯一run-002完成21/21、2970ID，278.780588s、exit0。正式2760={'success': 2290, 'http_rejection': 320, 'http_timeout': 150}；预热210={'success': 198, 'http_rejection': 9, 'http_timeout': 3}。没有not_sent/not_started、传输/协议/deadline/interrupted。Q按120/rate完整窗口、scheduled起TTFT≤250ms及E2E≤500ms；HTTP成功不等于SLO成功，拒绝/超时不缩分母。短长类分别完整记账、使用同总窗口。分位nearest-rank，p50≥20/p95≥100/p99≥1000，不合并重复。

逐ID自写复算核验冻结顺序/分类/时钟/请求及正文hash；连接按每cell、唯一target和源port两侧独立排序/非重叠关联；全部host终态恰一次，后台集合仅成功ID，超时均入队未派发且等待不提前。实测runtime配置去端口后与静态完整JSON和manifest一致。排队派发/超时按host时刻独立复算等待分位，与queue-audit吻合；所有原始点保留。

| cell | success / full / timeout | SLO数 | goodput req/s | 完成吞吐 req/s | arrival limited |
| --- | --- | --- | --- | --- | --- |
| 00-T-0-0-D | 200 / 0 / 0 | 200 | 1275.412 | 1275.412 | False |
| 01-T-1-0-D | 200 / 0 / 0 | 200 | 1990.847 | 1990.847 | False |
| 02-Q-0-5-Z | 120 / 0 / 0 | 120 | 5.000 | 5.025 | False |
| 03-Q-0-5-B | 120 / 0 / 0 | 120 | 5.000 | 5.024 | False |
| 04-Q-0-5-C | 120 / 0 / 0 | 120 | 5.000 | 5.024 | False |
| 05-Q-0-60-Z | 60 / 60 / 0 | 56 | 28.000 | 28.287 | False |
| 06-Q-0-60-B | 74 / 46 / 0 | 30 | 15.000 | 32.042 | False |
| 07-Q-0-60-C | 69 / 0 / 51 | 66 | 33.000 | 29.475 | False |
| 08-Q-1-5-C | 120 / 0 / 0 | 120 | 5.000 | 5.025 | False |
| 09-Q-1-5-B | 120 / 0 / 0 | 120 | 5.000 | 5.024 | False |
| 10-Q-1-5-Z | 120 / 0 / 0 | 120 | 5.000 | 5.024 | False |
| 11-Q-1-60-C | 72 / 0 / 48 | 69 | 34.500 | 33.693 | False |
| 12-Q-1-60-B | 74 / 46 / 0 | 26 | 13.000 | 31.804 | False |
| 13-Q-1-60-Z | 60 / 60 / 0 | 56 | 28.000 | 28.299 | False |
| 14-Q-2-5-B | 120 / 0 / 0 | 120 | 5.000 | 5.024 | False |
| 15-Q-2-5-Z | 120 / 0 / 0 | 120 | 5.000 | 5.024 | False |
| 16-Q-2-5-C | 120 / 0 / 0 | 120 | 5.000 | 5.024 | False |
| 17-Q-2-60-B | 72 / 48 / 0 | 28 | 14.000 | 29.638 | False |
| 18-Q-2-60-Z | 60 / 60 / 0 | 56 | 28.000 | 28.301 | False |
| 19-Q-2-60-C | 69 / 0 / 51 | 67 | 33.500 | 32.181 | False |
| 20-T-2-0-D | 200 / 0 / 0 | 200 | 1202.916 | 1202.916 | False |

5/60req/s有效三元组各3/3；5req/s B/C各重复120/120成功，无拒绝/超时，符合本次低负载控制。全部短长类、等待分布见raw-audit.json各cell，机器可读完整原点不省略。

| rate | repeat | B goodput | C goodput | C−B | 配对相对变化 |
| --- | --- | --- | --- | --- | --- |
| 5 | 0 | 5.000 | 5.000 | +0.000 | +0.000% |
| 5 | 1 | 5.000 | 5.000 | +0.000 | +0.000% |
| 5 | 2 | 5.000 | 5.000 | +0.000 | +0.000% |
| 60 | 0 | 15.000 | 33.000 | +18.000 | +120.000% |
| 60 | 1 | 13.000 | 34.500 | +21.500 | +165.385% |
| 60 | 2 | 14.000 | 33.500 | +19.500 | +139.286% |

数值门槛满足=True；独立T吞吐[1275.4123519732511, 1990.8469814603868, 1202.9158150072817]req/s，控制flags={'machine_drift': False, 'generator_sensitive': True, 'client_cpu_at_least_085': True}。**不推荐替换基线**：工具限制仍触发，正向观察不能解释为因果、网关容量、通用调优或真实推理收益。与Builder观察方向一致并不消除该限制。100ms非最优值，500ms只是实验基线，产品默认1000ms保持。

预算direct/managed/emergency={'direct': 93847552, 'managed': 7847973, 'emergency': 34903}bytes；direct共179文件×512KiB预留，符合512/448/64MiB分区及1GiB总界。101PID全部start/reaped闭合。drain资源全零且FD回各自基线；最大排空RSS4542464bytes、相对预热增长163840bytes≤32MiB。原始peak={'peak_reserved': 184549376, 'peak_capacity': 524288, 'peak_pending': 2506, 'peak_inflight': 2, 'peak_queue_count': 8, 'peak_queue_bytes': 12416}；perbackend≤1。实际gateway/process采样最大间隔0.120142635/1.009750174s，100ms/1s是目标周期，不是硬实时保证。

## AC/RV映射与身份

| 项目 | 结论及证据 |
| --- | --- |
| AC01/RV01 | PASS：249已跟踪保护文件逐字节对HEAD不变；产品/S1工具/历史保持。唯一旧测试例外经Approved返工。三配置实际加载且模板一致 |
| AC02/RV02 | PASS：21cell/2970ID、固定分母/双SLO/完整长短类与等待/后台逐ID复算、新负控及独立反例 |
| AC03/RV03 | PASS：真实超时未派发、终态/资源/PID/预算回归、故障与未来ID留存 |
| AC04/RV04 | PASS：两rate各3/3有效，低负载无误杀；数值门槛和工具限制独立复算，拒绝一般推荐 |
| AC05/RV05 | PASS：独立三套21/21、新控制及唯一矩阵完成，源/42个自有产物前后身份不变；最终状态同步由Leader执行 |

E中identity-before/after.json保存249项保护与42自有binary身份；run-002-sha256.json逐文件封存原始矩阵，manifest保存请求/源/平台/host；raw-audit.json是独立复算而非项目analysis复制。关键SHA256：

- `docs/leader/designs/V0.4/S2-design.md`：`e26173c6cc5862d37f95cff96162be814a23018829eaa4cfe2cce50ae9bd0410`
- `docs/reviewer/reviews/V0.4/S2-review.md`：`20d0e143bdf7b2e6f8d34bcefa203d8a7880d269873b4c2cd2d45aa7d7207692`
- `docs/leader/reworks/V0.4/S2-rework-001.md`：`87a4aa4eb633c7a0710c0c9393a43c015a9f1a85b4aa83c1668c420b808d5eb4`
- `docs/leader/reworks/V0.4/S2-rework-002.md`：`2ba1b374c572cdf92a8b9b18d27126c36b237a2450752c7565e2ec6a472ca542`
- `docs/leader/reports/V0.4/S2-report-004.md`：`97ac1d5ba935c38c676d737121371bbea814480e9c8df5d2a441e3dcfb6ede89`
- `docs/leader/reworks/V0.4/S2-rework-003.md`：`d28f69e9de47a15ac77ee29058c576cb0c55b7ef10c50e83fa9a87fdb4fe2ac2`
- `docs/leader/reports/V0.4/S2-report-005.md`：`5e690852261c545419ce26cfec08abf7cfd6ae310797bbe2be9fd3d0494bd970`
- `docs/builder/reports/V0.4/S2-report-004.md`：`e8fe3babee2682b278008cc660db18481036a68b1a89e20c2944c63fbb2e33c3`
- `tests/admission/RunAdmission.py`：`cc04f6141a569287fc5bfc58d33ea965119e18f8a687a076f685359783c02e24`
- `build-local/reviewer/v0.4-s2/evidence/identity-after.json`：`cc1b0765e887fc151957d778ff581b544deeb3986240842994b0cf43cd6100e7`
- `build-local/reviewer/v0.4-s2/evidence/raw-audit.json`：`beb9c2972993bce8b7368013b2d0bca71e177b608df6f67786850b7f1f3fb997`
- `build-local/reviewer/v0.4-s2/evidence/run-002-sha256.json`：`036e1f939b6eba2fb02e02b6ffdd2fcc8b5e4c0773c77ff8e6e5263a0d4f5651`
- `build-local/reviewer/v0.4-s2/evidence/RawAudit.py`：`258994b1a9659aed2824a8b727046bd8e0fed4ef206956b1efa60bbec797c43a`
- `build-local/reviewer/v0.4-s2/evidence/SuperviseRun002.py`：`f6572aab4cada6b67da2020c500864e713d7968c9b9a7e7625d32c237fd376f7`
- `build-local/reviewer/v0.4-s2/evidence/supervisor-002-events.jsonl`：`dfe197e3791ddb84603b0f4b22da183722857b54dbf4fc302c302dc17e4c8ac8`
- `build-local/reviewer/v0.4-s2/evidence/supervisor-002-result.json`：`72a56ef7b37ba5a3cd002faaf4c5aad839416b23269244e8506e09053600436b`

## 发现、未验证项及交接

无Blocker/Major/Minor、无返工要求、无待接受债项。观察限制为发压端敏感/CPU和固定合成工作负载；真实GPU/模型、最优参数搜索、容量/因果和V0.5均不在本阶段验收。首次失败现场缺失的returncode不补写。本轮未发现需要进一步返工的问题，不启动第四轮。

Leader下一步按本报告同步README/ROADMAP/ARCHITECTURE当前状态、CHANGELOG、结果中的独立数据和收口报告，保留历史批准/失败及Builder原数据，避免历史快照被当成当前状态；Coordinator之后精确本地提交、不推送。Reviewer不宣布已提交、不修改实现或其它文档，不重跑矩阵。
