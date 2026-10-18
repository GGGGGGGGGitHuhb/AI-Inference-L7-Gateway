# V0.1/S1 Builder 返工报告 002

日期：2026-10-18。角色：Builder (Hephaestus)。累计返工 **1/2**。本轮修正和自测已完成，交 Reviewer 独立复验；不宣称验收或阶段完成。

## 输入与范围

依据 Approved [返工 001](../../../leader/reworks/rework-001.md)、原 Approved [S1 设计](../../../leader/designs/V0.1/S1-design.md)及[审查计划](../../../reviewer/reviews/V0.1/S1-review.md)，读取 Leader 002、Reviewer 001 的 F-001/F-002，以及 Builder 001。继续使用 agent-execution-route、personal-cpp-standards 完整规则及正反例、通用 Builder guide 回退。

本次仅修改 `src/http/HttpParser.h/.cpp`、`tests/ProtocolTests.cpp`、README 当前说明、Builder breakdown 和本新报告。没有修改 JSON、复用组件、第三方、原权威或历史报告，也未修改兄弟仓库、引入 S2 能力。

分支 `codex/v0.1-s1-foundation`；HEAD `62d10e0a0c4348cea7cc23761f4b91a762839f0f`。保留已有脏工作区，无 commit/push/tag。

## 修正与不变量

| 项目 | 实现 | 回归 |
| --- | --- | --- |
| RW-01 / F-001 | response header-complete 检查 100—599；范围外 Rejected/502；继续拒绝 101；不使用注册状态白名单 | 000/099/600/999 所有单切分点；599、299、471；100 后最终响应；101；仅 100 后 EOF；错误终止和 reset |
| RW-02 / F-002 | 在 WirePhase::kChunkLine 缓存完整原始行，严格验证 hex、扩展、BWS、token/quoted-string、quoted-pair/obs-text 和 CRLF；验证后只向 llhttp 投递规范化 hex+CRLF | 请求/响应、有值/无值、多扩展、等号/分号 BWS、空引号、分号/转义/obs-text、零块；非法语法/CTL/溢出/尾部裸空白/EOF 全切分拒绝 |
| RW-03 | raw wire/line 只在接收处计数；内部编码在独立 18 字节栈数组，不参与预算；llhttp 继续承担正文、data CRLF、终块和 trailers | 原默认容量边界全回归；新有扩展 line/wire limit−1/limit/limit+1；正文含类似 chunk 行；多数据块；逐字节/随机/全单切分；两报文边界；前置缓存 bad_alloc |
| RW-04 | 仅授权范围，新增独立 r1 日志和本报告 | 完整 Debug/Release/asan CTest；格式化、hash、manifest、mock、负断言 |

大小行校验不会 trim 整行；尾部空白只有后续分号或等号的语法归属成立时才被消费。`decodeChunkLine` 检验完整原始行，`validateExtensions`、`consumeQuotedString` 分离连贯职责；不另写正文定界器。

`deliverByte` 使用独立栈持有者，避免 llhttp 同步回调影响内部输入视图。chunkLine 缓存仅在原始行状态累积，有界且跨调用拥有存储；成功投递或拒绝清空，reset 清空所有相关状态。原始字节不重放、不再次计量。

`consumedBytes` 是本次接收的原始输入前缀。已缓存的未完成行计入消费量；完整非法行含触发校验的 LF；预算拒绝和缓存分配失败不计入尚未成功接收的该字节。跨所有单切分累计消费量与整块输入一致。Rejected 后输入消费为零；可显式 reset 后重新解析。内部生成长度不对调用者暴露。

回调继续 catch(...)；前置缓存分配异常由 parseBytes 的 catch 转为 internal_error，request=500、response=502；无异常跨 C 或 noexcept 边界。内部行编码不动态分配。未改 lenient 模式或第三方源码。

## 执行路线与实际命令

原生 WSL2 `/bin/bash`、login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`；沿用 GCC 13.3.0、CMake 3.28.3、Ninja 1.11.1、clang-format 18.1.3、Python 3.12.3。

本轮 Python/构建/测试前均显式设置：

```bash
export TMPDIR="$PWD/build-local/builder/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/cache"
```

没有下载或包安装。完整 CTest 含已知 loopback/socket 权限边界，直接沿用窄范围升级执行，未重复沙箱失败或跳过网络测试。Reviewer 的原探针源只读，重新链接到 Builder 的库与独立输出；不使用其可变构建状态。

```bash
clang-format-18 -i src/http/HttpParser.h src/http/HttpParser.cpp tests/ProtocolTests.cpp
clang-format-18 --dry-run --Werror src/http/HttpParser.h src/http/HttpParser.cpp tests/ProtocolTests.cpp
find src tests -type f \( -name '*.h' -o -name '*.cpp' \) -print0 | xargs -0 clang-format-18 --dry-run --Werror

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

