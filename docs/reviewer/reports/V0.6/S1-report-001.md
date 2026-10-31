# V0.6/S1 Reviewer 001：独立容量诊断与验收边界

2026-10-29。独立 Reviewer，依据 [S1 设计](../../../leader/designs/V0.6/S1-design.md)、[审查计划](../../reviews/V0.6/S1-review.md)、Approved 返工001–004及冻结附加诊断计划。已读 Builder 001–006，未以 Builder 自测替代独立采集。项目无专用 Reviewer GUIDE，沿用全局 plan-project-docs Reviewer 参考模板；执行原生 WSL、角色独立 Release 构建、tmp/cache/证据目录。

## 结论

| 对象 | 结论 | 依据与限制 |
|---|---|---|
| 最终测量设施与数据守恒 | PASS（本次范围） | 负控、完整独立矩阵及全量原始审计通过；历史首停和工具版本边界保留，不称首次无错误 |
| S1 有界诊断交付 | PASS | 两角色同一72项矩阵、有限控制、预算及来源证据完整；允许以有边界的诊断交付收口 |
| 冻结条件下的有限窗口档位 | PASS | 可报告下表的最高已测通过档和相邻失败档；不是最大容量、生产SLO或持续稳定性保证 |
| 网关本体最大容量及L4高档唯一瓶颈归因 | BLOCKED | 发压工具敏感、同机资源争用尚未隔离；未证实具体产品热点 |
| S2 产品优化入口 | BLOCKED | 尚无可行动产品热点与可归因的收益基线；不能把已有配置额度效应当作产品优化 |

本报告接受测量和诊断材料，不批准“同资源扩容收益”“生产容量上限”或任何新产品性能提升声明。Leader负责阶段收口；后续S2设计必须另行引用证据并冻结目标。

## 独立执行与身份

自有根目录：`build-local/reviewer/v0.6-s1/`。Gateway、只读dirty L4源分别独立配置/构建 Release；L4 `BUILD_TESTING=OFF`、`L4LB_BUILD_XDP=OFF`、`L4LB_BUILD_XDP_LOADER=OFF`，无下载、安装或产品修改。构建前文件hash与采集前/后实际源文件hash一致；L4既有dirty diff保留。`source-before.json` 与 `source-after.json` 完全相同，包含两个二进制hash。`protection-audit.json`确认基线`b9a12d46e13ff937947e72c5e7ddb173a22e3be9`以来受保护产品及既有测试无修改。

Reviewer与Builder压力采集串行。Reviewer正式前完成自有Release回归：21/21，40.33s，见`evidence/ctest-release-loopback.log`。首次默认沙箱因禁止创建socket失败的日志`ctest-release.log`保留；随后仅本机回环测试权限下通过，不将权限限制归为产品失败。

完整计划83cell：5个故障/中断/冒烟诊断、4个关键E2、72个正式、最后2个反序配额诊断。未重复全部探索阶梯；复用经审查的选档证据，独立重做关键控制。下游每请求新TCP、上游reuse=false；聚合slots128、cap32、stream4MiB；M/L每实例均分额度。A使用两个generator，S使用一个；所有角色在同机20逻辑CPU上运行，未固定CPU quota或专核。

初始完整最坏预算2,116,227,273B，低于2GiB，余31,256,375B；包括全部83项、未使用的5个诊断预留和16MiB收口池。续采及末诊断前均按实际已用重新预检，没有删除失败或重开账本。

## 首停、批准修正与版本边界

Builder前三次正式首停分别为多词L4结束理由漏解析、收口采样缺少错误细节、窗口外PermissionError即时poll未取得退出码。Reviewer独立核对原始日志/采样时序及全部对应前缀，批准返工范围内的派生结果保留真实失败请求，不重新发压。各次历史报告和v1–v4清单保留。

Reviewer以v4从头采集，SHA256 `a559456acd9851c51a14b877fcfb42bdfe829c144bd4c61efdf71ebc245fe692`。第33项`F-A-L-3840-r1`在cleanup发生`/proc/166168/stat`的FileNotFoundError，l4lb即时poll为null；v4没有为该异常执行有界等待，因此按规则停止。事件在formal_end后43.195092ms、最后client close后37.035458ms；全部6个子进程最终exit0并回收。原result/error与ledger.failed保留，63869成功、12821传输失败、110漏发均未改动。

