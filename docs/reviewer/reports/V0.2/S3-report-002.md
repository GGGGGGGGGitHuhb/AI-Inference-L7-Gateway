# V0.2/S3 Reviewer 最后一轮独立复验报告002

2026-10-19；Reviewer (Athena)。结论：**PASS**。唯一Major **V02-S3-F-001已关闭**，无新增发现、未接受Minor、债项或契约内阻塞项。累计返工 **2/2**，没有第三轮。初审FAIL、原始丢失反例和旧长期结果全部保留。本报告不代Leader关闭S3/V0.2，不表示已经提交或推送。

## 1. 权威与执行路线

完整读取Builder003、当前来源/breakdown、r2精确差异及身份，依据Reviewer001§2发现与§7最小复验条件。继续使用用户AGENTS、agent-execution-route、personal-cpp-standards及plan-project-docs全局Reviewer模板回退；项目无专用Reviewer指南。

Approved设计SHA `af975691b5540600e9f8c894b0964346ba6ad3b77c30bc420eedaea74475ae5a`、审查SHA `1315d12f060048cd5706e59a552a3658e4e6d2e45e8145d7369ca06bc2b7b0b5`保持；Reviewer001 SHA仍为`6e2530c1ec09b4fd93e269ed30c5ed44bc8894100f017657abffc93c7063e313`。

