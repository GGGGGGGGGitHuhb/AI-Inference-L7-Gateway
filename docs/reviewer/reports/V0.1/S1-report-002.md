# V0.1/S1 Reviewer 第 1 轮返工复验报告 002

日期：2026-10-18。角色：Reviewer (Athena)。**结论：PASS。** 累计返工 **1/2**；F-001、F-002 均经独立复验关闭。无新增阻塞发现、无须接受的延期债项。此结论仅验收 S1 协议与组件基础；最终阶段、路线和发布状态由 Leader 同步。

## 依据与独立性

沿用用户 AGENTS、agent-execution-route、personal-cpp-standards 完整规则和正反例；无项目 Reviewer 指南，继续使用 plan-project-docs 的 Reviewer 模板回退。复用前轮已读规则，不另立标准。

本次读取 Approved 原 S1-design、S1-review、Approved `docs/leader/reworks/rework-001.md`、Leader 002、Builder 002 和 Reviewer 001；保留原报告与原始失败证据。Approved 三文件实测 SHA-256 见 `build-local/reviewer/evidence/r1-authority-sha256.txt`：

- 原设计：`7a493854ce86bb27f7c1a6cf6ad98650035b48bb8173eeadff740d76911cf71f`
- 原审查计划：`fa247c50dfe5a8d8e8333c1d777ccfd46e71d841b655290fa22369bc12b9cd6f`
- 返工 001：`657b0734bdc0208713ef9c366bcfbb46e654aaf02860344465cda1caf2623e86`

当前分支 `codex/v0.1-s1-foundation`，HEAD `62d10e0a0c4348cea7cc23761f4b91a762839f0f`；产品仍为未提交工作区。相对 Reviewer 001 的完整源码/测试/第三方散列快照，仅 HttpParser.h、HttpParser.cpp、ProtocolTests.cpp 改变，见 `r1-scope.log`；其余组件、JSON 和第三方内容保持一致。本轮身份见 `r1-worktree-sha256.txt`。重新核对七项复用原提交源/目标散列全部匹配。没有修改产品、第三方、兄弟仓库或生命周期文件，没有 commit/push/tag。

执行路线：原生 WSL2、`/bin/bash`、login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`；沿用 Reviewer 自有 `build-local/reviewer/{debug,release,asan,tmp,cache,evidence}`。所有脚本/构建/测试显式设置 TMPDIR/TMP/TEMP/XDG_CACHE_HOME 指向 Reviewer 目录；未使用 Builder 的可变构建、测试进程或临时状态。工具版本与 001 相同。

## 独立代码检查

完整阅读当前 HttpParser.h/.cpp 的新增逻辑、状态转换、tests/ProtocolTests.cpp 新增回归、Builder 002 证据以及 README 的状态说明。

- 响应头完成时检查 100—599；仍拒绝 101，非 101 的 1xx 按原规则等待最终响应，不引入注册状态白名单。
- 原始大小行只在 `kChunkLine` 收集；收到 LF 后完整验证 CRLF、十六进制范围及扩展。token、quoted-string、quoted-pair、obs-text、BWS 分别检查，不能依靠 trim 或无条件删空白修正非法输入。
- `from_chars` 拒绝范围溢出；uint64 的规范大小行使用独立 18 字节栈数组（16 hex + CRLF），同步 llhttp 回调不会使该输入失效。无整报文额外复制或新增正文定界器。
- 原始字节在 accountByte 只记一次；内部生成大小行不经过原始计量。未完成行的消费量使用原输入前缀；超过预算或缓存分配失败的触发字节不计入返回消费量。拒绝后终止；reset 清理状态，EOF 不把未完整行判成功。
- llhttp 继续处理 chunk data CRLF、末块、trailer 和消息完成。头、正文和 trailer 不经过扩展适配；第三方未修改、没有启用 lenient。
- 新增具名辅助函数与异常边界符合个人 C++ 规范；产品原有 C trampoline 的异常捕获保持。

## 执行命令与结果

本节日志均在 `build-local/reviewer/evidence/`，使用 `r1-` 新名称；未覆盖 001 证据。

对 debug/release/asan 分别执行：

```bash
export TMPDIR="$PWD/build-local/reviewer/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/reviewer/cache"
cmake --preset "$variant" -B "build-local/reviewer/$variant"
cmake --build "build-local/reviewer/$variant" -j 2
ctest --test-dir "build-local/reviewer/$variant" --verbose
```

configure/build 在沙箱内执行；CTest 含已知 socket 边界，直接使用窄范围升级，没有重复此前 EPERM。三套全部退出 0。

| 独立执行 | 结果 | 原始证据 |
| --- | --- | --- |
| Debug | 5/5 CTest；33 Foundation、76,848 Protocol 检查 | r1-debug-configure/build/test.log |
| Release | 5/5；相同检查数 | r1-release-configure/build/test.log |
| ASan + UBSan | 5/5；无 sanitizer 诊断 | r1-asan-configure/build/test.log |
| MockBackend | 每套 fixed/chunked/delayed/truncated/malformed 均通过；进程退出，临时端口监听关闭 | 三套 test.log |
| Manifest | 三套逐文件 SHA-256 全匹配 | 三套 test.log |
| Release 负断言 | `build-local/reviewer/release/FoundationTests --intentional-failure` 退出 1，符合预期 | r1-negative.log |
| 全部自有 C++ 格式 | `find src tests -type f \( -name '*.h' -o -name '*.cpp' \) -print0` 交给 `xargs -0 clang-format-18 --dry-run --Werror`，退出 0 | r1-format.log |
| 空白检查 | `git diff --check` 退出 0 | r1-diff-check.log |
| 原 Reviewer 探针重链接 | 执行退出 0；显示缺陷见下节 | r1-original-acceptance-probe.log |
| 新独立探针 | 877,219 项断言通过，另遍历全部 1,000 个三位状态码；实际失败数 0 | r1-independent-probe.log |
| 新独立探针 ASan/UBSan | 同样通过，无 sanitizer 诊断 | r1-independent-probe-asan-authorized.log |

原探针只读重用 `AcceptanceProbe.cpp`，链接本轮 Reviewer debug 静态库，输出二进制为 `r1-original-acceptance-probe`。新探针独立编写为 `R1IndependentProbe.cpp`，链接命令如下：

```bash
c++ -std=c++20 -Isrc -Ithird_party/llhttp/include \
  build-local/reviewer/evidence/R1IndependentProbe.cpp \
  build-local/reviewer/debug/libgateway_foundation.a \
  build-local/reviewer/debug/libllhttp.a \
  -o build-local/reviewer/evidence/r1-independent-probe
