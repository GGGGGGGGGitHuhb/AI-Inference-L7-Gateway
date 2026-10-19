# V0.2/S1 Builder 初次实现报告001

2026-10-19；Builder Hephaestus；初次实现，累计返工0/2。结论：实现和Builder自测完成，等待独立Reviewer；未提交、未推送、未进入S2。V0.1历史计数不变。

## 依据、目标与路线

依据Approved [设计](../../../leader/designs/V0.2/S1-design.md)、[审查计划](../../../reviewer/reviews/V0.2/S1-review.md)及Leader001，参照V0.1/S3收口、S2关闭返工002。目标是受限文本stream=true的SSE字节增量链路，同时保留原非流式/池/关闭行为。设计SHA为11ecb703242f5c1077e3205ed2de5ab43f7b53d619e81c1b6dea5b6507d02711；审查SHA为272ed417a6b8aeb4fab819fd7f288c13bb7c7729a7f0a6f2bea1301149e1e1f9，交接核验相同。

执行原生WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`，分支`codex/v0.2-s1-streaming`，HEAD `d653e9c400517783d5d33025a0b66a737c8256eb`。遵循agent-execution-route、personal-cpp-standards完整规则/正反例和plan-project-docs；无项目Builder指南，回退全局`plan-project-docs/references/role-guides/builder-guide-template.md`。保留Leader根文档变更；无第三方/net/pool/历史manifest变更、联网或安装。

角色目录`build-local/builder/v0.2-s1`，构建/Python使用TMPDIR/TMP/TEMP指向其tmp，XDG_CACHE_HOME指向cache。首次恢复诊断的本地脚本/增量构建未重复export，脚本未创建临时文件；后续全部显式设置，产物仍在角色目录。Socket/LSan测试按已知边界精确升级，不禁用检查。证据均在该目录的`evidence/`，是本地材料，不代表已发布。

## 实现与覆盖

文件及起点/当前hash见[变化记录](../../../references/V0.2-S1-changes.md)。没有改变批准范围。

| AC/RV | 实现与实际验证 |
| --- | --- |
| 01 请求/选择 | TextRequest仅允许布尔true，原体不改。HttpParser默认buffered，opt-in仅最终200且唯一合法SSE类型进入流；非SSE原预算回退。Protocol旧非法字段/方法/路径/头断言保留，仅合法true预期改变；StreamingParser覆盖合法charset/非法参数/重复头/非200/冲突/编码/1xx/JSON与204/304回退 |
| 02 增量/寿命 | parser固定16KiB片段和累计计数；body不积累。C trampoline捕获异常，只复制/检查；返回后ProxySession转换阶段、复制片段再reset，无IO/重入或悬空视图。StreamingParser全切分点、逐字节、20固定seed切分保留BOM/UTF8/注释/多行/DONE后数据；Runtime分配失败尽力500；真实CL/chunked/EOF分别先确认完整头、再确认不完整event/chunk前缀才放行尾部 |
| 03 定界/租约 | StreamOutput只在HTTP complete排一次零块，EOF0与RST区分，CL欠长/缺零块/坏后续块/trailer截断。stream=true可借idle但强制close且总invalidate（含JSON回退）。真实false,false,true,false,false产生2连接5请求；早期SSE停止上传且不误记写完，空pending不SHUT_WR；真实客户端SHUT_WR仍收完整流、RST使上游关闭 |
| 04 提交/异常 | 独立responseStarted在send接受任意字节设置；消费压缩不重置。FakeIO精确仅发送“H”后EAGAIN、完整头/前缀已耗尽、候选头未发送三种再截断：前者无二次头/零块，未提交仅502；已排200但无send的response超时仅504，回调异常500；pending超限提交前后同样分流。真实故障在客户端已见前缀后触发 |
| 05 资源/期限 | 固定pending256KiB含封装，16KiB解析片/recv，8MiB decoded/16MiB wire计数；边界接缝N−1/N/N+1、真实8MiB累计及超一字节、fallback4MiB拒绝、chunk/header原限制。固定response/total与连续非空batch写期限，部分进展不刷新；排空再到片才开新batch。真实4194427字节单上游chunk完整转发，慢读受限关闭期间正常请求仍完成；真实流正常/首信号期限/二次信号/等待首片终态session/reserved/pool/retired/timer归零，旧FD/公平回归保留 |
| 06 回归/格式 | 三预设全部11/11，原GatewayE2E448检查、ReuseE2E374、Pool166保留；旧120/150ms关闭窗口20次全成功。实际clang-format-18 -i/dry-run及人工函数边界/分组审查，详见下文 |
| 07 交付边界 | README同步初版支持和硬限制，明确待独立验收。无S2高低水位/动态账本、真实GPU或性能收益承诺；旧18cell没有重跑；权威/历史hash保护，协调者接受收口后本地commit |

检查计数是日志摘要，不能代替上述行为对应关系。下游请求仅一条；每方向64KiB/64次IO额度、原错误/closing窗口、满池立即503/no retry保持。

## 同时存活存储上界

新流路径使用固定array：pending262144字节，parser片段16384字节，recv栈16384字节。SSE模式HttpMessage.body始终空，已发送数据立即消费压缩，8MiB总流只作为计数；无按字节分配节点。streamOutput只在选择SSE后创建，未与整响应缓冲并存。最终头规范化临时串和header集合受16KiB/100头与固定头生成限制；保守留1MiB给头/对象/临时值，足够覆盖新增固定数组外的元数据。

阶段不是同时相加：请求SAX阶段沿旧≤8MiB逻辑存储推导，新增parser固定16KiB；请求规范化后销毁requestParser；流切换瞬间尚未释放的请求输出，当前libstdc++增长策略capacity保守小于2×(1MiB+64KiB)，加固定288KiB及1MiB元数据余量小于3.41MiB，随后立即释放请求输出。持续流仅固定288KiB及1MiB余量。非SSE回退保持原路径：请求输出capacity<2.125MiB、逐字节增长4MiB正文capacity<8MiB，规范化串最后一次大正文append在本libstdc++实现分配到所需≤4.0625MiB（此前仅有≤64KiB头），加1MiB元数据及16KiB片段，总保守<15.21MiB。这不是跨标准库capacity保证，当前构建使用已固定WSL/libstdc++；迁移标准库须重核旧buffered增长。新流数组容量不依赖实现增长。allocator/RSS/内核Socket buffer不作为精确16MiB逻辑预约。会话在closing仍预约16MiB，Runtime只在cleanup释放计数。

## 命令与结果

公共环境：

```bash
export TMPDIR="$PWD/build-local/builder/v0.2-s1/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.2-s1/cache"
cmake --preset debug -B build-local/builder/v0.2-s1/debug
cmake --build build-local/builder/v0.2-s1/debug -j 4
ctest --test-dir build-local/builder/v0.2-s1/debug --output-on-failure
```

release/asan同样替换目录/预设，configure/build exit0。最终C++补充首字节与发前504接缝后，三套增量build为`*-build-final2.log`。最终完整CTest分别`debug-test-final2.log` 11/11 14.40s、`release-test-final2.log` 11/11 11.74s、`asan-test-final2.log` 11/11 28.24s，全部exit0，无sanitizer错误；逐测试原始输出另存`*-LastTest-final2.log`。注册项见`test-registration.log`：StreamingParser、StreamingE2E、ReuseE2E、Pool、Runtime、GatewayE2E、Foundation、AssertionFailure、Protocol、MockBackend、Manifest。

最终审查矩阵又补充了真实下游RST取消场景，仅更改StreamingE2E Python文件；对三套二进制分别运行`ctest --test-dir build-local/builder/v0.2-s1/<mode> -R '^StreamingE2E$' --output-on-failure`，全部1/1 exit0（`*-cancel-final.log`、`*-LastTest-cancel.log`）。其余产品/C++测试字节未变化，复用上述三套完整回归，不无谓重跑。

`build-local/builder/v0.2-s1/release/FoundationTests --intentional-failure`真实exit1（release-negative.log），不是Release关闭断言导致假绿。`python3 build-local/reviewer/s2/evidence/CloseWindow.py build-local/builder/v0.2-s1/release/ai-inference-gateway` exit0，原后端120ms/额外写150ms/20次，`close-window-final.log`记录20完整响应和FAILURES 0 OF 20；脚本SHA158de752e714596bbdacf5e0e5c351d098d74239faf95d3b7f4d63ec8b58b425未改。原正常/错误握手由三套GatewayE2E保留测试证明。

## 首次失败与修正记录

首次基础Debug11/11通过（debug-test-initial.log）；FakeIO扩展3/3通过（debug-stream-expanded.log）。后续新增Runtime真实流资源快照探针首次失败：`debug-resource-test.log`中Runtime eof line1084；诊断`debug-resource-diagnostic-test.log`显示stopMode=1、active=0、timers=0。根因是测试在停止后仍把100次runtime.pollOnce(1)当100ms等待，实际上已停止循环立即返回，TCP EOF尚未交付。改为每轮对客户端fd显式有界poll等待，再读FIN/RST；不改产品或弱化EOF断言。`debug-resource-fixed-test.log`3/3通过，最终三套Runtime均通过。所有初次失败/诊断/修正日志保留，无覆盖、无删除失败样本。

## 格式与人工复核

实际工具clang-format-18（版本见format.log），对以下12个文件执行`-i`及`--dry-run --Werror` exit0：src/gateway/ProxySession.cpp/.h、TextRequest.cpp；src/http/HttpParser.cpp/.h、HttpNormalization.cpp/.h、StreamOutput.cpp/.h；tests/ProtocolTests.cpp、RuntimeTests.cpp、StreamingParserTests.cpp。Runtime末次测试补充后再次-i/check。完整可复现命令见format-manual.txt。git diff --check exit0。

人工逐文件检查：ProxySession新增beginStream/acceptStreamResult/writeStream与相邻定义都有空行，流接口/状态按职责分组、注册lambda仍仅转发；TextRequest内部TextSax构造与接口分组，外部JSON override名称按例外保留；HttpParser新增selectResponseMode、handleBody及相邻函数空行，私有固定片段/llhttp状态分组，沿用原C trampoline宏捕获全部异常；Normalization/StreamOutput独立函数均有空行，append前校验、无历史累积；ProtocolTests补齐原operator定义间空行，原断言保留；Runtime新接缝、辅助、流测试与邻接定义空行，复杂场景函数按连贯测试职责保留，不制造业务lambda；StreamingParser按碎片、选择、预算、输出职责分开，具名辅助；所有头无新增多行内联连续挤压。未把格式工具通过等同人工规则通过。

## 交接与需独立关注

当前没有已知未解决实现失败或批准范围冲突；未完成项是Reviewer独立验证、Leader收口及协调者本地提交。重点请复核首字节commit（包含只有“H”）、parse返回后错误优先于候选输出、真实后端双门控、慢读硬溢出、批次期限与response绝对期、stream=true的非SSE回退仍invalidate，以及当前标准库下旧buffered capacity推导。

源码/测试/配置完整最终身份`source-final-sha256.json`，二进制`binaries-final-sha256.json`，权威和关闭探针`authority-final.sha256`；最终Python追加取消场景已更新身份，并单独注明增量证据。无声称独立接受或V0.2整体完成。
