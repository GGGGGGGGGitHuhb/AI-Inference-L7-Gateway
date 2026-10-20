# V0.2/S3 Builder 交付纠正报告002

2026-10-19；第1轮受限交付纠正，累计 **1/2**，等待独立Reviewer。本轮依据协调者的唯一计数纠正要求，Approved设计/审查、产品、测试、固定资产均不变；保留报告001原字节与全部历史证据。

报告001审计段及初次handoff误写二进制清单33项，正确为 **36项**。实际`binaries-final-sha256.json`从始至终包含36项，原`protected-audit.json`的binary_files也已经是36；不是新增3个产物或修复缺失hash。

| 构建模式 | 可执行文件 | 静态库 | 合计 |
| --- | --- | --- | --- |
| Debug | 9 | 3 | 12 |
| Release | 9 | 3 | 12 |
| ASan+UBSan | 9 | 3 | 12 |
| 合计 | 27 | 9 | 36 |

每模式9个可执行文件是ai-inference-gateway、IntegrationRuntimeHost、StreamingParserTests、ParseResponse、FoundationTests、ProtocolTests、BackpressureTests、RuntimeTests、PoolTests；3个静态库是libgateway_foundation.a、libgateway_runtime.a、libllhttp.a。

误记原因：写报告时沿用未经重新计数的旧“30项”口径，加三个模式的新host得出33；实际原有每模式11项，新增host后12项。虽然此前逐项hash验证通过，人工报告没有从机器清单读取长度，造成计数陈述不一致。本轮以机器清单实际键数与分类为准，不再由旧计数推算。

在原生WSL、bash login=false及原Builder角色tmp/cache环境下，用Python读取清单、按模式/后缀分类，并逐项重算SHA256：36项全部匹配。另核对64项源码身份全部匹配，原保护审计100项口径不变。36是产物数量，三模式各13个CTest是测试入口数量，不应相互换算；没有发现其他计数需要更正。此次没有重跑构建、CTest、探针或长run，完整复用001中的已执行证据。

更新当前breakdown的36项和累计1/2；新增原始证据`build-local/builder/v0.2-s3/evidence/r1-count-audit.json`，不覆盖旧manifest或审计。报告001保留作为历史，当前正确口径由本002补充。无产品/测试/Approved修改，无commit/push；本轮到此停止，交协调者核对。