原生WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`，分支`codex/v0.2-s3-integration`，基线HEAD `d933e8892033a600b68ff5ac0db950dec5abea90`。沿Reviewer自有`build-local/reviewer/v0.2-s3/{tmp,cache,evidence,debug,release,asan}`；E指evidence。本轮新增r2前缀，旧输出不覆盖。脚本/配置前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME；socket/loopback精确窄升级；不安装/下载、不派agent、不改产品/工具/权威、不commit/push。共享资产只读，模型/host/gateway独立PID与端口，实际始终只启一个模型。

## 2. 精确差异与长期证据复用判定

独立重算当前65项源码身份并与Builder003清单逐项匹配。初审64项中恰好4项变化、60项不变，新增1项：

- Support.py：把编码/连接纳入异常与finally边界，保留partial结果；添加recorded_exchange唯一落盘包装。
- RealRun.py：协议与soak调用包装，原正常校验纳入记录作用域。
- SyntheticRun.py：worker、预热及unsupported请求走包装；worker记录在原锁内。原校验谓词保持，协调端既有校验仍在，未放宽成功条件。
- CMakeLists.txt：仅追加IntegrationAttempts快速入口。
- 新增AttemptTests.py：13类异常及并发晚到失败回归。

独立将Builder保存的r2-before文件SHA与Reviewer初审清单核对后，从这些已验证旧字节和当前文件重新生成E/r2-diff-*.patch，不只相信Builder自报patch。测试README/当前变化和breakdown另有本轮说明更新，不属于代码清单的4项计数。

产品src、RuntimeHost、WireResponse、Inputs、固定CLI、配置/期限/容量、正常send/recv与解帧、IO时刻采样、慢读节奏、seed/配比、4并发及closing退休门、资源采样和RSS/长期门槛不变。Reviewer初审36个二进制/静态库逐项SHA未变；本轮只重新配置Release使新增Python测试注册，不需要重建相同产品。

正常请求增加attempt_id与记录包装、将成功校验放入包装；这些属于初审§7允许的必要采样包装。异常记录不改变正常HTTP输入/输出、调度规则或资源限额。没有性能收益验收，不能把新增包装开销表述为零开销或新吞吐证明。下述完整短校准同时验证正常成功分类、无重复记录和输入/负载身份。

因此**满足Reviewer001§7的长期复用条件**。明确复用初审原身份下独立执行的真实601.662秒/1270请求、模拟310.192秒/650请求、三套13/13、原18+18期限与20关闭窗口及相关协议/取消/故障结果。旧source manifest SHA `72eee933535c0f66a19279d4b33d936c0a7b9e31200a0797fd3dcadc6a330d34`，旧binary manifest SHA `becb5a2bd132d5590ba9bdbdc97e3a4e621267b471ac152f0da5a2e934c80992`。

本轮没有重跑600/300秒、三套全量或18+18/20；不会把旧长期结果伪称当前65项源的重新全量执行。旧长期结果负责不变正常路径和固定负载，本轮新增证据负责改变的异常记录、传播与包装路径。无需因纯异常记录修复重复不变的长期实验。

## 3. F-001修复审查与独立反例

exchange现在在创建socket之前建立result，编码/连接失败也填入error、error_type、起止、请求hash及0字节hash。解析/结构/断言/回调异常携带同一partial对象继续传播；finally补正文计量、已知头/状态并关闭socket。已有网络/HTTP错误维持失败结果返回语义；其他异常、连接错误、KeyboardInterrupt/实际SIGTERM保持失败传播。content最终join失败也能记录并经嵌套finally关闭socket。

recorded_exchange在进程内生成唯一attempt_id，合并既有label/index；成功或异常最终只在一个finally出口append。校验错误记录error后再抛出，不把complete（HTTP层完成）等同整体有效。Synthetic worker自己完成落盘，不依赖协调循环成功取得future；首个future失败后其余已开始worker仍产生各自记录。

Reviewer原探针只改输出根为E/r2-probes，原时序/断言保持，旧文件/失败日志保留：

| 独立执行 | 本轮结果 |
| --- | --- |
| 原SampleLossProbe | 真实连接拒绝、模拟连接拒绝、非法SSE三例各1条；丢失0/3，exit0 |
| 原LateFailureProbe | 4个错开结束的future异常，4条记录，exit0 |
| 原FailureCleanupProbe | run失败子进程exit1，FAIL结果保留，两个自有进程reaped；外层exit0 |
| 原WireProbe | 8个原始解帧/尾随/截断对照通过，exit0；WireResponse本身未变 |
| 13类异常持久负控 | 每类恰1条、具体异常类型/partial bytes/hash/起止/request ID核对，socket确实关闭；全部子进程非零 |
| 首失败后晚到future新增控制 | 4个index与4个attempt_id唯一，全部错误留存 |

13类覆盖连接拒绝、连接超时注入、坏HTTP状态、坏CL、非法SSE、坏JSON、JSON结构缺失、非字符串content、回调RuntimeError、KeyboardInterrupt、实际SIGTERM、读取超时、完整非流HTTP后的JSON校验失败。持久原始文件在E/r2-attempt-records，各case包含attempts.jsonl、child.log；exits.json区分普通exit1与中断exit-2。中断仍非零，记录interrupted=true；不是仅mock一个异常名。

读取超时保留6字节partial，非法SSE保留10字节，回调/中断保留68字节；连接失败为0字节，均有hash与已知元数据。完整HTTP但JSON无效的校验也先记录错误再非零。独立r2-AttemptAudit.py核对所有case，exit0。原失败及本轮通过对照具备相同根因覆盖，**正式关闭V02-S3-F-001**。

Builder早期新fixture未先SHUT_WR导致JSON验证案例先遇读超时的失败日志仍保留；当前测试要求每例具体error_type，已独立得到validation=JSONDecodeError，未以任意非零冒充目标异常。

## 4. 快速回归与完整短校准

重新配置Reviewer Release后，CTest实际注册14入口；本轮只运行`IntegrationDetectors`和`IntegrationAttempts`：**2/2，2.50秒，exit0**。E/r2-test-registration.log、r2-fast-ctest.log、r2-fast-LastTest.log保留。旧9项负控和新13类/4晚到均执行，没有声称14/14。Python py_compile与git diff --check通过；无新增C++，本轮不重复无关格式化/编译。

独立启动固定CPU资产，实际模型CLI和hash检查沿原要求，不接管Builder进程；两个显式命令使用Reviewer原Release产物，增加`--calibration`和新输出目录：

| 校准 | 本轮实际结果 |
| --- | --- |
| E/r2-real-calibration | **CALIBRATION_PASS，87条/87唯一attempt_id，exit0**。含8预热、direct/proxy各20正式、长3/慢3/SHUT_WR3、context错误、5取消及恢复、3轮后端故障与每轮4恢复、正式gateway流/非流及活动停止 |
| E/r2-synthetic-calibration | **CALIBRATION_PASS，50正式请求，exit0**；另1未支持字段+5预热，共56条/56唯一ID。40正常/5取消/5故障，累计256次pause/resume，最终活动账本0 |

E/r2-CalibrationAudit.py独立复算记录数量、唯一连续ID、实际formal分布、请求hash与初审同标签身份、长流≥16增量、取消5秒/恢复10秒边界、3轮故障、配置容量及最终资源。模拟前50个index的kind/request hash和非取消正文hash逐项匹配初审seed序列。没有靠Builder汇总或只看CALIBRATION_PASS字符串。

两校准所有排空点FD7、sessions/reserved/capacity/pending/paused/timers/upstreams/leased/idle/pool_total/retired为0；全部快照预约≤64MiB、数组≤1MiB、pending≤capacity。真实6个自有进程、模拟1个host均有start/reaped对应且/proc无残留；后端线程由驱动结束回收。独立清理探针的两个进程也已回收。原始记录见各processes.jsonl及E/r2-calibration-audit.json。

这些仅是短校准，不用于替代原600/300秒门槛；长期证据的复用身份与适用边界已在§2明确。

## 5. 当前身份、原始命令与保护

- E/r2-source-sha256.json独立65项，SHA256 **`04ff60400ca0996a096caa397a1d5afb8bb21cc8923973353fac7b1139db7176`**。
- 当前Support.py：`637c54b69dbebd5caca631343bdf8446bb023f821ba25b1c0bea919124f19210`。
- 当前RealRun.py：`bb6a1c7b19e448ef46f9571547bfac87c3aeeded97bab927802643867379cb32`。
- 当前SyntheticRun.py：`cdae80eb023a7a2ed46130ce08e6617e1f8b758c64792a85af0d010c532c6f99`。
- AttemptTests.py：`98426dcf8c3c9cab66c166d87998598a7637cef2cfca600e13de3a92d28301cd`。
- 36项Reviewer产物原字节不变，沿E/binaries-sha256.json；差异映射E/r2-identity.json及独立生成r2-diff-*.patch。

所有脚本/配置前：

```bash
export TMPDIR="$PWD/build-local/reviewer/v0.2-s3/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/reviewer/v0.2-s3/cache"
```

实际主要命令：

```bash
cmake --preset release -B build-local/reviewer/v0.2-s3/release
ctest --test-dir build-local/reviewer/v0.2-s3/release -R '^Integration(Detectors|Attempts)$' --output-on-failure
python3 tests/integration/RealRun.py --assets build-local/integration/v0.2-s3 --host "$PWD/build-local/reviewer/v0.2-s3/release/IntegrationRuntimeHost" --gateway "$PWD/build-local/reviewer/v0.2-s3/release/ai-inference-gateway" --output build-local/reviewer/v0.2-s3/evidence/r2-real-calibration --calibration
python3 tests/integration/SyntheticRun.py --host "$PWD/build-local/reviewer/v0.2-s3/release/IntegrationRuntimeHost" --output build-local/reviewer/v0.2-s3/evidence/r2-synthetic-calibration --calibration
```

原探针分别`python3 E/r2-{SampleLossProbe,LateFailureProbe,FailureCleanupProbe,WireProbe}.py`，持久负控`python3 E/r2-AttemptAudit.py`，校准核算`python3 E/r2-CalibrationAudit.py`，均顶层exit0；各负控子进程非零按预期单列。校准完整stdout和真实退出码见E/r2-{real,synthetic}-calibration.log/.exit。py_compile将PYTHONPYCACHEPREFIX显式指向角色tmp/pycache。

Approved、Reviewer001及原清单/失败/长期证据不覆盖。没有C++/产品/第三方变化，没有新资产下载或权限范围扩大。

## 6. 最终验收与交接

F-001关闭；修复后的异常留存/传播与正常短校准通过，结合按精确身份复用的初审完整协议/长期/回归，S3全部AC已有独立证据，结论PASS。无剩余发现、待接受债项或未验证阻塞项。

边界仍为单静态后端、单slot固定CPU模型与受限HTTP/SSE子集；取消仅报告网关资源、连接与CPU slot观察，不承诺GPU内核停止或调度性能；用户态容量预约不等于RSS/内核缓存。测试host没有变成产品管理API。既有长期实验阈值只支持固定负载结论。

请Leader依据本PASS完成S3/V0.2文档收口，再由协调者按用户既有授权本地提交、不推送。Reviewer已回收自有进程并停止，累计2/2保留，不开启第三轮或后续版本。