build-local/reviewer/evidence/r1-independent-probe
```

Sanitizer 版本使用同一独立源码，链接 Reviewer asan 两个静态库，增加 `-fsanitize=address,undefined -fno-omit-frame-pointer -fno-pie -no-pie`，输出 `r1-independent-probe-asan`。

该额外探针首次在沙箱结束时遇到 LeakSanitizer 的 ptrace 限制（退出 1），证据 `r1-independent-probe-asan.log`；未关闭 leak detection 或删除断言。随后仅对同一二进制作一次窄范围升级，退出 0，完整输出与无诊断结果在 `r1-independent-probe-asan-authorized.log`。这是新增运行路径的环境限制及纠正，不是产品修正或新增返工轮次。

## 原探针显示问题与旧证据澄清

Builder 指出的显示问题属实：旧 `AcceptanceProbe.cpp` 状态行把 `wire.size()+1` 固定输出为 `failures across splits`，因此即使实际失败数为零也打印 44。实际 failures 变量参与程序退出码；扩展的 failedSplits 是真实计数。旧日志和探针不改写。

001 的状态缺陷结论还由独立 `Probe.cpp` 的实际 Complete/statusCode=600 以及当时产品无范围检查共同支持；但旧日志的字面 44 不能单独视为实际失败计数。新 `R1IndependentProbe.cpp` 遍历 000—999，独立统计非法状态被接受数与合法状态被拒绝数，均为 **0**，消除显示歧义；新增产品回归另外检查非法状态各单切分点及 reset。

## 返工 §4 逐项验收与发现关闭

1. **状态范围：通过，F-001 关闭。** 独立全部 000—999 值覆盖、原探针通过；产品回归验证 000/099/600/999 各切分拒绝 502、599 和未注册合法状态、100 后最终状态、101、仅 100 后 EOF、错误终止及 reset。
2. **合法扩展：通过，F-002 关闭。** 新探针在请求和响应侧逐字节/全单切分验证 BWS、多扩展、quoted 和 quoted-pair；全部 256 字节分别放入 quoted、escaped、token 位置，用独立语法判定接受/拒绝。产品回归还含空值引号、无值名字、分号、obs-text、终块扩展、多个块及固定种子分片。独立合法 JSON chunk 请求验证 API 接受，正文原样保留。
3. **非法扩展和大小行：通过。** 非法控制字节、名字/值/引号、转义、符号/0x/空大小/非 hex/数值溢出、尾随空白、裸 LF/坏 CRLF/EOF 均拒绝。完整 CTest 包含 chunk-data CRLF 和非空 trailers 拒绝，未因前置适配放松原规则。
4. **分片与消费量：通过。** 独立探针对正反输入的每个单切分，核对状态、错误码、累计原始前缀与整块一致；逐字节结果一致。合法输入拼接下一报文后消费量仍只到本条边界。产品回归另覆盖固定随机种子 20261018。
5. **预算/异常：通过。** 全套原默认容量边界继续执行；新增含扩展的 chunkLine 和 raw wire limit−1/limit/limit+1、完整行与缓存前缀、body/chunk 数、终块/多块/EOF/reset、前置缓存 bad_alloc 均通过。独立探针另对含扩展原始 wire 边界全切分检查，不能用缩短后的内部行绕过预算。ASan/UBSan 的产品与独立探针无诊断。
6. **完整回归与证据：通过。** 三套独立 CTest、模拟器、来源/manifest、格式和负断言证据齐全。未改变原 AC/RV 或兼容边界。

原 AC/RV 总结：AC-01/RV-01 独立构建依赖、AC-02/RV-02 复用所有权、AC-03/RV-03 HTTP、AC-04/RV-04 JSON、AC-05/RV-05 预算生命周期、AC-06/RV-06 模拟器、AC-07/RV-07 交接范围均通过。未改变的模块由本轮完整回归、内容身份及前轮语义检查共同支撑；没有把 Builder 自测当作独立验收。

## 风险、限制与下一步

没有新增 Major/Blocker，也没有自行接受的技术债。已测试集合不能证明完整 RFC 兼容或所有资源故障；S1 仍是受限协议基础，不含完整 Gateway、SSE、上游池、GPU 或性能验收。逐字节解析成本仍属后续测量范围。

初次复用说明中后置校验段落明确由 README 指向 Approved 返工及当前实现；它是历史实现记录，未作为当前验收依据。Leader 收口应同步 README/ROADMAP/架构中的当前进展与报告链接，保留历史权威和失败证据，不把 S1 完成写成 V0.1 代理完成。

推荐协调者进入 **Closing**，交 Leader (Zeus) 同步阶段状态和最终报告。Reviewer 自有构建、CTest、额外探针均已退出，无继续运行工作；累计返工保持 1/2。
