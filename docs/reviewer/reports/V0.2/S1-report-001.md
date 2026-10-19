# V0.2/S1 Reviewer 初次独立审查报告001

日期2026-10-19；Reviewer (Athena)。结论：**FAIL**。发现1项Major：流式最终读取跨越response绝对截止时，完成转换撤销了已过期的期限，错误发送正常终止块。当前累计返工0/2；本报告不提前启动返工、不关闭阶段、不提交/推送。没有新Minor、没有接受技术债。

## 1. 权威、范围与独立性

读取Approved V0.2/S1-design、S1-review、Leader001、Builder001/breakdown/变化记录，以及现行README/架构/路线与V0.1关闭/池验收边界。适用用户全局AGENTS；仓库无新增AGENTS或Reviewer指南，继续使用plan-project-docs全局Reviewer模板回退，已告知协调者。复用并核验agent-execution-route，遵循已完整读取的personal-cpp-standards规则与正反例。

路线：原生WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`，分支 `codex/v0.2-s1-streaming`，HEAD `d653e9c400517783d5d33025a0b66a737c8256eb`。独立构建/临时/缓存/证据为 `build-local/reviewer/v0.2-s1/{debug,release,asan,tmp,cache,evidence}`，所有构建/Python显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。已知Socket/LSan权限边界直接对精确测试命令窄升级；未先制造EPERM失败、未关闭sanitizer/跳过测试、未下载安装。

证据前缀 **E=`build-local/reviewer/v0.2-s1/evidence/`**。未使用Builder可变二进制运行验收；未改产品、测试、第三方、兄弟仓库、权威或历史报告，未派生代理。用户授权接受收口后由协调者本地提交、不推送，本角色不抢先执行。

身份独立核对见E/identity.log：Builder最终54项源码/测试/配置逐项匹配。独立清单E/source-sha256.json SHA256 `c3c6f8c82adf85facfba73b02092d6805610905fa2c447b709806dbcbe0f4376`；独立Release二进制SHA256 `7d98aba7d70e3c3aee16d619fd4ac3698fc8add999b3f39caa8aa0bbb5221f79`。批准设计保持 `11ecb703242f5c1077e3205ed2de5ab43f7b53d619e81c1b6dea5b6507d02711`，审查计划保持 `272ed417a6b8aeb4fab819fd7f288c13bb7c7729a7f0a6f2bea1301149e1e1f9`。

## 2. V02-S1-F-001 — Major：完成转换遗漏已过期response期限

**权威：** 设计§6/§7 REQ/AC-04、05，RV-04/05：response从本次连接启用起绝对计时，覆盖到HTTP完成；未send时超时返回504，已send后中断，不能发正常零chunk。

**位置：** `src/gateway/ProxySession.cpp:354–384` readUpstream、`:486–509` acceptStreamResult，尤其`:498`设置streamHttpComplete；nextDeadline的`:110–113`在该标志为true后不再考虑response。

**根因：** 每轮read仅在receiveBytes之前checkDeadline。recv/parse/finishInput返回后，stream完成路径没有再次核对仍有效的截止，先把streamHttpComplete设true并追加终止块，再armDeadline；已过期response因此永久从候选集合消失。非流式completeResponse原有checkDeadline，而新增流完成路径缺少等价保护。线程被抢占或解析耗时跨过截止均可能触发，不要求生产Socket阻塞。

**独立确定性复现：** E/DeadlineMatrix.cpp从当前RuntimeTests复制夹具到Reviewer目录，仅给FakeIo新增一次性“上游receive返回时推进单调时钟”的控制；未改产品。response=10ms、total=1000ms，读取事件开始时未超时，最终一次read返回时分别到9/10/11ms。覆盖CL最后正文、chunked最后零块、EOF定界read=0；各含未提交与已提交前缀两种状态。EOF未提交场景已有排队头/正文但尚无send，符合设计允许替换候选的边界。

| 最终读取时刻 | 期望 | 实际 |
| --- | --- | --- |
| 9ms，小于10ms | 正常流完成，一次零chunk | 6/6正确 |
| 10ms，恰等于截止 | 未提交仅504；已提交只截断、无零chunk | 6/6错误，均正常200和零chunk |
| 11ms，超过截止 | 同上 | 6/6错误，均正常200和零chunk |

E/deadline-matrix.log：**FAILURES 12 OF 18，exit1**。初始两例观察E/DeadlineProbe.cpp/deadline-probe.log也保留，该探针exit0表示打印观察，不作为通过证据。

**对照与边界：** E/TotalDeadlineMatrix.cpp只把同样矩阵换为total=10ms、response=1000ms，18/18通过（E/total-matrix.log，exit0）。total没有被完成标志移除，后续发送检查仍正确生成504或截断。因此本发现限定为response完成转换，不声称total同样失效。产品SIGTERM/第二信号/关闭截止在完整真实测试中通过；未声称发现新的shutdown故障。

**影响：** 客户端会把本应按response超时中断的流识别为正常HTTP完成，与README/设计绝对期限承诺不符。没有观察到内存损坏或串扰，因此定Major而非Blocker。

**返工要求：** 在读取/解析返回后的正常完成被接受、撤除response期限或排入成功终止块之前，重新执行仍有效的时间边界判定。恰等于截止按过期处理；保留发前504/发后截断及候选清理。不能仅增加配置时间、刷新response、先发零块再补错误，或仅依赖稍后已被重排的timer。保持total最早截止及既有shutdown强制优先级，不把HTTP完成当作取消所有约束。补CL/chunked/EOF的截止前/恰等于/超过矩阵以及未提交/首字节/完整前缀状态，保留total/停止对照。完成后重新独立验证相关三套回归与反例。

## 3. 全部RV检查与已通过证据

| RV/AC | 独立结果 |
| --- | --- |
| 01 请求/响应矩阵 | 通过。TextRequest仅把合法布尔true接入metadata，原body不改；ProtocolTests类型矩阵继续拒null/数字/字符串/重复等。parser仅opt-in且最终200/唯一合法SSE类型选择流，非SSE回退4MiB/8MiB；非法charset/参数、重复Content-Type、非200 SSE、编码/CL+TE/Connection等在finalHeadersReady之前拒绝。默认buffered仍拒SSE，合法1xx内部消费。 |
| 02 增量与C边界 | 通过。读取完整HttpParser、Normalization、StreamOutput与ProxySession流路径；C trampoline catch-all，回调只复制/验证固定片段，parse返回才IO/迁移/销毁。每recv≤16KiB，parser片段固定16KiB，body空且单独decoded/wire累计，无逐字节队列节点。全单切分、逐字节、20固定seed多切分和UTF8/BOM/DONE透明样本通过。真实CL/chunked/EOF双门控分别要求客户端先收到完整头、再收到未完成event/chunk前缀，后端才放行尾部，三套独立通过。 |
| 03 定界/租约 | 通过已覆盖正常及协议异常路径；超时完成另见F-001。CL恰长、chunk零尾、EOF read0正常完成；欠长、缺零尾、坏chunk/trailer、RST中断；DONE之后字节继续转发，无DONE长流正常结束。stream=true含JSON回退借池但强制close并invalidate，真实false/false/true/false/false为2连接5请求；原S3复用保持。early SSE停止上传、未完整标志不改，客户端SHUT_WR不取消，真实RST失效上游。 |
| 04 提交/错误 | 普通故障通过，但response完成超时分支FAIL。responseStarted只在send接受字节后置true，包含只发“H”；pending消费归零不撤销。未send候选可换502/504，已提交不二次头/伪零块；暂空不SHUT_WR。独立ParseOrderProbe补同次parse产生正文后坏CRLF/非法trailer/坏大小行：未commit只502，已commit仅“H”保持截断，16项断言通过。 |
| 05 预算/期限/停止 | 预算与其他已覆盖期限通过，response完成跨截止FAIL。固定pending262144含封装，片段/recv各16384，decoded8MiB/wire16MiB，append先检查减法边界；N−1/N/N+1、真实8MiB累计/超一字节、fallback4MiB限制及原headers/chunk限额回归通过。真实>4MiB单chunk双门控长流完整；慢客户端有限中断且正常请求仍完成。批次写期限不因部分进展刷新，排空后新批次起算；正常/首信号期限/第二信号/等待首片资源终态全部归零，16MiB预约保持到cleanup。 |
| 06 回归/规范 | 独立三套完整11/11通过、Release负控exit1、原120/150ms窗口20/20。旧GatewayE2E正常/错误握手、池/Runtime/ReuseE2E全部保留。clang-format18检查12文件通过，人工逐函数/职责分组检查未发现新规范问题；第三方/net/pool/旧manifest与返工权威未改。 |
| 07 交付审计 | 当前README准确标注实现待验收、S2高低水位/动态预算/真GPU未做；无性能收益/模型完成承诺。README所述response全程绝对期限目前有F-001差距，不能收口为已验收。54项来源hash和原始自测失败均可追溯。 |

检视文件包括全部12个受影响C++、StreamingE2E、CMake、来源表、README，以及沿用的Pool/Runtime/SessionIo/事件回调清理契约。没有用测试总数替代上表的状态与输入覆盖，没有用Builder报告代独立执行。

## 4. 存储推导与验证限制

新流pending为固定262144数组、parser片段16384数组、recv栈16384，合计288KiB；不会保存流历史，8MiB是总量计数。选择流后仅流输出与头元数据，不保留完整response body。切换时短暂请求输出capacity按当前libstdc++小于2×(1MiB+64KiB)，随后释放；沿Builder保守元数据余量后低于16MiB。

旧buffered分支仍依当前libstdc++增长行为而非跨标准库保证：独立ParseOrderProbe用4MiB逐字节正文及90个160字节头，实际body capacity=7,864,320、规范化output capacity=4,209,892（恰为size），见E/parse-order.log。源码先构造有界小头再一次append大正文，与当前标准库按所需容量分配一致。叠加请求输出<2.125MiB、1MiB元数据余量、16KiB新片段仍在Builder所述<15.21MiB保守界内。该探针是具体增长路径对照，结合源码推导使用，不是所有allocator/RSS/内核缓存的形式化上界或跨平台保证。更换标准库需重新验证。

## 5. 独立命令、结果与原始记录

公共环境：

```bash
export TMPDIR="$PWD/build-local/reviewer/v0.2-s1/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/reviewer/v0.2-s1/cache"
```

每mode单独保存配置/构建/测试日志和检查exit，mode=debug/release/asan：

```bash
cmake --preset "$mode" -B "build-local/reviewer/v0.2-s1/$mode"
cmake --build "build-local/reviewer/v0.2-s1/$mode" -j 4
ctest --test-dir "build-local/reviewer/v0.2-s1/$mode" --output-on-failure
```

E/{mode}-configure.log、{mode}-build.log均exit0；E/{mode}-test.log各11/11、exit0：Debug14.35s、Release11.49s、ASan/UBSan27.86s，无sanitizer诊断。CTest包括StreamingParser/StreamingE2E/ReuseE2E/Pool/Runtime/GatewayE2E/Foundation/AssertionFailure/Protocol/MockBackend/Manifest；各构建Testing/Temporary/LastTest.log保留详细用例输出。当前最终Python取消场景已包含在本轮完整三套内。

```bash
build-local/reviewer/v0.2-s1/release/FoundationTests --intentional-failure
python3 build-local/reviewer/v0.2-s1/evidence/CloseWindow.py build-local/reviewer/v0.2-s1/release/ai-inference-gateway
clang-format-18 --dry-run --Werror src/gateway/ProxySession.{h,cpp} src/gateway/TextRequest.cpp src/http/{HttpParser,HttpNormalization,StreamOutput}.{h,cpp} tests/{ProtocolTests,RuntimeTests,StreamingParserTests}.cpp
build-local/reviewer/v0.2-s1/evidence/DeadlineMatrix
build-local/reviewer/v0.2-s1/evidence/TotalDeadlineMatrix
build-local/reviewer/v0.2-s1/evidence/ParseOrderProbe
git diff --check
```

负控E/negative.log exit1；关闭探针E/close-window.log exit0、20次完整105字节、FAILURES 0 OF 20，原脚本SHA256 `158de752e714596bbdacf5e0e5c351d098d74239faf95d3b7f4d63ec8b58b425`保持。格式E/format.log exit0；人工复核ProxySession、TextRequest、HttpParser、Normalization、StreamOutput及三测试文件函数间空行、头分组、短转发/C外部接口例外，无新增Minor。

探针编译使用Reviewer Debug三静态库，`c++ -std=c++20 -g -I src -I tests -I third_party/llhttp/include <探针.cpp> <debug>/libgateway_runtime.a <debug>/libgateway_foundation.a <debug>/libllhttp.a -pthread -o <探针>`，E/*-build.log exit0。DeadlineMatrix exit1为真实产品失败；TotalDeadlineMatrix/ParseOrderProbe exit0。接缝改变仅在Reviewer副本，用于模拟recv/parse之间时间推进，不冒充真实网络计时分布；真实网络门控与sanitizer由完整CTests独立验证。未跑旧18cell矩阵或新增性能实验。

Builder首次Runtime资源探针失败原因已审读：停止后pollOnce立即返回，原固定次数并非等待TCP EOF；现有夹具使用有界poll客户端fd，仍检查EOF/终态零计数，没有修改产品或移除断言，本轮三套通过。独立新增失败全部保留，不能用完整11/11覆盖DeadlineMatrix反例。

## 6. 返工与交接

唯一必须修复项V02-S1-F-001，建议统一进入第1轮受限返工，保持原Approved行为及历史证据。Reviewer未修产品，未把缺陷改为债或扩大到V0.2/S2策略。复验须运行当前反例及新的精确边界回归，并验证发前发后语义、total和产品shutdown边界不回退。

当前无环境阻塞；已覆盖项证据如上。未接受的response完成期限缺陷使AC04/05不满足，不能关闭S1或创建“已验收”提交。后续Leader/协调者处理阶段状态与本地提交授权，禁止推送。
