# 变更记录

仅记录已实现并验收的结果；未来计划见 [ROADMAP](ROADMAP.md)。

## Unreleased

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
