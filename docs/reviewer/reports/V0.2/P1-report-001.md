# V0.2/P1 Reviewer 独立审查报告001

2026-10-19；Athena。**结论：PASS。无待纠正发现、无接受债务，P1累计返工0/2。** P1为独立性能基线专项，S3已关闭且历史2/2不变。此结论不代表性能收益、生产容量或发布；由Leader同步最终用户文档和状态，协调者按既有授权处理本地提交，本人未提交/推送。

## 1. 范围、权威与独立性

完整读取Approved [P1设计](../../../leader/designs/V0.2/P1-design.md)、[审查计划](../../reviews/V0.2/P1-review.md)、Leader001、Builder001/拆解、来源说明、用户结果/完整cell表及全部六个新Python工具和README；结合根文档P1边界、既有S3最终接受以及只读Support/WireResponse/CMake。无项目AGENTS或专用Reviewer指南，使用用户跨项目规则及plan-project-docs全局Reviewer模板回退；执行路线技能沿用。personal-cpp-standards规则与正反例已读；本次没有C++代码变化，因此不无故重跑三套或旧S3长期实验。

原生WSL，/bin/bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway；分支codex/v0.2-performance-baseline，HEAD555b65d66a52d95791dba5445178e57a69b81d2c。独立目录build-local/reviewer/v0.2-p1/{tmp,cache,evidence,release}，Python/构建前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME；socket回环测试首次按已知边界精确升级，无安装/下载/全局操作。共享CPU模型只读，独立构建、端口、进程和测量，测量期间没有其他角色性能运行。

以下E指build-local/reviewer/v0.2-p1/evidence。Reviewer只新增独立探针、证据、本文及[独立测量附表001](P1-measurements-001.md)，未修改产品、工具、权威或历史。

权威/交付SHA再次独立核验：

| 文件 | SHA256 |
| --- | --- |
| Leader P1-design | b65bf637c62463d5a7863c3e1fc988b9d27122e284c9d0cea4978e818fb45a2f |
| Reviewer P1-review | ab535bb2e4ee4aaf39675478ef507a38cdecb17a4a998d3f0a8a6d23d465d397 |
| Leader P1-report-001 | 3938f140b1dedd9ec43346ffeaf594095864c32191d72db8d70c06998f55879f |
| Builder P1-report-001 | de8203f8d8ed135930855302b06d8ed9f5a34c2bce96acd2329dc74a709e51d7 |

## 2. 独立执行与实际结果

所有命令在上述cwd/env执行，构建普通sandbox，回环/模型命令窄升级。主命令及实际退出/日志：

| 命令 | 实际结果与证据 |
| --- | --- |
| cmake --preset release -B build-local/reviewer/v0.2-p1/release；cmake --build该路径 -j4 | exit0，E/configure.log、build.log；独立12项Release产物另存hash |
| ctest --test-dir build-local/reviewer/v0.2-p1/release --output-on-failure | exit0，**15/15，27.53s**，E/ctest.log及release/Testing/Temporary/LastTest.log |
| python3 tests/performance/RunBaseline.py --check --output E/detectors | exit0；E/detectors.log与detectors目录。3时钟控制、10失败attempt、零成功null、失败子命令exit1/缺参数资产exit2均通过 |
| python3 tests/performance/RunBaseline.py --gateway "$PWD/build-local/reviewer/v0.2-p1/release/ai-inference-gateway" --host "$PWD/build-local/reviewer/v0.2-p1/release/IntegrationRuntimeHost" --assets "$PWD/build-local/integration/v0.2-s3" --output E/run-001 | exit0；**72/72，751.520285s**，E/run-001.log及原始run目录。未重跑/择优 |
| python3 E/BoundaryProbe.py | exit0，E/boundary-probe.log；8独立边界attempt及额外4个混合早/晚worker结果，通过 |
| python3 E/Audit.py E/run-001 E/independent-audit.json | 完整结果成功；E/audit.log，独立40,498项断言一致 |
| python3 E/Audit.py build-local/builder/v0.2-p1/evidence/run-002 E/builder-independent-audit.json | 完整结果成功；E/builder-audit.log，当前Builder run同样40,498项一致 |
| python3 E/ContractAudit.py；python3 E/Identity.py | 完整成功输出，E/contract-audit.json、identity.log/identity.json；审计串行shell最终exit0，没有错误/Traceback |

计数独立核对为：主矩阵A13,500/B1,800/C120/R720=16,140，控制1,500，预热1,740；**19,380唯一attempt、0失败、0未开始**。全部成功正文、时序、请求hash、batch结束=max(t_closed)、实际在途峰受C约束；未以汇总计数代替覆盖。

额外BoundaryProbe不导入DetectorTests：CL最后一字节延迟120ms与EOF再延迟200ms；SSE role/不完整content后延迟120ms才完整；chunk零块最后空行延迟120ms；HTTP完成后两种迟到尾随；validator分别抛KeyboardInterrupt/SystemExit/RuntimeError。完整/partial时钟和失败分类均符合约定。再通过实际batch收集2成功+2验证失败，最晚返回仍恰一次持久化，not_started为空，batch终点等于最后关闭。

既有实际SIGTERM负控在独立目录执行：单/双发压各**16 started=16 saved、112 not_started**，外层预期exit1；双子进程exit0且已回收。失败负控本身不算正式矩阵失败，未删除或改写其原始日志。

