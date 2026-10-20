# V0.3/S3 Builder 返工报告002

2026-10-20，Hephaestus。依据Reviewer001 F-001（Major），当前累计返工 **2/2**，最后允许返工。修复及自测完成，交独立Reviewer；不宣称验收通过，不提交/推送。若之后仍需第三轮纠正，必须硬停交协调者。

## 原因与修复

[Reviewer001](../../../reviewer/reports/V0.3/S3-report-001.md) SHA256 `0d6078027f4d3760798612abe6471771f259d7cc203d1a8b7fe7c525b581e506` 指出完整run的128MiB预算只有事后检查。确认该问题；Builder001“有界”描述缺少运行期总量保障，原小体积成功不能证明此契约。旧报告/正式结果保持原字节，不用改历史消除失败。原Approved五件套仍有效。

新Budget.py建立严格分区上界：**96MiB直接文件预留＋28MiB Python累计写入＋4MiB错误保留＝128MiB**。RunMvp在plan/manifest前激活预算；所有目录内Python写入先序列化为字节、在同一RLock内检查/计费，再写，覆盖不退账，因此并发、部分写入、覆盖临时文件均不能超出已计费上界。包括manifest、计划、配置、资产、event/resource、attempt、join/summary和最终result；没有仅靠事后遍历。

子进程输出采用系统已有`/usr/bin/prlimit`执行RLIMIT_FSIZE=4MiB，core=0；不使用多线程Python的preexec_fn。每次启动前为全部直接路径预留全额，不是只为进程预留单份。host写四个路径：合并stdout/stderr日志、state、state.partial、history；原子rename前两份快照同时存在也分别计入。其他固定backend/official只向继承stdout/stderr合并日志写输出，模型只读；不新增外部可写接口。真实最多7路径=28MiB（1host四路径＋2backend/1official三日志），模拟最多20路径=80MiB（5host），均落在96MiB池。跨组不回收预留，防止先前文件被遗忘。超出预留池在spawn之前失败；直接文件单次写穿由内核拒绝，10ms目标监视或成功前复查把达到边界转成明确BudgetExceeded，终止自有进程，不能仅留SIGXFSZ而继续成功。

正常池耗尽停止整个run。已开始attempt的finally保留身份、错误、时刻、状态、实际字节/hash及有界正文前缀，明确failure/evidence_truncated；不能把截断证据标为成功。最大29条，正文/错误各4096字符，ASCII转义最坏仍为每条有界数十KiB，全部小于4MiB错误池；同池包含固定最多9个正式run子进程start/reaped、有限cleanup错误及最终FAIL。该池本身也严格锁内计费，不因错误而无限豁免。全局失败只通知一次，避免不断打断清理；cleanup_all仍逐项执行，context退出额外kill/wait残余自有子进程。PASS前检查没有活子进程并复查预算。

## 修改范围与复用边界

新增Budget.py/BudgetTests.py；Common只替换本阶段写入/OwnedProcess，并给host列明三个直接快照路径；Attempts只将finally持久化交给预算；RunMvp增加预算上下文/失败记录/成功前检查。追加README、来源、结果更正和拆解。未改产品、C++ host、CMake、旧工具、Real.py、Simulated.py及协议验证/矩阵门闩；不改Approved128MiB或固定分母/期限。

E=`build-local/builder/v0.3-s3/evidence`。E/budget-source-diff.patch通过把三个既有Python文件逆变换并对照Builder001保存SHA验证后产生，精确列出本轮修改；不是以手写说明代替diff。98个其他原源/配置文件身份及全部48二进制与Builder001一致。旧102源清单中的另4项为Common/Attempts/RunMvp/README；新增2个Python后新清单104项。原Builder001 SHA仍为`f291b821785ade44f698d5704337da017bf0bbedd819de864e0c3efcac64fd4e`。

因此复用修复前真实28、模拟29和Debug/Release/ASan各20/20作为**产品/矩阵功能**证据，不声称旧run执行了新预算。本轮针对新的写入/进程启动路径执行下列短控及三套受影响MvpDetectors，没有重复模型负载/旧长矩阵。C++没有变动，复用原clang-format-18实际格式化/dry-run及独立Reviewer人工规范检查，不虚构本轮C++改动或重建。

