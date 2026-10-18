# V0.1/S1 Reviewer 独立审查报告 001

日期：2026-10-18。角色：Reviewer (Athena)。结论：**FAIL**。初次独立审查；交接时累计返工 0。本报告不修改批准基线、产品代码或阶段生命周期，不批准技术债。

## 结论与交接

独立 Debug、Release、ASan/UBSan 构建成功，三套现有 CTest 均 5/5 通过。组件来源、格式检查和正常/异常测试证据可复现。但独立补充探针暴露两个 HTTP 契约问题（F-001、F-002），AC-03 尚不能通过；不能因原有测试全绿关闭阶段。

建议将两项合并处置。F-001 是原批准范围内修复；F-002 涉及 llhttp 严格模式的实际兼容边界，先交 Leader 决定在原契约内适配或创建明确的修订基线，不能由 Builder/Reviewer 静默删掉支持要求或开启宽松模式。修复后补产品回归测试并再次独立审查。README 保持待审查/返工的真实状态；ROADMAP、ARCHITECTURE 和阶段状态最终同步由 Leader 负责。

## 输入与独立性

读取用户 AGENTS 指令；仓库及父目录未发现额外 AGENTS.md，项目无 Reviewer 指南，按要求回退至个人 `plan-project-docs/references/role-guides/reviewer-guide-template.md`。已读取 `agent-execution-route`、`personal-cpp-standards` 及完整正反例。

已读 Approved `docs/leader/designs/V0.1/S1-design.md`、Approved `docs/reviewer/reviews/V0.1/S1-review.md`、ARCHITECTURE、ROADMAP、README、Leader S1-report-001、Builder S1-report-001 与 S1-breakdown、依赖与复用说明及 JSON 清单。无前次 Reviewer 报告或批准返工。

两份批准文件 SHA-256 与交接一致：

- design：`7a493854ce86bb27f7c1a6cf6ad98650035b48bb8173eeadff740d76911cf71f`
- review：`fa247c50dfe5a8d8e8333c1d777ccfd46e71d841b655290fa22369bc12b9cd6f`

分支 `codex/v0.1-s1-foundation`，HEAD `62d10e0a0c4348cea7cc23761f4b91a762839f0f`；实现未提交。实际实现身份见 `build-local/reviewer/evidence/worktree-sha256.txt`，包含自有代码、测试、第三方快照。没有 commit/push，未修改兄弟仓库。独立读取固定来源七文件，源/目标散列全部吻合；来源七文件相对固定提交当前无差异。无法仅凭本轮状态证明其他角色过去所有文件操作，未作此泛化声明。

使用原生 WSL2、`/bin/bash`、login=false，仓库根目录工作。独立目录为 `build-local/reviewer/{tmp,cache,evidence,debug,release,asan}`；TMPDIR/TMP/TEMP 和 XDG_CACHE_HOME 均指向 Reviewer 自有目录。未使用 Builder 的可变构建、模拟进程或测试临时目录。只读其证据及仓库内第三方源码。

工具：GCC 13.3.0、CMake 3.28.3、Ninja 1.11.1、clang-format 18.1.3、Python 3.12.3；原始输出和 Git 状态见 `environment.log`。

## 执行与结果

以下证据路径均相对于 `build-local/reviewer/evidence/`。初始化并导出临时目录后，对 debug/release/asan 分别执行：

```bash
cmake --preset "$variant" -B "build-local/reviewer/$variant"
cmake --build "build-local/reviewer/$variant" -j 2
ctest --test-dir "build-local/reviewer/$variant" --verbose
```

所有 configure/build 退出 0，日志为 `<variant>-configure.log`、`<variant>-build.log`。初始批次测试在沙箱中因 `socket(AF_INET, SOCK_STREAM): Operation not permitted` 失败（退出 8），保留 `<variant>-test.log`。这是执行环境限制；同批其余构建继续执行。识别后对完整三套 CTest 使用一次窄范围升级，结果保留 `<variant>-test-authorized.log`，各退出 0。未跳过必需网络测试或修改断言。

