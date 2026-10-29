# V0.6/S1 Builder 006：完整矩阵与收口交接

2026-10-29。依据 Approved S1 设计、返工001–003、冻结v4及末两诊断安排。Builder已完成72/72正式cell与全部12个diagnostic，待Reviewer独立采集与Leader验收；不自行宣告S1 PASS或S2入口成立。本报告更新当前状态，001–005及其原始失败、未执行计划快照保持历史原貌。

## 实施与证据完整性

新增标准库asyncio有界容量设施，保留逐ID计划/时钟/正文摘要、全部失败分母、L4日志守恒、资源窗口及累计预算。未修改产品C++、旧测试工具或L4工作树。独立Release构建完成，既有产品CTest 21/21通过；最终工具自测17/17通过，均有原日志，本次收口没有重复运行测试。

最终清单SHA256：`a559456acd9851c51a14b877fcfb42bdfe829c144bd4c61efdf71ebc245fe692`。原72项仅各采一次：前33项使用批准r4派生复审，后39项原始结果；未重发早先失败cell。三次首停分别为多词L4关闭原因解析、无细节的退出期资源读取错误、已定位但立即poll尚null的退出期PermissionError。原result和failed ledger不改，派生记录绑定原输入、二进制、清单链与工具哈希。

返工003仅允许自有子进程PermissionError在实际时间已到formal_end且阶段为窗口外时，无信号等待不超过100ms及剩余cell期限；取得实际退出码才跳过，窗口内、控制器、存活或超时仍fatal。最终续采39项未遇新首错，两个退出确认等待分别1.161025ms、1.427208ms，均记录exit0。第33项85.246%真实达标率未被错误修正抹掉。

证据根 `build-local/builder/v0.6-s1/evidence/`：

- `run/formal-summary-builder-complete.json`：72项含repeat、全部outcomes、P95/P99、CPU/资源、来源hash；SHA256 `c3cf8830e74f3ef097d2164a31abbe21aeb35085b7278138de7d0504b10fdb6e`。
- `run/formal-reaudit-r4/summary.json`：批准33项派生与取证；SHA256 `bbf09176eca32a4d72658d6356a7c15b10723676b3a3b525b89f62c43c0f6253`。
- `source-final.json`：与source-before内容完全相同，两仓实际源码/dirty diff、两Release二进制未变；SHA256 `b39ab65263183ef6f2d695f93176e3e65c37f41346d11a2e23aa02c50a12799a`。
- `builder-closure.json`、`final-diagnostic-budget.json`、`final-diagnostics.log`：累计额度、进程收口与末两单变量控制。

## Builder有限窗口结果

每点预热3s、正式20s、三重复；下游新TCP，上游reuse=false，聚合cap32/slots128/stream4MiB。A双generator、S单generator；M/L均分配置额度。SLO从scheduled到完整HTTP framing解析观测，成功还需随后EOF和正文校验；不是模型token延迟。所有正式cell生成器门槛通过、观察到正文/协议损坏0。

| 路径 | A最高三重复通过档 req/s | S最高三重复通过档 req/s | 边界 |
|---|---:|---:|---|
| B 后端直连 | 3840 | 600 | 都是最高已测通过档，不是最大容量 |
| G 单网关 | 3840 | 240 | S 480/600未达标 |
| M 双网关直连轮转 | 3840 | 240 | S 480/600未达标 |
| L L4至双网关 | 1920 | 240 | A 3840三次99.159%/85.246%/85.652%；S 480/600未达标 |

正式1929600计划 = 1852173 success + 24816 transport_failure + 277 not_sent + 52334 HTTP拒绝；good为1852173。全部失败留在计划分母，不使用成功子集时延代替总体达标率。三重复只验证这些有限窗口与同机配置，不能外推生产容量、长期稳定性、物理NIC线速或GPU推理性能。

归因仍有限：S受固定4MiB聚合stream额度影响，E2仅扩到8MiB可使单G480从约81.67%升至100%；这属于配置控制。A单双generator的P95/P99差异超过10%，工具敏感；L3840退化在重复中复现，但第33项backend约0.861核、两个generator约0.844/0.837核，存在同机CPU争用/工具与后端忙核风险，不能直接称网关本体上限。

## 末两诊断与预算

按Leader冻结附加计划，A-L3840双generator/slots128、预热2s/正式5s、stream4MiB及其他参数一致，依次cap32→64；入口/池/准入/预约内存随cap配套变化。cap32：good98.776%，18965success/235transport_failure；cap64：good98.984%，19005success/76transport_failure/119not_sent。两者都未达99%；P95分别5.572/5.622ms、P99 12.282/9.613ms，backend均约0.817–0.818核。单对短窗且失败构成变化，不能声称cap64稳定提升或同资源优化；Reviewer反向顺序控制待独立结果。

累计118cell = 27 E1 + 7 E2 + 72 formal + 12 diagnostic，活动2285.344976s，低于120cell/5400s。账本保留两个中断负控failed及三个正式首错failed；没有running cell/auxiliary。425个已记录自有子进程PID全部不存在，已通知Leader交接Reviewer串行采集。

收口记录前证据1017802182B，最大单文件1048576B；最终JSON收口仅约1KiB，距2GiB充分。正式采样峰RSS160346112B、FD461，低于1GiB/2048；这是采样峰，不声称连续峰值或长期无泄漏。最终冻结py哈希全部匹配，未修改采样语义或主清单。Builder后续不再发压，由Leader统一验收与提交推送。
