# 变更记录

仅记录已实现并验收的结果；未来计划见 [ROADMAP](ROADMAP.md)。

## Unreleased

### S2 单上游代理 — 已验收，未提交/推送

- 2026-10-18：新增独立非流式文本代理、静态IPv4配置、异步建连、硬限额、分类截止时间及信号停止；无连接池或SSE。
- 响应后写半关闭并有界读排空，修复额外输入跨关闭窗口丢首响应；关闭期间保留预约，绝对期限与停止优先级不变。
- [Reviewer S2-002](docs/reviewer/reports/V0.1/S2-report-002.md) PASS：三套独立7/7、原窗口20/20完整、正常/错误握手验证通过；两发现关闭。阶段收口见[Leader S2-003](docs/leader/reports/V0.1/S2-report-003.md)，累计1/2。
- 仅交付进程接口；事件外直接调用内部Runtime停止方法不属于立即清零保证，限制见ARCHITECTURE。没有接受契约内延期债务。
- V0.1整体仍待S3；S1已推送阶段分支，未合并main/正式发布。

### S1 收口历史记录


V0.1/S1 于 2026-10-18 验收完成，当前为未提交工作区成果；没有正式发布版本或标签，V0.1 整体尚未完成。

### Added

- 固定依赖的独立离线构建，以及 Debug、Release、ASan/UBSan 验证入口。
- 从 Server 固定提交迁入 Buffer、Socket、TimerQueue 及最小依赖，保存可复核来源和适配差异。
- 受限 HTTP/1.1 增量解析、容量预算、文本 JSON SAX 校验及报文规范化；不包含监听型 Gateway。
- 固定、分块、延迟、截断和畸形响应五场景模拟后端及自测。

### Fixed

- 拒绝超出 100—599 的上游状态；维持合法 1xx 和 101 的原契约。
- 支持合法 chunk 扩展 BWS：前置验证原始大小行，保留原始预算和消费偏移，严格拒绝畸形输入；第三方源码保持不变。

### Validation

- [Reviewer 002](docs/reviewer/reports/V0.1/S1-report-002.md)：PASS；独立 Debug/Release/ASan+UBSan 各 5/5 CTest，附独立协议探针，F-001/F-002 均关闭，无待处理债项。
- [Leader 收口](docs/leader/reports/V0.1/S1-report-003.md)：S1 已完成，累计返工 1 轮；S2/S3 未开始，无完整代理、SSE、GPU 或性能验收结论。

### 文档更正

- 2026-10-18：[Leader 004](docs/leader/reports/V0.1/S1-report-004.md) 纠正当前依赖验证与目录状态描述，累计返工更新为 2/2（第 2 轮仅文档）；上列 Leader 003 的 1 轮为当时记录。产品仍为 Reviewer 002 验收的同一实现，未新增功能或发布。

### 交付状态追加

- 2026-10-18：S1成果已提交为 `bb318d8c55f5851d27cd52e6cd3367f450a5d8dd`，并推送到 `origin/codex/v0.1-s1-foundation`（协调者远端核验）。上文“未提交”为收口当时记录；当前未合并main、未正式发布。S2仅设计获准，其计划不列为已完成变更。