| 独立检查 | 结果与证据 |
| --- | --- |
| Debug CTest | 5/5；33 Foundation、4567 Protocol 检查；授权测试日志 |
| Release CTest | 5/5，同样检查数量；授权测试日志 |
| ASan/UBSan CTest | 5/5，无 sanitizer 诊断；授权测试日志 |
| 模拟后端 | 三配置均 fixed/chunked/delayed/truncated/malformed 五场景；原始响应交给 C++，每个进程退出且原临时端口拒绝连接 |
| 断言反例 | `build-local/reviewer/release/FoundationTests --intentional-failure` 退出 1，`negative.log`；Release 检查没有被 NDEBUG 移除 |
| 格式 | `find src tests -type f \( -name '*.h' -o -name '*.cpp' \) -print0 \| xargs -0 clang-format-18 --dry-run --Werror`，实际管道执行退出 0，`format.log`；人工检查命名、声明/定义、回调与状态分组 |
| 差异空白 | `git diff --check` 退出 0；自有未跟踪 C++ 另由格式检查覆盖 |
| 来源 | Python 对七项执行 `git -C /home/power/projects/HP-HTTP-Server show <commit>:<source>` 并重算源/目标 SHA-256，全部匹配，`provenance.log` |
| 依赖 | 三套 Manifest 测试逐文件匹配；固定 URL、版本宏、MIT 文件、CMake 本地源码路径一致，没有构建期 FetchContent/下载或兄弟路径依赖 |
| 独立反例 | `AcceptanceProbe.cpp` 编译成功；执行退出 1，`acceptance-probe.log`，下述两项重现 |

独立探针的实际编译/运行：

```bash
c++ -std=c++20 -Isrc -Ithird_party/llhttp/include \
  build-local/reviewer/evidence/AcceptanceProbe.cpp \
  build-local/reviewer/debug/libgateway_foundation.a \
  build-local/reviewer/debug/libllhttp.a \
  -o build-local/reviewer/evidence/AcceptanceProbe
build-local/reviewer/evidence/AcceptanceProbe
```

另有探索探针 `Probe.cpp` / `probe.log`：obs-fold 确认拒绝，204/304 相关无正文行为按定界优先级检查。探索输入不是全部被认定为缺陷；本报告仅把下述明确基线差距作为返工项。

## 逐项审查

- **RV-01 / AC-01：通过。** 三套独立离线构建、CTest 非零失败和 Release 负断言均有实测。未重新下载官方文件；本轮独立校验固定 manifest 和现存源码，而非重新证明下载传输过程。
- **RV-02 / AC-02：通过。** 阅读 Buffer/Socket/TimerQueue/NonCopyable 全部迁入实现与固定原始 Buffer/Timer 代码，散列校验覆盖七文件。适配记录与命名差异一致。容量、移动/关闭、重排/取消、cutoff、回调中新建及异常恢复验证通过。Buffer 借用视图失效遵守调用契约，未通过故意悬空访问来测试。
- **RV-03 / AC-03：失败。** 已有 CL/chunked/EOF、1xx/204/304、重复 CL/Host、TE+CL、逐跳字段、尾随消息消费量测试通过；独立探针发现状态范围与合法 chunk 扩展兼容差距，见 F-001/F-002。
- **RV-04 / AC-04：通过当前覆盖。** 逐项阅读 TextSax 和字段测试；根/作用域重复键、metadata 所有权、字符串类型、数字限制、UTF-8、未知字段、深度和项数按输入有界处理。保留原始正文，未建立完整 DOM；normalizeMessage 仅接受已解析且已做 API 校验的消息，此前提已在复用说明记录。
- **RV-05 / AC-05：通过当前覆盖。** 默认/收紧预算 limit−1/limit/limit+1 覆盖起始行、每组头、字段数、1xx 次数/累计头、请求/响应体及 wire、chunk 行/数、JSON 深度/项数。llhttp settings 与实例生命周期固定，禁止移动；所有 C trampoline catch(...)；fault injection、reset/error/EOF 与 sanitizer 均执行。此项不消除 AC-03 的语义缺陷。
- **RV-06 / AC-06：通过。** 独立 loopback 临时端口、进程超时和 finally 回收，原始响应和记录来自合成输入，五场景结果可重复；代码仅清理创建的子进程。
- **RV-07 / AC-07：证据基本齐全，阶段尚不能关闭。** README 的 Reviewer 等价入口实际执行；Builder 格式/哈希/测试记录与本轮复现一致。没有完整代理、SSE 或路由提前实现；旧规划状态应在最终 Leader 同步，Reviewer 未擅改。

