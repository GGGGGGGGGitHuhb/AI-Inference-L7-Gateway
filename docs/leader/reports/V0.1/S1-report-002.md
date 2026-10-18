# V0.1/S1 Leader 返工决策报告 002

日期：2026-10-18。角色：Leader (Zeus)。本次为第 1/2 轮返工的权威澄清；不作实现或独立验收。

## 第一部分：PM 决策摘要

**当前结论：At Risk，可以继续修正。** S1 初次独立审查 FAIL，阶段为返工中。已有组件与协议基础以及三套测试证据，但两个协议边界尚未达标，不能关闭阶段。

**计划与实际：** Builder 和 Reviewer 的 Debug/Release/ASan+UBSan 现有测试均通过；Reviewer 另外发现非法响应状态被接受、合法分块扩展空白被拒绝。已形成 Approved [返工 001](../../reworks/rework-001.md)，将两个问题合并为一次修正，保留已有兼容范围和质量门槛。

**决定与取舍：** 在自有解析适配层补状态检查，并先校验有界分块大小行，再交现有解析库处理正文。无需换库或改第三方；需要补测原始字节计量、分片和异常路径。这是有限范围的兼容修复，尚未实测，交付需等再次独立审查。重大范围、成本或安全风险接受：None；进度风险为必要返工增加一轮，未承诺具体工期。

**PM 决策：None。** 依据用户“你来决策吧”及随后“可以，做吧”并调用 Olympus 的明确授权，由 Leader 作常规技术决定；不降低验收要求，不授权发布或后续阶段。

**下一步：** Builder (Hephaestus) 按返工 001 完成两项修复和回归证据；Reviewer (Athena) 独立复验；只有验收后 Leader 才收口。累计返工 1/2，禁止在第三轮修正开始后再补报停止。

## 第二部分：详细工作记录

本部分供 PM 按需查阅，为角色交接与审计记录。

### 权威与输入

读取当前用户 AGENTS 规则、agent-execution-route、personal-cpp-standards 完整正反例、plan-project-docs 及 rework-guide。项目无本地 AGENTS/角色指南，使用 `plan-project-docs/references/role-guides/leader-guide-template.md` 回退，含 Project-Owner Relationship and Decision Support 与 Leader Work Report 两节。

读取 ARCHITECTURE、ROADMAP、Approved S1 设计及审查计划、Leader/Builder/Reviewer 各 001 报告；当前没有技术债台账，也没有先前返工。两个发现是当前验收缺陷，不转为延期债务。历史规划中“待实现”等是当时快照，当前执行状态以本报告和返工 001 为准；本轮不重写原基线及历史报告。根文档最终状态同步留待独立验收后的 Leader closeout。

复核原设计 SHA-256 `7a493854ce86bb27f7c1a6cf6ad98650035b48bb8173eeadff740d76911cf71f`、审查计划 SHA-256 `fa247c50dfe5a8d8e8333c1d777ccfd46e71d841b655290fa22369bc12b9cd6f`，与交接相同。返工文件明确补充实现约束而不替换它们。用户执行许可为本轮会话中“可以，做吧”与显式技能调用，不把旧设计报告虚构为新增用户批准。

### 证据与技术判定

阅读 `src/http/HttpParser.h/.cpp`、相关协议测试、Reviewer 探针日志和 llhttp 生成状态机相关位置。F-001 的 header-complete 路径无 100—599 范围检查；F-002 的当前后置校验位置晚于底层拒绝。`acceptance-probe.log` 对 600/999 各 44 个切分失败，两项 BWS 扩展各 69/74 个切分失败，对照无 BWS 扩展通过。

选择前置有界大小行校验，是因为现有适配器已有 chunk-line 状态、缓存、字节计数和回调，不需替换正文定界机制。验证后忽略扩展符合原已批准行为；仅对库输入重编码，原始消费偏移与容量独立计量。详细约束见返工 RW-01—04，避免复制技术基线。

未选缩小兼容面：会使原合法输入被拒绝，不能仅为消除 FAIL 改验收。未选宽松开关或第三方修改：与原依赖、严格模式边界相冲突。前置校验需防止把畸形行修成合法行、同步回调使缓存视图失效，以及忽略扩展后低估原始预算；这些是强制回归项，不是已接受风险。

依照 [RFC 9112 扩展语法](https://www.rfc-editor.org/rfc/rfc9112.html#section-7.1.1) 和 [RFC 9110 状态范围](https://www.rfc-editor.org/rfc/rfc9110.html#section-15) 核对判定。设计可行性来自只读代码检查，本轮没有重新构建、运行探针或声称修复已验证；动态结果均归属已引用 Reviewer 报告。

### 交接与完成条件

新增 `docs/leader/reworks/rework-001.md`（Approved）与本报告；本轮不修改产品代码、测试或历史权威。Builder 下一报告 002，Reviewer 下一报告 002；同一轮累计计数 1 不因 Leader 澄清增加或重置。所有旧失败和初次实现证据保留，修正日志用新名字。

Builder 范围为解析适配/必要私有辅助、协议回归及必要注册、README 当前状态和 Builder 文档。Reviewer 除重跑原独立探针，还需验证请求/响应合法和非法扩展、全切分、原始 wire/行预算及异常，并独立重跑三套完整测试。原来源和其他功能的通过证据不豁免本轮回归。完整代理、SSE、连接池仍不在范围。

执行路线复用原生 WSL2、`/bin/bash`、login=false、仓库绝对路径；实测分支 `codex/v0.1-s1-foundation`，HEAD `62d10e0a0c4348cea7cc23761f4b91a762839f0f`。Leader 使用 `build-local/leader/{tmp,cache,evidence}`；脚本前显式设置临时/缓存变量。没有网络 Socket 或构建需求；只读外部规范。Builder/Reviewer 各自目录与构建状态独立，loopback 权限限制是已知边界。

保留脏工作区，未提交/推送/打标签，未修改兄弟仓库。当前阶段未完成，F-001/F-002 在下一次独立验收前仍为未关闭；无待 PM 批准事项。协调者可立即交 Builder 继续第 1 轮返工。
