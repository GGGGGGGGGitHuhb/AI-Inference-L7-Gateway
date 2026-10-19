# V0.1/S2 Reviewer 独立审查报告 001

日期：2026-10-18。角色：Reviewer (Athena)。**结论：FAIL**。这是 S2 初次审查，交接时累计返工 **0/2**；S1 已完成及历史 2/2 不变。本报告不修改产品、批准基线、历史报告或阶段状态。

## 结论与建议

独立 Debug、Release、ASan+UBSan 完整 CTest 均 **7/7 通过**，网关可实际启动并完成非流式代理。但独立复现确认：额外输入跨越关闭窗口时，第一条合法请求的响应仍可能全部丢失。调整测试后端从 120ms 延迟到 400ms 只避开了该窗口，不能证明原契约成立。另有新写 C++ 的函数间空行违反明确规范。

发现：**S2-F-001 Major**（关闭时序与首响应完整性）、**S2-F-002 Minor**（代码排版规范）。没有发现可直接接受的债项，不使用 PASS WITH DEBT。

建议先交 Leader (Zeus) 处理 S2 §5 立即全关闭与额外数据不损害首请求的行为矛盾，明确有界关闭阶段及其截止、计数、停止与取消规则；保持“不派发第二请求”的范围。随后将两个发现作为一次合并修正，Builder 修复、Reviewer 独立复验。不能只移动测试时间窗口、降低响应断言或把丢响应描述为已经验证的正常行为。

## 输入、身份与独立路线

读取用户 AGENTS 指令；当前仓库无项目角色指南，使用 plan-project-docs 的 Reviewer 模板回退。执行前重读 agent-execution-route；沿用完整 personal-cpp-standards 与正反例。读取 Approved S2-design、S2-review、Leader S2-report-001、Builder S2-report-001、README、根架构/路线当前 S2 边界及 S2 复用清单；历史 S1 仅作为已验收前置，不继续 S1 工作。

批准基线实测 SHA-256：

- design：`a8d0206472e85bbb8facc5ba668c1aa4964803f48d7737cca659855aafc9de51`
- review：`c8ad195e1c0a75155f91912179dc92bcd9187bf281329a063ef49b733a63c471`

分支 `codex/v0.1-s2-proxy`；HEAD `bb318d8c55f5851d27cd52e6cd3367f450a5d8dd`，S2 为未提交工作区。源码、测试、第三方、配置身份见 `build-local/reviewer/s2/evidence/source-sha256.txt`。无提交、推送、标签；本轮未改兄弟仓库。