## 3. RV/AC逐项验收

| 项 | 独立检查与结论 |
| --- | --- |
| RV01/AC01 | 54测量源逐项匹配当前文件、2运行二进制及12Release产物留hash；143历史保护项142原字节保持，唯一授权CMake变化仅新增快速入口。产品src/旧S3工具/输入/第三方保持。资产大小/hash/许可证、已知llama-server身份及库文件独立核验；9个CPU模型实际CLI固定4线程/ctx2048/parallel1/ngl0。102启动与102reaped匹配且PID不存在。PASS |
| RV02/AC02 | 自行重建期望调度而非导入schedule，72项顺序、69矩阵及3控制、warmup/count/timeout/guard一致；39份网关/host配置符合固定设计。PC和流式正式accept数等于请求数，PR正式accept增量≤并发、确有预热复用；每cell后端请求差量等于正式n、无后端发送错误。真实请求实际执行，不以旧S3输出替代。PASS |
| RV03/AC03 | 人工审查预序列化/t0/connect/send/recv/body/content/HTTP/EOF/校验/关闭边界与WireResponse调用顺序；3时钟负控及独立8边界+4晚到混合控制通过。全部确定性body SHA/长度、SSE唯一DONE/finish、严格HTTP终态及失败partial留存正确；主计时不含EOF延迟，校验关闭计入闭环。PASS |
| RV04/AC04 | 独立Audit.py只用标准库、不导入Summarize；从每条原始attempt/resource重算成功/失败/分位、批次完成率/字节率/token率、实际在途、周转、CPU秒/核数等价/RSS/FD/context-switch、快慢分布、后端间隔及三重复median/min/max；Reviewer和Builder最终run各40,498项一致。低n尾分位和缺token正确null。PASS |
| RV05/AC05 | 3控制与50ms/1s资源采样、机器load/system CPU和worker周转记录齐备；独立结果触发前后控制>20%漂移并在附表明确，不根据平台曲线声称容量。Release15/15及新增负控实际通过；不存在新增C++设施或无关产品调参。PASS |
| RV06/AC06 | Builder主报告/两次附表清楚区分run身份、自测/独立验收、目标与实际间隔、CPU单slot/闭环限制；Reviewer独立附表列全部72cell、三重复表、C快慢与资源、3控制及失败数，保留Builder来源。交Leader将该附表链接/核心观察并列到用户结果报告并更新待验收状态，这是收口责任，不替换历史数据。PASS |

## 4. 独立观察与结论边界

详见[独立附表](P1-measurements-001.md)。三cell统计中位：A并发1的D/PC/PR E2E p50为**1.035/1.721/43.894ms**，PR在本后端上更慢，数据不支持复用收益。真实流并发1 D/P TTFT p50为**16.603/17.387ms**，E2E p50为**443.916/423.359ms**；这些是不同请求/时段的聚合观察，P E2E较低不证明网关加速，更不能把相减值命名为单请求额外开销。

C host pause/resume三轮159/159、150/150、159/159；容量峰1MiB、预约峰64MiB，pending峰/快慢延迟见附表。三轮自然排空FD=7以及所有活动账本零，随后停止自有host；自然排空与强制进程停止未混淆。

本次前后控制触发>20%漂移，Builder最终run另有双进程>15%及客户端近一核标记，结果并不要求一致。不能从两角色差值归因产品或某一工具机制；保留原始环境/采样与时间顺序。Python发压/后端、单机调度、单slot缓存/排队和闭环coordinated omission仍限制外推。只有三重复观察范围，无置信区间；A p99探索性、B p50/p95、真实p50/p90；流式无可靠token计数则null。未验证/未声称生产容量、GPU、多实例调度、严格公平、开放负载SLO或性能优化收益，这些不在Approved范围。

## 5. 发现、身份与交接

**发现：None。Blocker/Major/Minor均无待处理项；无需返工、无需技术债。** 上述负面性能与波动是已按设计披露的观察，不是待修缺陷。没有关键验收缺口或环境阻塞。

独立当前身份（完整明细E/identity.json）：

- run-001/manifest.json（54测量源+2运行binary）：`b46e136388ec1ae7dd24b38273fc31665bb8746445abfb21f64fd51618354088`。
- E/source-sha256.json（54项）：`c6b5c9d1b3dc42399817a73e4d77a120a372c416b870e2e183334aaa0c61dc02`。
- E/binaries-sha256.json（12项Release产物）：`a7f7c27c863607f70b1d8880a58c70c389a8eda11688e4ce46a627740bc9ec92`。

固定tar19144446字节/SHA9cbbff430e4f2d976135d68d998576530cc1bd87babe1d71db4886d8a79e7b2e、GGUF491400032字节/SHA74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db均独立复核；llama-server SHA45938e6847d403ff6486cd692de9441aeb330e971a5dd8ad6f695b60bae2d081。无资产更换。

所有自有模型/后端/gateway/host及控制发压子进程均回收，短边界服务线程关闭；没有后台负载遗留。Builder初次run/初始负控/四源变化身份保留，未把旧run时间作为当前工具复跑；本文只接受当前工具身份下的独立run。未改变S3或P1权威/既有报告，未提交、推送或提前启动V0.3。交Leader收口用户结果/根状态，保留两角色独立观察和当前限制。
