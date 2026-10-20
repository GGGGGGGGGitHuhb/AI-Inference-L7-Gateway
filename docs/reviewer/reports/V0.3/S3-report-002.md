# V0.3/S3 独立有限复验报告002

2026-10-20，Reviewer（Athena）。**PASS；F-001关闭，累计返工2/2，无残余发现或待接受债务。** 本次为最后允许返工的有限复验，没有第三轮实施。原[Reviewer001 FAIL](S3-report-001.md)、Builder001及Approved历史原字节保留；本报告不把失败历史改为通过。交Leader收口，随后协调者本地提交、不推送；没有启动V0.4或宣称已经发布。

## 依据、独立性及复用范围

依据原Approved设计/审查计划、rework001及Leader002、Reviewer001的F-001与最小复验许可、[Builder002](../../../builder/reports/V0.3/S3-report-002.md)及源码差异。累计计数保持2/2。复用原生WSL路线：`/bin/bash login=false`、cwd=`/home/power/projects/AI-Inference-L7-Gateway`、分支`codex/v0.3-s3-mvp-acceptance`、HEAD=`d89de57eb6be0106bccd24432b2559d342ed8b79`。重新读取agent-execution-route；既有plan-project-docs Reviewer模板回退及personal-cpp-standards规则/正反例仍适用，本轮没有C++修改。

独立`build-local/reviewer/v0.3-s3/{tmp,cache,evidence}`，Python/短控显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；socket/LSan/prlimit短进程按窄权限执行，不禁检测器。以下E为该目录的evidence。没有修改产品、工具、Builder材料、旧报告/权威/根文件，没有提交推送。

E/R2Identity.py独立验证：原102源中98项不变，仅Common.py、Attempts.py、RunMvp.py、README.md变化；新增Budget.py/BudgetTests.py后104项。将当前三份Python复制到Reviewer临时目录，逆向应用Builder差异，再逐一与Reviewer001原源SHA比较，全部相同，证明差异没有隐藏矩阵/协议改动。产品、C++host、CMake、Real.py、Simulated.py不变；双方各48产物逐一核对原清单，均不变；191个HEAD保护文件不变。源码差异与新预算逻辑均人工审查，并非只信Builder复用声明。

因此复用Reviewer001独立三套20/20、真实28与模拟29为**修复前产品/固定矩阵功能证据**；这些旧run没有执行新预算，明确不作为新预算通过证据。保留原格式检查及人工C++审查，未重建或假称本轮重新全量测试/运行模型。

## F-001实现复核

完整run创建plan/manifest前激活RunBudget，预算为96MiB直接文件预留＋28MiBPython累计写入＋4MiB错误保留，合计128MiB。写前在同一RLock中按序列化字节计费；覆盖不退账，失败写入亦不退账，故当前存量不会超过累计已准许写入量。managed与direct路径不能混写；错误池也独立计费并有硬上限。

逐条检查实际正式run写入路径：plan/manifest/config/assets/events/resources/attempt/join/queue-waits/summary/result/cleanup均经Budget.save/append/save_attempt；Simulated后端记录也经该路径。其wfile输出是网络字节，不是目录日志。子进程合并stdout/stderr每路径先预留4MiB；host另声明state、state.partial、history三路径，包含原子替换前两个快照同时占用。真实最多7个直接路径预留28MiB，模拟五host共20路径预留80MiB；跨组不退预留，均在96MiB池内。新短检测器自身审计输出在受限case之外，未冒充正式run预算内文件。

prlimit在exec前设置RLIMIT_FSIZE软/硬均4MiB、core软/硬0，没有在多线程Python中使用preexec_fn。该限制覆盖每个子进程直接文件实际字节；启动前整组路径预留，不能靠每个文件单独未满绕过总预算。内核限制写穿；10ms目标监视器将触及边界变为预算失败，并终止自有进程；无论子进程是否忽略SIGXFSZ，不能继续生成超限文件。成功前finish检查无存活子进程及直接文件边界，context退出再兜底检查/回收。

正常池耗尽时保存已开始attempt的有界失败记录，保留身份、状态、时间、实际字节/hash、错误与正文前缀，明确failure/evidence_truncated，设置persistence_error使join失败，不能伪造完整成功正文。按固定最多29条及每记录正文/错误4096字符计算，最坏ASCII转义仍可由4MiB错误池容纳；过程start/reaped、有限cleanup及两层最终FAIL均从该池扣账。全局失败只首次发通知，cleanup_all仍逐项清理，预算context额外kill/wait兜底。未开始计划ID不伪造成attempt，成功结果必须精确计划分母；末态零值和缺失记录不混淆。