路线为 WSL 原生 `/bin/bash`、login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`；Reviewer 独立 `build-local/reviewer/s2/{debug,release,asan,tmp,cache,evidence}`，构建/脚本显式 TMPDIR/TMP/TEMP/XDG_CACHE_HOME。没有复用 Builder 的可变构建、端口、进程或临时配置；Builder 初次失败与最后通过日志只读。已知 socket/LSan ptrace 边界直接用精确测试命令窄范围升级，不跳过。无下载和全局安装。

## 实际审阅范围

完整阅读 S2 产品新增实现及头：GatewayConfig、SignalSource、main、GatewayRuntime、ProxySession、SessionIo、EventLoop、Channel、Epoller；审阅 HTTP 规范化的 close 参数变更。审阅 RuntimeTests、GatewayE2E_test、ProxyBackend、CMake 注册及 README 启动方式。S1 未改的解析、JSON、Buffer/Socket/TimerQueue 沿用已验收语义，并通过本轮完整回归。

- 固定来源六文件从 Server 指定提交 git show 提取并重算 source/target SHA-256，全部匹配；另两项 HTTP 规范化来源从 Gateway 的 S1 提交取源。`provenance.log` 保留结果，`source-*.h/.cpp` 为 Reviewer 独立源快照。比较事件实现：主要为命名空间、格式/无效 friend 适配，epoll_wait EINTR 改为空批次以重算截止时间，与记录一致。
- Channel 只观察 FD；事件使用单调 token 查表，注销使旧事件失效。finishSession 只注销/关闭/取消，Channel 存活到 callback 返回后的 cleanup。timer callback 执行时对应任务节点由 TimerQueue 持有，清理会话不销毁正在执行的 Channel 回调。未发现此路径 UAF/重复释放。
- config 在监听前验证，重复键 guard、深度/大小、整数与布尔区分、IPv4/self endpoint、端口/额度/timeout 范围；main 配置错误 2、运行失败 1、信号停止 0。日志为固定摘要，无原文/凭据路径。
- 上游先验证请求再新建，SO_ERROR 检查、读写并行、短写偏移与 OUT 兴趣、MSG_NOSIGNAL、FIN/RST 分离均存在。大小预算与 deadline 由真实代码执行，接缝仅在测试实现，无产品注入开关。
- 终结与清理计数有单一所有者；stop 关闭监听并保留有界排空，第二信号强制。正常关闭路径的可见响应保证存在 S2-F-001，不能用内部计数归零代替客户端收到完整消息。

## 独立执行与证据

日志根均为 `build-local/reviewer/s2/evidence/`。配置、构建三种预设：

```bash
export TMPDIR="$PWD/build-local/reviewer/s2/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/reviewer/s2/cache"
cmake --preset "$variant" -B "build-local/reviewer/s2/$variant"
cmake --build "build-local/reviewer/s2/$variant" -j 2
ctest --test-dir "build-local/reviewer/s2/$variant" --verbose
```

每种 configure/build/test 均退出 0；对应 `<variant>-configure.log`、`<variant>-build.log`、`<variant>-test.log`。CTest 为独立编译、独立进程的当前测试；检查数只是证据索引，不视为覆盖证明。

| 检查 | 实际结果 |
| --- | --- |
| Debug 全套 | 7/7；Runtime 121、Gateway E2E 400、Foundation 33、Protocol 76,848 |
| Release 全套 | 同上 7/7 |
| ASan/UBSan 全套 | 同上 7/7；无 sanitizer 报告 |
| 其余三项 CTest | 预期失败断言、MockBackend 五场景、Manifest 均通过 |
| Release 直接负断言 | `FoundationTests --intentional-failure` 退出 1，`negative.log` |
| 格式工具 | 全部 src/tests C++ 的 clang-format-18 dry-run Werror 退出 0，`format.log`；人工规范检查仍发现 F-002 |
| diff 空白 | `git diff --check` 退出 0，不覆盖人工职责/函数间空行规则 |
| 来源清单 | 八项源/目标逐项 SHA-256 匹配，`provenance.log` |
| README 原示例 | 使用 Reviewer debug 二进制与 `config/example.json`，实际 READY 127.0.0.1:8080，SIGTERM 后退出 0，`readme-smoke.log` |
| 新独立关闭窗口探针 | 20 次中 1 次首响应为空，退出 1，`CloseWindow.py` / `close-window.log` |

Debug 请求接收 timeout 实测 0.07063s（配置 70ms），shutdown 实测 0.06075s（配置 60ms）；Release/ASan 对应日志也在约 0.071—0.072s / 0.061—0.068s。它们只验证该场景，没有推导服务性能。

## REQ/AC/RV 对照

| 项目 | 独立观察与判定 |
| --- | --- |
| 01 来源/事件安全 | 六固定源及两规范化变更可复核；实际 fd 复用、旧 token、同批删除另一 Channel、回调后清理、timer 取消/到期、token 耗尽的测试均独立运行，通过 |
| 02 配置/启动 | config 正负矩阵和 64KiB 边界、数值上下界、重复键、CLI、端口0、bind失败、help、READY；代码验证在监听/访问上游前发生，通过 |
| 03 完整代理 | 真实固定/chunked/EOF/1xx/204/304/400/500/471/599/分片、早期413、坏请求无上游、Expect417、Host/CL/Via/close/认证、原JSON字节等均通过；**额外输入跨关闭时首响应丢失，未通过** |
| 04 IO/生命周期 | EINTR/短写/EAGAIN/恢复、SO_ERROR、SHUT_WR、RST、bad_alloc、deadline竞争及计数/FD基线通过现有测试；独立关闭探针暴露可见响应丢失，不能整体接受关闭行为 |
| 05 资源/公平 | N−1/N/N+1、双门槛、最大正文/慢读与热连接时另一请求408通过；逻辑预算推导见下；当前 hot 测试未覆盖闭窗，首请求保证受 F-001 阻塞 |
| 06 deadline/停止 | 接缝逐项 request/connect/write/response/total/downstream 和错误排空，真实拒连、request/response/total、SIGTERM正常/强制/第二信号通过；新增关闭阶段若修改须由 Leader 明确其截止与 shutdown 优先级并复验 |
| 07 工程/文档 | 三套完整回归、README启动、来源、manifest和格式工具证据可复现；F-002 人工规范未满足，且 F-001 未关闭，阶段不可标完成 |

罕见系统调用验证来自独立构建运行的 FakeIo 接缝，已阅读其触发参数与断言：它不等价于内核实际发生这些 syscall 返回。真实 loopback E2E 独立证明产品链路，两者分别报告。最小 connect timeout 依赖确定性时钟/连接接缝，没有以黑洞路由替代。

### 单会话存储与公平性的独立判定

已追踪对象寿命与字符串持有：requestParser 完成/JSON返回后规范化输出，请求解析器在连接前释放；请求输出发送完释放；responseParser 完整后生成独立输出并释放解析器/请求输出。最坏早期响应期间同时有约 1MiB+64KiB 请求输出、4MiB 响应正文、4MiB+64KiB 响应输出，另有受 16KiB 头/1KiB chunk/16KiB scratch 等约束的临时内容；保守 1MiB 余量后 10.125MiB，低于 16MiB。

JSON SAX 无 DOM，1MiB 原输入限制字符串/键副本总内容；字段数/深度/条目上限约束结构元数据。未发现将整个 4MiB 响应再复制第三份的隐式路径。checkOutputBudget 在生成规范化输出前按头/正文安全减法检查；输入增长由 S1 预算约束。16MiB 是逻辑存储预约，不覆盖 allocator capacity、内核缓冲和进程 RSS。没有据此宣称 RSS 上限。

预约在会话/解析器构造前执行，失败回滚，cleanup 一次扣除；每事件 accept32、每方向64KiB/64次调用避免无界处理。上述有限处理有利公平性，却不能代替正常关闭时避免 TCP reset 的机制。

## 发现

### S2-F-001 — Major：额外输入跨关闭窗口可能抹掉第一条合法响应

- 关联：REQ/AC/RV-03、04、05，S2-design §5 “额外数据不取消第一条完整合法请求”与 E2E 完整收到要求；S2-review §3 第一请求与后续额外数据规则。
- 位置：`src/gateway/ProxySession.cpp:382` 的 writeDownstream 成功后立即 finishSession；`ProxySession.cpp:47` 注销并直接 reset 下游 Socket；readDownstream 每事件只有限丢弃输入，没有正常输出后的半关闭/有界读排空阶段。`tests/GatewayE2E_test.py` hot 场景将后端延迟改为400ms，而热发送150ms，因此回避该关闭窗口。
- 独立复现：

```bash
python3 build-local/reviewer/s2/evidence/CloseWindow.py \
  build-local/reviewer/s2/debug/ai-inference-gateway