## 发现与返工要求

### F-001 — Major：非法响应状态码被作为合法最终消息交付

- 关联：REQ-03 / AC-03 / RV-03；设计 §5 最终状态仅在协议合法时保留，§6 响应协议错误映射 502。
- 位置：`src/http/HttpParser.cpp:277`，handleHeadersComplete 只校验版本和 101，没有校验 response status 范围；handleMessageComplete 随后返回 Complete。
- 输入：`HTTP/1.1 600 Invalid\r\nContent-Length: 0\r\n\r\n`；999 同样重现。
- 预期：Rejected / 502；合法范围为 100—599，参见 [RFC 9110 §15](https://www.rfc-editor.org/rfc/rfc9110.html#section-15)。
- 实际：Complete，statusCode=600/999，无错误；每个输入全部 44 个单切分点均不满足预期，`acceptance-probe.log`。
- 影响：异常后端状态进入可规范化转发路径，违反严格响应契约。不是已证明的内存安全漏洞，因此定为 Major。
- 要求：在适配层验证完整范围，增加低于 100、高于 599 及合法边界/合法未注册状态的回归；非法结果保持终止，reset 后可复用。不要把未知但处于合法范围内的状态一律拒绝。

### F-002 — Major：已承诺的 chunk 扩展语法无法接收合法 BWS

- 关联：REQ-03 / AC-03 / RV-03；设计 §6 的 chunked 扩展“仅校验语法并忽略”，且没有排除该语法中的 BWS。
- 位置：`src/http/HttpParser.cpp:141` parseBytes 直接逐字节送入 llhttp；`validChunkExtensions` 在 chunk header 完成后才运行，不能修复底层更早的拒绝。
- 输入：`HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1;foo = bar\r\nx\r\n0\r\n\r\n`；另一个为 `1;foo="x" ;bar=y`。
- 预期：Complete，body=`x`，消费量精确；[RFC 9112 §7.1.1](https://www.rfc-editor.org/rfc/rfc9112.html#section-7.1.1) 的扩展语法含等号前后和分号前的 BWS。
- 实际：Rejected / invalid_http；两个输入分别在全部 69、74 个单切分点失败。对照 `1;foo=bar` 所有切分点通过。原始证据 `acceptance-probe.log`，不涉及网络条件。
- 影响：当前实现支持面窄于批准协议矩阵；正常 chunk 扩展可能被误判为上游错误。
- 要求：Leader 先确认处置，因为固定依赖/严格模式与承诺兼容范围存在实际能力差距。在原契约下安全适配需保留原始预算、精确消费量、畸形拒绝和任意分片；如果缩小范围，必须通过批准的修订记录明示限制并同步测试，不能只改报告。不得直接修改第三方生成源码或开启 lenient 作为隐式修复。

## 限制与残余风险

- 独立验证不含完整代理、真实 GPU、性能、并发进程总内存、SSE 和连接池；这些不在 S1。
- 本轮没有做穷举 HTTP 语法/fuzz；全绿的 4567 检查不能推出完整 RFC 兼容。
- 每字节调用 llhttp 有性能成本，但基线允许且未承诺吞吐，不作为缺陷；后续优化必须保留定界/预算测试。
- 两个 Major 尚未解决，没有可自行接受的债项。当前无 Reviewer 自有构建/测试进程继续运行。阶段保持未完成，由协调者按工作流交接。