## 实际短控

沿原生WSL、/bin/bash login=false、cwd仓库根；所有Python/测试显式TMPDIR/TMP/TEMP为build-local/builder/v0.3-s3/tmp，XDG_CACHE_HOME为同角色cache，PYTHONPYCACHEPREFIX为cache/pycache。socket/LSan首次精准升级，不关闭检测。

```bash
python3 tests/mvp/BudgetTests.py \
  --host build-local/builder/v0.3-s3/release/MvpRuntimeHost \
  --output build-local/builder/v0.3-s3/evidence/budget-003
ctest --test-dir build-local/builder/v0.3-s3/debug -R '^MvpDetectors$' --output-on-failure
```

后者release/asan各实际执行一次。`python3 -m py_compile tests/mvp/*.py`与`git diff --check`退出0。

| 检查 | 实际结果 | 证据 |
| --- | --- | --- |
| 多文件累计 | 每项4000bytes小于8192，合计写入前拒绝；已有attempt/error保留，sleep子进程回收；子驱动exit2 | budget-003/aggregate及相邻audit |
| 多线程 | 4线程各2100bytes，共享8192池，锁内预先拒绝累计超限；exit2 | concurrent |
| 原子替换 | state.partial/rename循环按累计字节计费，不退覆盖额度；exit2 | replacement |
| 实际子进程硬限 | 子进程向预留路径写9000bytes，8192硬限截住，记录明确文件名与BudgetExceeded；exit2 | direct |
| 实际多进程多文件 | 前两进程各3个raw文件＋stdout预留满65536池，每文件实际仅1000bytes；第三进程在spawn前拒绝；前两均回收；exit2 | direct_aggregate |
| attempt保留 | 超常规池的record写入错误池，标failure/evidence_truncated；exit2 | attempt_fallback |
| 真实HTTP attempt | 本地TCP发送合法200非流大正文，实际Attempt线程finally触预算，保留hash/部分证据和明确failure，无PASS；exit2 | actual_attempt |
| 正常短控 | 相同预算路径启动真实MvpRuntimeHost，idle排空/正常停止、文件有界；exit0 | normal |
| 三套MvpDetectors | 各1/1，驱动exit0；旧11类负控与host短控通过 | ctest-{debug,release,asan}-budget.log |

全部7个负控独立子驱动真实退出2，正常子驱动0；总驱动0。每case核对存储实际大小≤各池总和、已发生attempt与错误存在、所属进程退出、耗时<10s。测试审计另放受限case目录外；不是把审计悄悄写入受限目录绕过预算。探索性budget-001/002也保留（均通过）；003是最终冻结版，新增真实Attempt及子驱动退出码证明，并加入禁止core/最终兜底回收，未覆盖旧证据。

## 身份与交接

- E/source-builder002-sha256.json：104项，SHA256 `3d5ba3720ec752b7159702e8268bf10cfaf33596afc2c86ba92e49ba550bad54`。
- E/binaries-final-sha256.json：48项仍完全一致，SHA256 `35398630951d9f43a272f8d1708ba16eb00ae0493135becd30e891b63c5817dd`。
- E/budget-source-diff.patch SHA256 `250ef10e12131dcab632bcea1655251ade48628f768ea472cc9fc333c0df31e7`。
- E/budget-reuse-proof.json SHA256 `3d37e9e9e6837456ca988b92e2f9db36f11ef43a618a04da8c4aa90268134162`。
- E/budget-003/audit.json SHA256 `0abe64eb752f9ba1a4148975a144f0c74a1eca0f91a1f8945cdf32b270ce51e1`。

Reviewer重点独立核对预算池总和/所有直接路径乘积、并发计费和原子覆盖、异常清理及failure证据，不将旧功能PASS误读为新预算验证。运行期存储边界已自检；真实慢读未触高水、协议健康、共享CPU小样本和采样非硬实时限制仍保留。所有本轮测试子进程已回收；现在停止，交独立Reviewer裁决。