[返工004](../../../leader/reworks/V0.6/S1-rework-004.md)统一三类退出读取异常：仅自有子进程、实际时间已过formal_end且处于排空/cleanup，才允许无信号等待至多min(100ms,剩余cell活动期限)，实际取得退出码才跳过。窗口内、控制器自身、仍活或超时仍fatal；正常采样间隔和请求语义不变。该机制不要求推断具体内核或CPython竞争根因。

Reviewer唯一profile `reviewer-v4-prefix33`绑定原plan/provenance/event/result SHA、PID、唯一失败和完整33项输入。Reviewer自行生成`run/formal-reaudit-r5/summary.json`，SHA256 `540da55f61575e0c993b58ba7d070bf13b3dfbe1a0746915cc15c7ae5c4c5681`；全部派生metrics与原metrics逐字段相等。最终v5 SHA256 `f059fc20bf38d0c7f333440d925f1ff70316cd19beac7769b5fdc9bc49018e9a`只续采余39新ID，未重发前33项。

Reviewer另观察两次窗口外PermissionError经真实退出确认安全跳过，等待1.207920ms和1.270866ms，均exit0；唯一fatal仍为已保留的原第33项。不能将恢复后完成描述为收口全过程首次无错。

## 全部原始数据独立审计

自写`evidence/IndependentAudit.py`不导入提交工具，逐cell读取全部原始记录，验证计划ID覆盖/唯一性、scheduled公式、时序、成功正文hash、backend身份、L4完整会话和字节守恒、全部失败分母、goodput、每个延迟分位、生成器有效性、精确进程集合及退出。逐资源采样独立复算进程/线程ticks、真实窗口、1tick量化、RSS/FD峰值及采样开销。

正式72项及7个成功控制/冒烟项全部通过该审计，见`all-independent-audit.json`。4个故障/中断诊断单独验证预期失败，未将其纳入成功样本。独立审计第一次运行曾发现自身将dispatch误列为latency字段，修正自有脚本后全量重算；未修改提交工具或任何原始结果。

正式计划1,929,600请求，完整守恒：

| 终态 | 数量 |
|---|---:|
| success / SLO good | 1,839,022 |
| transport_failure | 38,077 |
| not_sent | 220 |
| HTTP拒绝 | 52,281 |
| 正文/协议损坏 | 0 |

含预热的正式矩阵总计划2,219,040。所有72项generator_valid为true；成功子集分位不替代全部计划达标率。goodput以scheduled归属正式20秒窗口的达标请求为分子，包括自身SLO内排空期完成者；分母固定20秒。P50/P95/P99分别遵守20/100/1000成功样本门槛。

## 有限窗口结果

每点3s预热、20s正式、三重复；A端到端≤100ms，S端到端≤250ms且首body≤50ms，三次均≥99%才列通过。

| 路径 | A最高已测三重复通过档 req/s | S最高已测三重复通过档 req/s | 已测失败边界 |
|---|---:|---:|---|
| B 后端直连 | 3840 | 600 | 两workload均未测到失败上界 |
| G 单网关 | 3840 | 240 | S 480/600未过 |
| M 双网关直连轮转 | 3840 | 240 | S 480/600未过 |
| L L4至双网关 | 1920 | 240 | A 3840、S 480/600未过 |

A/L1920三次99.848958%/100%/99.942708%；A/L3840三次86.084635%/83.162760%/83.781250%，退化在独立角色复现。A/G3840三次99.342448%/99.734375%/99.548177%，A/M为99.424479%/99.640625%/99.653646%。S/B三档均100%；S/G、M、L的240均100%，480约79.69%–81.75%、600约65.30%–68.68%，以HTTP拒绝为主。

只能将这些数字解释为当前同机拓扑与固定配置、有限窗口的通过/失败档位。L的A通过1920、失败3840可作为该端到端配置的测试区间；S代理通过240、失败480同理。不得转述为Gateway本体最大容量、长期生产容量、物理NIC线速、GPU吞吐或模型token延迟。

## 关键控制与未隔离因素

