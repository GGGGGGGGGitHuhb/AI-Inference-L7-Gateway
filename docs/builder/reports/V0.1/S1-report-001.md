# V0.1/S1 Builder 实现报告 001

日期：2026-10-18。角色：Builder (Hephaestus)。本次为初次实现，累计返工 0；状态：实现与自测完成，交独立 Reviewer。未宣称阶段通过或完成。

## 依据、范围和结果

读取 Approved [S1 设计](../../../leader/designs/V0.1/S1-design.md)、Approved [审查计划](../../../reviewer/reviews/V0.1/S1-review.md)、ARCHITECTURE、ROADMAP 及 Leader S1-report-001。没有已批准返工或先前 Builder/Reviewer 报告。项目没有角色指南，使用 plan-project-docs 的 Builder 模板回退；读取 agent-execution-route 和完整 personal-cpp-standards 正反例。保留既有未提交规划文件，不修改 Leader/Reviewer 权威。

预期交付独立可构建的协议、组件和模拟器基础；实际已实现全部 S1 模块，并通过 Debug、Release、ASan/UBSan 自测。没有实现监听型 Gateway、上游连接器、连接池、SSE、路由、队列或性能基准。

当前分支 `codex/v0.1-s1-foundation`；HEAD 仍为 `62d10e0a0c4348cea7cc23761f4b91a762839f0f`。未提交、推送或打标签。未修改 Server/L4LB。

## 文件与实现

| 范围 | 目的 |
| --- | --- |
| CMakeLists.txt、CMakePresets.json、.clang-format、.gitignore | 离线固定源码构建；Debug/Release/asan；CTest；Google/clang-format 18；隔离构建产物。preset schema 5 与 CMake 3.24 最低版本对应 |
| third_party/llhttp、third_party/nlohmann、manifest.json | 官方固定标签源码与许可证，逐文件真实 SHA-256；正常构建没有 FetchContent/网络步骤 |
| src/base、src/net、src/timer | 七个来源文件的最小迁入，强制 Buffer 显式预算，命名和排版适配 |
| src/http/HttpParser.h/.cpp | 单消息增量定界、完整消费量、头/正文/线缆/chunk/1xx 预算、错误映射、EOF/reset、C 异常边界 |
| src/http/HttpNormalization.h/.cpp | 去逐跳头和客户端认证、重建 Host/CL、追加 Via、保留普通重复头和原始正文、错误响应及 Allow |
| src/gateway/TextRequest.h/.cpp | SAX 文本 API 子集验证，作用域重复键、深度/项数预算、有限元数据提取，不构造 prompt DOM |
| tests/FoundationTests.cpp、ProtocolTests.cpp、TestSupport.h | 不依赖 NDEBUG 的断言、组件边界、协议矩阵、分片、容量、生命周期、分配异常 |
| tests/support/MockInferenceBackend.py、MockBackend_test.py、ParseResponse.cpp | loopback 临时端口，固定/分块/延迟/截断/畸形响应，原始响应输入 C++ 解析器，进程/监听回收 |
| tests/Manifest_test.py | 固定依赖逐文件 SHA-256 校验 |
| README、docs/references、Builder breakdown/report | 真实入口、来源差异、许可范围与交接证据 |

完整文件清单/工作区 hash：`build-local/builder/evidence/worktree-sha256.txt`。这些证据是 gitignored 本地原始产物，保留供同工作区 Reviewer 读取；不会随 Git 发布自动携带。

## 关键语义与初次实现发现

- llhttp 9.4.3 未启用任何 lenient 开关，但首轮负例发现 `1;=x` 被底层接受。自有适配层新增有界扩展语法校验，原始失败保留于 `debug-test-initial.log`；第三方生成源码未改。
- 每字节喂入 llhttp，完成时暂停；消息尾部留给调用者。代价是调用开销较高，当前未作吞吐声明，未来优化须保留本阶段语义测试。
- 起始行预算计量实际起始行，前导空行仍计入整组头部预算，不能绕过起始行上限。
- 204/304 不产生正文；规范化不输出 CL。304 来自表示长度的 CL 不充当正文长度。EOF 定界响应显式标记 eofDelimited，不作为可复用连接依据。
- 原始 JSON 正文保留；合法 API 的自然深度最多 3。默认深度 31/32/33 和项数 8191/8192/8193 测试以未知字段载入嵌套结构，区分未超预算的 unsupported_field 与超预算 invalid_request；另用合法 API 收紧预算验证接受边界。
- C trampoline 捕获所有异常，失败状态不再分配；测试覆盖回调中 bad_alloc 后 Rejected、销毁和 reset 重用。
- 使用 migrate 源语义，不修改原仓库。完整来源提交和每文件原始/目标散列见 `docs/references/V0.1-S1-reuse.json`。

## 执行路线与命令

原生 WSL2 Linux 6.6.87.2，显式 `/bin/bash`、`login=false`；工作目录 `/home/power/projects/AI-Inference-L7-Gateway`。工具为 GCC 13.3.0、CMake 3.28.3、Ninja 1.11.1、clang-format 18.1.3、Python 3.12.3。版本原始输出 `environment.log`。

初始化：

```bash
mkdir -p build-local/builder/tmp build-local/builder/cache build-local/builder/evidence
export TMPDIR="$PWD/build-local/builder/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/cache"
```

