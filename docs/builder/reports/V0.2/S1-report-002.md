# V0.2/S1 Builder 第1轮受限返工报告002

2026-10-19；Builder Hephaestus；累计返工**1/2**，状态Reworking，修复自测完成待独立复验。唯一初审发现[V02-S1-F-001](../../../reviewer/reports/V0.2/S1-report-001.md)为Major；本报告不代替Reviewer接受，不提交或推送，不开启后续阶段。

## 权威与路线

Approved设计SHA `11ecb703242f5c1077e3205ed2de5ab43f7b53d619e81c1b6dea5b6507d02711`、审查计划SHA `272ed417a6b8aeb4fab819fd7f288c13bb7c7729a7f0a6f2bea1301149e1e1f9`均保持；落实原AC04/05 response绝对期限，不修改权威。读取Reviewer001、原Builder001和当前代码，复读agent-execution-route、personal-cpp-standards规则与正反例；无项目Builder指南，沿原plan-project-docs全局模板回退。

路线原生WSL `/bin/bash` login=false、cwd `/home/power/projects/AI-Inference-L7-Gateway`，分支`codex/v0.2-s1-streaming`，HEAD `d653e9c400517783d5d33025a0b66a737c8256eb`未变。所有本轮构建/Python均显式TMPDIR/TMP/TEMP=`$PWD/build-local/builder/v0.2-s1/tmp`、XDG_CACHE_HOME=`$PWD/build-local/builder/v0.2-s1/cache`。Socket/sanitizer测试首次精确窄升级，无网络、安装、派生代理。证据根E=`build-local/builder/v0.2-s1/evidence`，全部新增r1前缀，初稿与Reviewer原日志不覆盖。

## 修复与回归范围

根因：流read/parse/finishInput返回可能已经跨截止，但acceptStreamResult先设置streamHttpComplete并撤除response deadline，再排成功终止块；后续写检查再也看不到response期限。

产品只改`src/gateway/ProxySession.cpp`：在complete分支置完成标志、移除response期限、排零块之前重新`checkDeadline()`。沿用现有比较（now等于截止即过期）和发前504/发后finish规则；候选正常头/正文尚未send时由错误路径清理。checkDeadline仍看见streamHttpComplete=false，total最早及同刻total优先保持。已由强制停止终结的会话依原事件入口保护，不会重新恢复。

复核前空→非空批次先记录新的outputStarted，避免新追加尾片让已排空批次的旧写期限重新参与判断。仅非空才参与nextDeadline，空输出不启动活动期限；这是完成复核所需的时序一致性修正，不改变批次定义或刷新持续积压期限。

测试只改`tests/RuntimeTests.cpp`：FakeIo增加一次性上游read推进时钟接缝；`checkStreamCompletionDeadline`、`testStreamingCompletionDeadlines`固定覆盖：

| 维度 | 输入/期望 |
| --- | --- |
| 定界 | CL最后正文、chunked最后零块、EOF read=0 |
| 提交 | 无send（EOF有候选头/正文）、仅首字节“H”、完整头和正文前缀 |
| 时刻 | 最后read从截止前进入，返回时9/10/11ms；期限10ms；9正常零块，10/11未提交仅504、已提交保留原前缀并截断 |
| 期限 | response=10/total=1000、response=1000/total=10、二者同为10；共81组合；同刻及total最早发前明确断言total_timeout |
| 批次/停止 | 原头/前缀已排空，间隔20ms超过旧10ms写期限但新正常尾片仍完成；三个提交状态下强制finish后迟到零块不能复活或追加内容 |

原Runtime真实首信号/二次信号/关闭期限、等待首片/closing与资源清理对照仍由三套完整回归执行。接缝强制finish不冒充真实信号优先级证明，真实信号由原Runtime/StreamingE2E证明。本次未改变其测试输入。

## 实际命令和结果

```bash
export TMPDIR="$PWD/build-local/builder/v0.2-s1/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.2-s1/cache"
cmake --build build-local/builder/v0.2-s1/debug -j 4
ctest --test-dir build-local/builder/v0.2-s1/debug --output-on-failure
```

release、asan同样替换目录；复用已配置的独立Builder三预设构建树。最终构建E/r1-{mode}-build-last.log各exit0；完整测试E/r1-{mode}-test.log：Debug11/11（14.95s）、Release11/11（12.09s）、ASan+UBSan11/11（30.59s），各exit0，无sanitizer诊断。原始逐测试输出独立复制为E/r1-{mode}-LastTest.log。早期Runtime定向验证E/r1-runtime-test.log 1/1 exit0；之后补写批次对照，以上最终完整回归覆盖当前最终测试身份。本轮没有失败测试日志被隐去，实际本轮测试均通过。

Reviewer两探针原文件逐字节复制为E/r1-DeadlineMatrix.cpp及r1-TotalDeadlineMatrix.cpp，不修改原输入。分别链接修复后Builder Debug库：

```bash
c++ -std=c++20 -g -I src -I tests -I third_party/llhttp/include \
  build-local/builder/v0.2-s1/evidence/r1-DeadlineMatrix.cpp \
  build-local/builder/v0.2-s1/debug/libgateway_runtime.a \
  build-local/builder/v0.2-s1/debug/libgateway_foundation.a \
  build-local/builder/v0.2-s1/debug/libllhttp.a -pthread \
  -o build-local/builder/v0.2-s1/evidence/r1-DeadlineMatrix
build-local/builder/v0.2-s1/evidence/r1-DeadlineMatrix
```

TotalDeadlineMatrix替换名称同样执行。E/r1-DeadlineMatrix-build-final.log与r1-TotalDeadlineMatrix-build-final.log编译exit0；运行E/r1-deadline-matrix.log **FAILURES 0 OF 18、exit0**，原审查为12/18失败；E/r1-total-matrix.log **FAILURES 0 OF 18、exit0**，保持原对照。修复后产品库身份与最终三套构建一致，最后增量仅补Runtime新批次断言，不改库。Reviewer旧反例与total日志完整保留。

本轮没有重跑历史18cell、旧关闭窗口独立探针或独立ParseOrderProbe，复用初审通过证据作为未修改分支背景；完整GatewayE2E内正常/错误握手和全部StreamingE2E已经重新运行。Release AssertionFailure负控包含于完整CTest，本轮未另跑独立负控命令。

## 格式、身份及交接

实际`clang-format-18 -i src/gateway/ProxySession.cpp tests/RuntimeTests.cpp`及同两文件`--dry-run --Werror`执行exit0；最终E/r1-format-last.log，早期格式日志保留。人工逐函数复核新增辅助/矩阵和邻接定义各有空行，FakeIo字段/分支职责明确；新增业务测试无lambda，产品原短转发回调未变。git diff --check exit0。

来源表当前两文件hash已更新，初稿source-final-sha256.json、Builder001、Reviewer001保持不变。当前用E/r1-source-sha256.json（54项）、r1-binaries-sha256.json（18项）并逐项匹配最终文件。仅ProxySession.cpp/RuntimeTests.cpp相较初版产品/测试身份改变，其他52项一致；Approved hash见r1-authority.sha256；审计见r1-handoff-audit.log。拆解状态记录当前1/2，未重置历史计数。

待Reviewer独立确认F-001关闭；没有新增已知失败、范围冲突或环境阻塞。请重点复验完成转换前仍包含response期限、恰等于截止、仅首字节提交、旧批次排空后的新尾片、total同刻及原强制停止保护。交接后停止本轮，不自行开展下一轮返工。