git diff --check
```

三套 configure/build/test 均退出 0；单独故意失败退出 1（预期）；格式检查和 diff 检查退出 0。人工检查新增辅助函数、函数分隔和内部独立存储的寿命。未格式化第三方。

原 Reviewer 探针复跑：

```bash
c++ -std=c++20 -Isrc -Ithird_party/llhttp/include \
  build-local/reviewer/evidence/AcceptanceProbe.cpp \
  build-local/builder/debug/libgateway_foundation.a \
  build-local/builder/debug/libllhttp.a \
  -o build-local/builder/evidence/r1-AcceptanceProbe
build-local/builder/evidence/r1-AcceptanceProbe
```

编译、运行退出 0；扩展三个对照的 failed splits 均为 0。**原探针存在显示缺陷：状态行固定输出 `wire.size()+1` 作为 failures across splits，因此恒显示 44，不是实际失败计数。** 源码真正的 failures 参与退出码判定，本轮退出 0；另外新增的状态全切分产品测试已通过。不修改原探针或其历史日志、不把固定显示的 44 隐藏为成功数据。

## 结果与证据

证据根 `build-local/builder/evidence/`，所有本轮日志以 `r1-` 开头；001 的源码散列、通过/失败日志均保留。

- `r1-debug-configure.log` / `r1-debug-build.log` / `r1-debug-test.log`。
- `r1-release-configure.log` / `r1-release-build.log` / `r1-release-test.log`。
- `r1-asan-configure.log` / `r1-asan-build.log` / `r1-asan-test.log`。
- `r1-format-check.log` / `r1-format-all.log` / `r1-diff-check.log`。
- `r1-release-negative.log` / `r1-acceptance-probe.log`。
- `r1-worktree-sha256.txt`：本轮源码、测试和权威身份。

三套 CTest **各 5/5**；每套 Foundation **33** 检查、Protocol **76,848** 检查。MockBackend 五场景的原始响应/退出/监听回收全部通过；Manifest 未变化且逐文件一致；AssertionFailure 维持预期失败。ASan/UBSan 没有诊断。未把测试时间当作性能结果。

新增测试为 `testResponseStatusRework`、`testChunkExtensionsRework`、`testChunkAdapterBudgets`，复用 splitFixture 的整块、逐字节、全部单切分点、种子 20261018 随机分片及双报文检查。新增 rejectedSplits 比较非法输入全部单切分点的状态、错误码和累计原始消费量。原全部 REQ/AC 测试仍保留，没有删除或削弱断言。

源码 SHA-256：

- HttpParser.h：`edf18e42d60f7ea06980f35102cffde58c2ce0c687300f5094abf510882ac3ec`
- HttpParser.cpp：`0b8e6f5a32f2aac4b7cb9d74c98f219e5a462e79e2c47b5872d55063c41306eb`
- ProtocolTests.cpp：`2567738b26c80b9d16a75d236b0dd0b955e41335511abb220c193007b0f84bfa`
- Approved rework-001：`657b0734bdc0208713ef9c366bcfbb46e654aaf02860344465cda1caf2623e86`

原 design/review 与 manifest 散列保持 001 所记值；机器清单已再次记录。

## 未完成与交接重点

本轮授权的两项修正及自测已完成，尚待 Reviewer 独立验收；F-001/F-002 的正式关闭由 Reviewer 判定。没有新延期项、发布或 PM 决策请求。Leader 保留生命周期和路线同步职责。

原复用说明关于后置扩展校验的段落是初次实现快照；RW-04 未授权修改该记录，因此 README 已明确指向本轮前置适配说明，未擅改来源文档。请 Reviewer 重点独立检查合法 BWS 与非法尾空白的区分、原始消费前缀、zero chunk/EOF、栈输入与同步回调寿命、异常路径及全套预算；使用独立 reviewer 构建/临时目录。累计返工仍 1/2，不因报告编号或 Leader 澄清重置。
