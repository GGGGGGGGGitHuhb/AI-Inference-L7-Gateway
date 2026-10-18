# V0.1/S1 返工 001：严格响应状态与 chunk 扩展适配

## 1. 状态、依据与范围

- 状态：`Approved`；日期：2026-10-18；批准人：Leader (Zeus)，在用户技术决策委托内采纳。
- 阶段状态：`返工中`；编排状态：`Reworking`；累计返工 **1/2**（初次实现不计）。本文件不构成验收。
- 用户授权：先“你来决策吧”，随后“可以，做吧”并显式调用 `orchestrate-olympus-stage`。本次纠正实现偏离，保持已承诺兼容面、接口、容量、依赖和阶段范围，无新增 PM 决策。
- 原基线：[Approved S1 设计](../designs/V0.1/S1-design.md)，SHA-256 `7a493854ce86bb27f7c1a6cf6ad98650035b48bb8173eeadff740d76911cf71f`；[Approved 审查计划](../../reviewer/reviews/V0.1/S1-review.md)，SHA-256 `fa247c50dfe5a8d8e8333c1d777ccfd46e71d841b655290fa22369bc12b9cd6f`。
- 触发：[Builder 001](../../builder/reports/V0.1/S1-report-001.md)、[Reviewer 001 FAIL](../../reviewer/reports/V0.1/S1-report-001.md) F-001/F-002。没有早期返工文件；不取代原设计，§5/§6/§7/§10 的 REQ-03/05、AC-03/05 在本文件明确其适配和回归要求，其余全部保留。
- 原设计中的“待实现/当前无返工”是规划时快照；当前阶段以本文件及 [Leader 002](../reports/V0.1/S1-report-002.md) 的返工状态为准，保留原文和散列。

## 2. 触发证据与决定

Reviewer 的独立三套 CTest 均 5/5，但额外探针发现：600/999 响应被交付为 Complete；合法 chunk 扩展 `1;foo = bar` 和 `1;foo="x" ;bar=y` 被拒绝。证据为 `build-local/reviewer/evidence/AcceptanceProbe.cpp` 和 `acceptance-probe.log`，每个单切分点重现。全绿的现有测试不能覆盖这两个缺陷。

源码核查显示 `parseBytes` 在每个原始字节上先运行 llhttp，`validChunkExtensions` 仅在 chunk-header 回调中执行，因此无法挽救库更早的拒绝。已有 `WirePhase::kChunkLine`、有界 `chunkLine_`、原始计数和 chunk 回调提供局部适配入口；无须换库或改第三方。

决定：**保留原契约，用有界的 chunk 大小行前置校验解决依赖差距。** 验证完整原始大小行后，仅将十六进制大小及 CRLF 投递给 llhttp；已校验的扩展按原契约忽略。llhttp 继续负责正文长度、chunk-data CRLF、终块、trailers 和消息结束。只在 chunk 大小行状态转换输入，不触碰普通头、正文或 trailer 字节。

这是受限适配器内的实现澄清，不是缩小兼容范围。不采用修改第三方生成源码、切换依赖版本、开启 lenient 或拒绝所有带 BWS 扩展的方案。可行性来自现有状态和接口的只读检查；修复正确性仍须 Builder 与独立 Reviewer 实测。

## 3. Builder 修正要求

### RW-01 / F-001：响应状态范围

在交付消息前检查响应状态范围 100—599。范围外统一 Rejected/502；不能进入规范化成功路径。合法未注册状态按原协议范围处理，不使用已知状态白名单。101 继续拒绝；其他合法 1xx 仍受次数/累计头预算约束并等待最终响应，不能把 100 当作最终完成。

增加 000、099、600、999，合法边界 100 后接最终响应、599，合法未注册最终状态，以及 101/1xx 原规则的测试。错误状态保持终止；reset 后不残留此前状态。

### RW-02 / F-002：有界前置语法校验

原始大小行完整且严格合法后才能生成提供给 llhttp 的内部大小行。输入须由一个以上十六进制数字开始，随后是合法扩展或 CRLF；不能容忍符号、0x 前缀、空大小、非十六进制字符或长度溢出。终块扩展适用相同语法。

扩展遵守 RFC 9112 §7.1.1，BWS 仅为语法允许位置的 SP/HTAB；名字是非空 token，值是非空 token 或合法 quoted-string（允许空引号值），正确区分 quoted-pair、引号内分号和引号外分隔。必须验证整个大小行，包括 CRLF；不能先 trim 整行或无条件删除空白。没有后续分号/等号可归属的尾随空白不能被洗白；裸 LF、CR 后非 LF、非法控制字节、缺失名字/值、未闭合引号/转义和非法后缀拒绝。对 obs-text 和 quoted-pair 按所引用的 RFC 9110 语法处理，不自行缩成 ASCII 白名单。

缓存未完成的大小行受既有上限约束，EOF 时未完成则拒绝。非终结块和终块分别正确进入 chunk-data/trailer 路径；不得新增第二套正文定界器，也不得重新解释 chunk 正文中的类似大小行字节。

### RW-03：原始计量、所有权和异常不变量

