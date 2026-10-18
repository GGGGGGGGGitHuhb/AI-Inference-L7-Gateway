# AI Inference L7 Gateway

面向在线文本推理服务的独立 C++ 七层网关项目，计划围绕流式代理、资源控制和请求调度建立可复现的工程实验。

**项目定位：独立项目、按需复用、最后联调。** Gateway 独立接收客户端请求；按需复用已有 HTTP Server、L4LB 的合适组件和工程经验；完成独立能力后，再验证与 L4LB 的组合部署。

## 当前状态

**V0.1/S1 协议与组件基础已完成**（2026-10-18，[Reviewer 独立复验 PASS](docs/reviewer/reports/V0.1/S1-report-002.md)、[Leader 收口](docs/leader/reports/V0.1/S1-report-004.md)）。累计返工 2 轮（第 2 轮仅纠正文档同步漏项），两项 HTTP 边界发现均关闭，无待接受债项。V0.1 整体仍未完成；尚无监听客户端的 Gateway 程序，不能启动完整代理链路，S2/S3 尚未开始。实现目前留在未提交工作区，未发布。

当前可验证：Buffer/Socket/TimerQueue，受限 HTTP/1.1 增量解析、正文与编码预算、文本 JSON SAX 校验、报文规范化，以及五场景模拟后端。SSE、异步上游连接、连接池和调度属于后续阶段。

## 构建与验证

环境：Linux、C++20 编译器、CMake >=3.24、Ninja、Python 3。Bash，工作目录为本仓库根目录。依赖已固定在 third_party，构建无需联网或同级项目。

```bash
mkdir -p build-local/builder/tmp build-local/builder/cache
export TMPDIR="$PWD/build-local/builder/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/cache"
cmake --preset debug
cmake --build --preset debug
ctest --preset debug --output-on-failure
```

Release 与 AddressSanitizer/UndefinedBehaviorSanitizer：将上述三个命令的 `debug` 分别换为 `release`、`asan`。每个预设注册 5 项 CTest；AssertionFailure 使用预期失败验证 Release 下检查仍有效。MockBackend 需要本机 loopback socket 权限，会自动申请临时端口并回收自己的子进程；权限不足即失败，不跳过。

独立审查使用 `cmake --preset debug -B build-local/reviewer/debug`（其他预设同理），随后通过 `cmake --build <目录>` 和 `ctest --test-dir <目录>` 操作；同时将 TMPDIR/TMP/TEMP/cache 指向 reviewer 自有目录。

格式检查（仅自有和迁入 C++，不处理 third_party）：

```bash
find src tests -type f \( -name '*.h' -o -name '*.cpp' \) -print0 | xargs -0 clang-format-18 --dry-run --Werror
```

测试使用合成输入，不需要 GPU、真实推理服务或 Python 第三方包。`tests/ParseResponse.cpp` 是将模拟器原始响应输入解析库的测试工具，不是网关产品入口。

## 计划解决的问题

- 代理 HTTP 推理请求，及时转发 SSE 响应。
- 在慢客户端、后端故障、取消和超时下维持资源边界。
- 在有限后端容量下，通过模型路由、准入和有界排队控制请求行为。
- 分别测量代理开销、流式稳定性和调度效果，避免仅用 QPS 表达系统能力。

## 与已有项目的关系

独立运行是主要交付路径：

```text
Client → AI Inference L7 Gateway → Inference Backends
```

后续联调路径：

```text
Client → L4LB TCP Proxy → Multiple Gateways → Inference Backends
```

- **HTTP Server：** 网络基础组件的复用候选，不要求作为运行链路中的独立服务。
- **L4LB：** 前期提供双向转发、背压等设计参考；后期可承担多个 Gateway 实例之间的 TCP 连接分发。
- **Gateway：** 独立承担 HTTP 代理、推理请求路由、流式生命周期及准入排队。
- **推理后端：** 执行模型计算。一个后端实例不预设对应一张 GPU。

Gateway 的构建和启动不应依赖同级 Server、L4LB 仓库的本地路径。S1 已按固定源码快照迁入最小组件，来源和差异见复用记录。

## 文档入口

- [架构大纲](ARCHITECTURE.md)：模块职责、所有权、请求流程、协议与资源边界。
- [分阶段开发路线](ROADMAP.md)：版本目标、阶段输出、验收条件和 MVP 边界。
- [V0.1/S1 设计](docs/leader/designs/V0.1/S1-design.md)：已选技术、协议子集、最小复用与实现验收基线。
- [V0.1/S1 审查计划](docs/reviewer/reviews/V0.1/S1-review.md)：独立验证方法及需求追溯。
- [S1 收口报告](docs/leader/reports/V0.1/S1-report-004.md)：阶段结论、验收范围和后续边界。
- [初始决策报告](docs/leader/reports/V0.1/S1-report-001.md)：规划时的选型依据和历史状态。
- [已验收变更](CHANGELOG.md)：Unreleased 阶段成果，不代表正式发布。
- [Approved 返工 001](docs/leader/reworks/rework-001.md)：状态范围与合法 chunk 扩展的适配权威。
- [Reviewer 复验报告](docs/reviewer/reports/V0.1/S1-report-002.md)：独立 PASS 及原始证据入口。

- [复用记录](docs/references/V0.1-S1-reuse.md)：固定来源与适配差异。
- [依赖清单](docs/references/V0.1-S1-dependencies.md)：版本、文件散列与许可证。
- [Builder 初次实现报告](docs/builder/reports/V0.1/S1-report-001.md)：初次命令、结果与证据。
- [Builder 返工报告](docs/builder/reports/V0.1/S1-report-002.md)：严格状态范围与有界 chunk 大小行前置适配、最新回归证据。

chunk 扩展先按完整原始大小行校验，再仅将大小与 CRLF 交给 llhttp；原始线缆/行预算和消费量保持独立计量。初次复用记录中的后置扩展校验描述属于旧实现，当前以 Approved 返工 001、Builder 002 和 Reviewer 002 的实现及验收说明为准。原设计/审查/返工中的阶段状态保留为历史快照，当前状态以本页、ROADMAP 和 Leader 004 为准。

尚未提供项目自身的 `LICENSE` 文件；third_party 内保留各依赖许可证。