```

  全部使用自有临时端口/配置/后端线程及 Reviewer 二进制。客户端先发送合法 JSON，等待后端完整收到，再在150ms内持续发送可丢弃额外输入；后端120ms后返回固定 `200` + `abc`。客户端停止发送后读取至 EOF，过程中没有主动 RST/close；程序 finally 终止并等待自己的进程/线程。
- 期望：首响应完整，额外输入不派发、不缓存，也不使首响应丢失。
- 实际：20次中第9次（日志索引8）收到 **0字节**；其余19次收到完整105字节。失败次 accepted_extra=6,104,000，send 报 BrokenPipeError，随后 read 为 EOF；后端线程无错误。独立探针退出1。不是仅复述 Builder 失败记录。
- 解释与证据边界：源码明确立即全关闭。该行为与 [RFC 9112 §9.6](https://www.rfc-editor.org/rfc/rfc9112.html#section-9.6) 描述的“关闭后额外数据引发 reset、客户端尚未消费的响应可能丢失”一致；本轮没有抓包，**不把具体内核包序列声称为已观测事实**。已观测的首响应丢失本身足以否定当前 E2E 保证。
- 影响：后端已完成推理，客户端仍可能无响应；现阶段又不允许自动重试，不能用普通断线概括为已满足首请求契约。不是 UAF 或内存破坏，因此 Major。
- 返工要求：Leader 明确正常响应/错误响应完成后有界关闭策略及资源保留、deadline、shutdown/取消优先级，解决设计 §5 “送入内核后关闭”与不丢首响应的冲突。可采用先 SHUT_WR 再有限读排空等方式，但具体方案由 Leader 决策；不可无界等待客户端，不可在此引入第二请求处理/连接池。恢复覆盖响应完成前、同时、后仍有额外写入的回归，明确握手/时限，保持完整首响应、一次上游、其他请求和计时器进展。只延后后端或删掉响应断言不接受。

### S2-F-002 — Minor：新写 C++ 未遵守明确的函数间空行要求

- 关联：REQ/AC/RV-07、设计 §9、personal-cpp-standards “.cpp 相邻函数定义之间保留一个空行，包括构造/析构”。
- 位置示例：`src/gateway/ProxySession.cpp:34` 后立即为析构，35后立即 startSession，41后立即 closeUpstream；GatewayRuntime.cpp、GatewayConfig.cpp、SignalSource.cpp、SessionIo.cpp 以及 RuntimeTests.cpp 也存在相同连续定义。
- 期望：对本阶段新增/修改范围实际格式化后，人工复核并补齐函数边界与职责分组。
- 实际：clang-format dry-run 通过，但默认 Google 配置不会自动补齐缺少的空行。Builder 的格式工具结果真实，不能替代技能要求的人工检查。
- 影响：违反明确个人规范，降低较长状态机代码可读性；不改变运行时结果。
- 要求：限定本阶段自有代码补齐相邻函数空行及对应声明/成员职责分组，保留语义/断言，重新运行格式工具和必要检查。无需改动第三方或重排旧阶段全仓。此项随 F-001 合并修正，不自行转为债务。

## 未验证、残余风险与交接

没有做真实 GPU、性能、连接池、SSE、多后端或 L4 联调，它们不在 S2；没有将模拟或接缝结果冒充这些能力。HTTP 协议穷举与所有内核调度组合也未验证。shutdown/超时实测仅代表所列有限场景。

初次全绿 CTest 与新增反例并存，必须保留两者。Builder 披露旧窗口失败的行为是诚实证据；其“可能是RST”的解释有协议依据，但不能据此将未满足的请求保证关闭。README/ROADMAP 最终状态由 Leader 处理，Reviewer 未标完成。

当前无 Reviewer 自有后台构建、CTest、网关、探针线程继续运行；所有新证据独立保留。交回协调者及 Leader，S2 保持未完成，初次审查 FAIL；后续修正按 Olympus 累计计数，不能用新报告号重置。