下载使用 `curl -fL --max-time 60 <manifest中对应URL> -o <对应path>`，7 个固定文件均完成；无全局安装。Git 分支写入因当前 `.git` 只读沙箱限制首次失败，随后仅对 `git switch -c codex/v0.1-s1-foundation` 窄范围升级成功，保留原有文件。固定下载及本机 socket CTest 按边界窄范围执行，未改全局设置。

一条仅修改文档的 Python 命令未显式重复导出临时目录变量；它仅读写仓库文件、未启动测试/包管理或生成外部临时文件，随后命令恢复显式变量。所有构建与动态验证使用 Builder 临时/缓存目录；Reviewer 应使用自己的目录。

实际构建与测试：

```bash
cmake --preset debug
cmake --build --preset debug
ctest --preset debug --verbose
cmake --preset release
cmake --build --preset release
ctest --preset release --verbose
cmake --preset asan
cmake --build --preset asan
ctest --preset asan --verbose
build-local/builder/release/FoundationTests --intentional-failure
```

配置和构建成功，最终 CTest 三套均退出 0。单独的故意断言失败命令退出 1（预期）。ASan 使用 address,undefined、frame pointer 和非 PIE；最终运行未出现 sanitizer 报告。没有将权限失败跳过为通过。

实际排版与检查：

```bash
find src tests -type f \( -name '*.h' -o -name '*.cpp' \) -print0 | xargs -0 clang-format-18 -i
find src tests -type f \( -name '*.h' -o -name '*.cpp' \) -print0 | xargs -0 clang-format-18 --dry-run --Werror
git diff --check
```

两项检查退出 0；覆盖文件在 `format-files.txt`，版本/结果为 `format-version.log`、`format-check.log`。人工检查函数边界、类内接口/成员分组、回调名称与短转发 lambda；第三方 C/头文件未格式化。

## 验证结果及追溯

证据根：`build-local/builder/evidence/`。

| REQ / AC | 执行证据 | 结果 |
| --- | --- | --- |
| 01 | debug/release/asan-configure-final.log、对应 build-final.log、Manifest | 本地快照独立构建，无兄弟仓库或下载依赖；逐文件 hash 匹配 |
| 02 | Foundation，reuse.json | 每套 33 检查；Buffer 上限、compact、move、非法 commit/consume、release；FD move/reset/release/close；Timer 取消/重排/cutoff/回调中新建与取消/异常恢复 |
| 03 | Protocol，testFraming/testFieldTypes/testNormalization | 固定 CL、chunked、EOF、204/304、1xx、TE+CL/Host/Trailer/Upgrade/Expect/CRLF 等拒绝矩阵；合法定界夹具整块、逐字节、所有单切分点及固定随机种子 20261018；双报文消费边界 |
| 04 | Protocol，testJson/testFieldTypes | 字段类型、缺省、允许值/边界；256 字节 model、256 messages；非法 UTF-8/重复键/尾部/注释；原始正文与元数据 |
| 05 | Protocol，testBudgets/testDefaultBudgets/testLifecycle，asan | 所有预算可收紧的 limit−1/limit/limit+1，实际默认边界；100 次 reset/EOF；bad_alloc 不跨 C；ASan/UBSan 无报告 |
| 06 | MockBackend | 每套五种场景通过；C++ 收到原始响应；每个子进程退出并核验原临时端口拒绝连接；无固定端口/共享可变状态 |
| 07 | README、format-check.log、diff-check.log、来源/依赖清单、本报告 | 构建/测试入口与实际执行一致；没有宣称完整 Gateway 或独立验收 |

最终原始日志：

- `debug-test-final.log`：5/5 CTest，33 Foundation + 4567 Protocol 检查，2.54 秒。
- `release-test-final.log`：5/5 CTest，相同检查，0.66 秒。
- `asan-test-final.log`：5/5 CTest，相同检查，11.72 秒。
- `release-assertion-negative.log`：主动失败断言，退出 1。

上述耗时只是测试执行观测，不是性能验收。CTest 的五项为 Foundation、Protocol、AssertionFailure（预期失败）、MockBackend、Manifest；三个 C++ 可执行文件。

依赖 manifest SHA-256：`3b01e222e3191ef27a661c0ed1833782ff8887cb193fc8db371d5e36dfcaee51`。
复用清单 SHA-256：`d5c980736aca0738e7a5b23c00649dda1433b670d1dd984cbc3aa54d159d048c`。
本轮读取的 Approved 设计 SHA-256：`7a493854ce86bb27f7c1a6cf6ad98650035b48bb8173eeadff740d76911cf71f`；审查计划：`fa247c50dfe5a8d8e8333c1d777ccfd46e71d841b655290fa22369bc12b9cd6f`。

## 未完成、风险与 Reviewer 重点

S1 授权范围内未发现需延期项；独立验证和 Leader 收口尚未执行。ROADMAP/设计中的阶段状态由 Leader 同步，本报告不擅自修改生命周期。未作协议性能或进程级并发内存声明，预算只针对单解析器。

请 Reviewer 优先独立复核：逐字节完成偏移、chunk 扩展边界、头/1xx/chunk 总预算交互、JSON 容量和类型优先级、回调分配失败、304/EOF 规范化，以及模拟器失败路径的子进程回收。使用 `build-local/reviewer/{tmp,cache,debug,release,asan}`，不复用 Builder 可变构建/进程状态。