- 原始 wire 和 chunkLine 字节（含被忽略的扩展、空白、CRLF）只计一次，仍遵循所有默认预算及 limit−1/limit/limit+1。内部生成字节不得计入原始预算，也不得替代原始字节计量。
- `consumedBytes` 始终表示本次调用接收/消费的原始输入前缀。未完成大小行被缓存时也须准确报告；完成时不吞下一条消息。错误与超限的消费前缀须明确且在不同分片下累计一致，不能返回内部生成长度。
- 缓存大小行的所有权须跨调用稳定。向 llhttp 投递的字节不能在同步回调清空/重分配缓存时失效；避免持有 `chunkLine_` 视图后在回调清空它。必要时使用独立有界持有者，临时占用为 O(chunkLineBytes)，不复制整条报文。
- 不回放已经计入的原始字节；新增字段在 reset/error/EOF 路径一致清理。回调和适配分配失败不穿越 C/noexcept 边界，Rejected 后不继续解释数据。
- 若局部实现仍不能满足这些要求，报告具体差距，不能擅自减少兼容面或放宽预算。

### RW-04：范围与交接

Builder 所有权限于 `src/http/HttpParser.h/.cpp`、必要的 `src/http/` 私有辅助文件、相关协议测试和必要的测试注册，以及 README 当前状态/说明、Builder breakdown 和新报告 `docs/builder/reports/V0.1/S1-report-002.md`。优先保持现有公开接口和 CTest 入口，新增测试拆分由 Builder 决定。既有组件、JSON 契约、依赖快照、同级仓库、原权威与历史报告保持不变。不得引入 S2 代理功能。

产出两项发现及 RW-01—03 对应回归、变更文件与源码身份、实际格式化/检查记录及原始测试日志；遵循 personal-cpp-standards 的规则和正反例。所有自有受影响 C++ 实际运行 clang-format 18 格式化及检查。新日志独立命名，不覆盖初次失败证据。没有数据迁移、发布或新增敏感数据处理。

## 4. Reviewer 独立复验

1. 对 F-001 重跑原探针并独立补充状态边界/未注册合法状态；范围错误仍为 502，1xx/101 原规则保持。
2. 请求与响应两侧验证扩展：无值名字、token/quoted 值、等号两侧 BWS、分号前后 BWS、多扩展、引号内分号/空白、转义、终块扩展。正文和原始完成消费量应相同；请求 API 校验另使用合法 JSON 正文，不把 HTTP 接受等同 API 接受。
3. 验证非法名字/值/引号/转义/CTL、空大小、非十六进制/溢出、尾随裸空白、裸 LF/坏 CRLF、截断大小行以及 chunk-data CRLF 仍拒绝；不能因移除扩展把畸形行变合法。
4. 有效夹具整块、逐字节、每个单切分点及固定种子分片，特别覆盖 BWS、引号、转义、CRLF；拼接下一条消息验证尾部不吞。非法夹具至少对每个单切分点验证拒绝分类和累计消费前缀一致。
5. 含大量扩展的原始大小行/总 wire 上限 limit−1/limit/limit+1；删除扩展后内部行虽短，原始超限仍须拒绝。验证零块、多个数据块、chunk 数、正文预算、reset、EOF 和适配缓存分配异常。
6. 使用独立 Reviewer 目录重新配置/构建/执行 Debug、Release、ASan+UBSan 的完整 CTest；保持 mock 网络联动、来源/manifest、格式检查和 Release 负断言证据。原探针可以编译到新输出路径，不能覆盖旧失败日志。

原 AC-01—07、RV-01—07 仍全部有效。任一未修复发现或新增定界/预算/生命周期问题均不能通过；环境阻止必要测试则 BLOCKED。Reviewer 独立给出新报告 `docs/reviewer/reports/V0.1/S1-report-002.md`，本文件不预判 PASS。验收之后才由 Leader 同步路线、阶段与适用发布/债务记录。

## 5. 执行路线和停止边界

沿用 WSL2 `/bin/bash`、login=false，根目录 `/home/power/projects/AI-Inference-L7-Gateway`，分支 `codex/v0.1-s1-foundation`，HEAD `62d10e0a0c4348cea7cc23761f4b91a762839f0f`，保留所有既有未提交内容。角色各用 `build-local/<role>/{tmp,cache,evidence}` 并显式设置 TMPDIR/TMP/TEMP/XDG_CACHE_HOME；Reviewer 使用独立构建和进程状态。同级仓库只读，正常构建不联网；已知 loopback Socket 权限边界按窄范围执行，不先重复沙箱失败。

本次为第 **1** 轮统一修正；包含 Leader 澄清→Builder 修正→Reviewer 复验，不另加一轮。若之后再需修正，只剩第 2 轮；第三轮开始前必须按 Olympus 停止，不以换角色/编号重置。没有提交、推送、标签授权，不开始后续阶段。

## 6. 技术依据

2026-10-18 核对 [RFC 9112 §7.1—7.1.1](https://www.rfc-editor.org/rfc/rfc9112.html#section-7.1.1) 的大小行/扩展语法，以及 [RFC 9110 §15](https://www.rfc-editor.org/rfc/rfc9110.html#section-15) 的状态范围；quoted-string/token 依照 [RFC 9110 §5.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.6)。本项目支持面仍以原设计子集为界，不声称完整 RFC 兼容。