- A/G3840单→双generator，总slots保持128：good98.5104%→99.1146%，HTTP P95 3.732785→3.223614ms（变化超过10%），单generator约0.9469核。工具敏感得到独立支持，不能把单发压失败当产品上界。
- S/G480仅stream4→8MiB：good81.25%→100%；正式仍使用4MiB。源码每流预约256KiB、聚合4MiB仅16份，控制支持配置额度限制。这是既有配置效应，不是产品代码优化。
- A/L3840三个正式重复backend约0.842–0.850核、两个generator约0.825–0.844核；存在同机资源与工具风险，但Reviewer这些值不应直接标记为严格大于0.85。Builder有相应忙核证据。未获得可行动产品热点剖析，不认定唯一瓶颈原因。
- 按冻结附加计划反序cap64→32，其他条件相同、2s预热/5s正式：cap64 good99.010417%，19010成功/160传输失败/30漏发；cap32 good98.875%，18984成功/155传输失败/61漏发，生成器均有效。HTTP P95/P99分别11.322977/23.419166ms与5.496225/7.543620ms。cap64尾延迟更差；Builder正序两点均未过99%。单对短窗、跨角色结果不一致，不能声称配额扩大稳定改善，更不能称同资源优化。

网络口径限于应用transport入队/接收及L4成功send日志；失败时不把入队字节当交付字节。没有测包级/NIC字节、握手和重传，也没有把捕获read等待时间解释为产品pipe阻塞。原CPU ticks、窗口与量化误差保留；采样峰值不等于连续峰值。

## 验证、预算与门槛映射

| 审查项 | 结论 | 实际证据 |
|---|---|---|
| RV01 / AC01 来源、选档、冻结、拓扑 | PASS | 自有构建和源前后身份；同72项未改；所有原错误和版本链保留 |
| RV02 / AC02 完整分母与统计 | PASS | 全72原始独立审计；19项提交工具无负载测试通过；5项Reviewer自写parser负控通过 |
| RV03 / AC03 诊断边界 | PASS，产品归因受限 | 单双generator、stream额度、B对照、反序配额控制；产品最大容量与S2入口BLOCKED |
| RV04 / AC04 预算、负控、清理 | PASS | 预留与累计账本、超限/重复/缺失检测、真实在途打断、326个进程全部回收 |
| RV05 交接 | PASS | 分开接受诊断材料与阻塞S2，未提前改变产品 |

最终83cell=72正式+4E2+7diagnostic；累计活动1961.059927s，低于5400s。原中断负控和正式首错failed状态保留，无running cell/auxiliary。326个记录PID全部不存在。正式采样峰RSS157,802,496B、FD518，低于1GiB/2048；最大单文件1,048,576B。收口前证据915,688,912B，约0.853GiB，最终摘要仅增加少量KiB，低于2GiB。

故障负控真实结果：timeout产生1个deadline；bad_body产生60个body_error；overload产生20个HTTP拒绝+40个not_sent；在途中断300个计划=81 interrupted+219 not_started，backend已收件记录保留且正常退出。L4冒烟60/60成功。19项无负载测试涵盖重复/丢ID、时钟、正文、文件/累计额度、日志分片和多词reason、正式损坏首停、精确进程集合及恢复profile、三类退出读取异常的21组合。Reviewer自写5项parser控制覆盖严格CL/chunk语法、冲突framing、截断/多余字节及首body提前观测。

## 复现入口与未验证范围

所有命令设置Reviewer局部`TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX`。主要入口及对应证据：

- `ctest --test-dir build-local/reviewer/v0.6-s1/gateway --output-on-failure` → `ctest-release-loopback.log`。
- `ReviewerControls.py` → `control-executions.json`及各诊断/E2日志；只调度冻结工具。
- `Run.py --mode formal --manifest ... --output .../reviewer/.../evidence/run` → 原`formal-plan.json`、`formal-provenance.json`、`formal-v4.log`与首错原result。
- `Resume.py --profile reviewer-v4-prefix33 --parent .../S1-manifest-v4.json ...` → `formal-reaudit-r5`；`Run.py --mode resume --manifest .../S1-manifest.json ...` → `formal-resume-r5-provenance.json`、`formal-resume-v5.log`。
- `Run.py --mode cell ... --capacity 64`后`--capacity 32`，其余参数见附加诊断计划 → `quota-64.log`、`quota-32.log`及各cell原始文件。
- `IndependentAudit.py`与`all-independent-audit.json`、`reviewer-closure.json`、`initial-budget.json`、`rework004-ready.json`、`quota-diagnostics-budget.json`为独立复核/收口入口；原始分片均保留。

未验证生产部署、长时间浸泡、物理网络/XDP、真实模型/GPU及跨机同资源扩容。未确认L4高档退化的唯一产品根因。S2必须先补充能隔离工具/后端/调度争用的证据，再选择产品改动和预注册收益门槛；本阶段不隐含授权提前优化。