以上提供运行期间总量上界，不再依赖末尾合计检查。运行中对文件达到边界的错误通知可以受调度延迟影响，但硬文件限制与预留证明不依赖监视线程实时性。没有放宽128MiB契约。

## 独立短控与追加证据

实际命令：

```bash
python3 tests/mvp/BudgetTests.py --host build-local/reviewer/v0.3-s3/release/MvpRuntimeHost --output build-local/reviewer/v0.3-s3/evidence/r2-budget-001
ctest --test-dir build-local/reviewer/v0.3-s3/debug -R '^MvpDetectors$' --output-on-failure
ctest --test-dir build-local/reviewer/v0.3-s3/release -R '^MvpDetectors$' --output-on-failure
ctest --test-dir build-local/reviewer/v0.3-s3/asan -R '^MvpDetectors$' --output-on-failure
python3 build-local/reviewer/v0.3-s3/evidence/R2Independent.py
```

| 独立验证 | 结果与证据 |
| --- | --- |
| 7类预算负控＋正常host | 七子驱动各退出2，正常子驱动0；总体0。多文件累计、并发、覆盖、子进程硬限、多路径预留、失败record及真实HTTP Attempt finally均通过。E/r2-budget-001和r2-budget.log |
| 三套受影响MvpDetectors | 各1/1、退出0，Debug0.88s/Release0.85s/ASan0.91s；E/r2-ctest-*.log |
| Reviewer自写累计＋Unicode取证 | 两文件各1400bytes，3072池第三400byte写入前拒绝、目标文件未创建；自有sleep子进程回收；既有Unicode正文attempt转错误池，前缀/hash/failure保留。子驱动退出9 |
| Reviewer自写活跃子进程硬限 | 子进程显式忽略SIGXFSZ、写9000bytes后继续sleep；4096硬限使日志恰4096，监视器使run失败并回收该进程，未等矩阵结束。子驱动退出9 |
| Reviewer自写跨路径预留 | 首子进程为stdout/state/partial共三路径预留满12288池；第二次启动前拒绝，第二日志不存在、只启动一个进程且回收。子驱动退出9 |
| 差异/保护/进程 | E/r2-identity.json核验精确SHA；E/r2-process-audit.json核验7组记录共8个自有进程start/reaped配对且/proc不存在；git diff --check退出0 |

独立追加源码E/R2Independent.py，逐case审计`*-independent-audit.json`和`r2-independent-results.json`保留原始大小、计费、错误、PID及退出码；三个case均小于5秒、实际总量≤各池总额。没有只调用Builder总结来证明新保护。

## 身份与最终边界

- Builder002 SHA：19d96ecd5438bc374d44cc8e6424df9615b5cdd417d10392e02b51e21dd1b132。
- 原Reviewer001 SHA仍为0d6078027f4d3760798612abe6471771f259d7cc203d1a8b7fe7c525b581e506。
- 当前104源Builder清单SHA：3d5ba3720ec752b7159702e8268bf10cfaf33596afc2c86ba92e49ba550bad54；Reviewer独立核验副本E/r2-source-sha256.json。
- 精确差异SHA：250ef10e12131dcab632bcea1655251ade48628f768ea472cc9fc333c0df31e7。
- 双方48产物仍分别对应Reviewer001的3012f101380232e74b3adee79a80f2e1e97b39309fa0df1f5931b0d37f2612c6及Builder001的35398630951d9f43a272f8d1708ba16eb00ae0493135becd30e891b63c5817dd清单。
- Approved设计/审查/rework001/Leader002/Builder001全部SHA保持，完整锚点在E/r2-identity.json。

F-001关闭；结合Reviewer001已通过的其余AC，本阶段整体PASS，累计2/2，无新增发现或债务。资源已回收且Reviewer停止工作。真实慢读pauses=0、共享CPU、协议级健康、采样目标非硬实时及小样本非容量/SLO证明的原限制全部保持；现有README旧“至少每100ms”须结合Reviewer001实测间隔理解，Leader收口说明用目标周期表达。最终阶段/版本状态与本地提交由Leader/协调者负责。
