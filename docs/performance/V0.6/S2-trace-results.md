# V0.6/S2-trace 首停结果（2026-10-31）

**观察设施未验收，未采集性能数据；S2产品优化入口继续BLOCKED。** 本轮实现默认关闭的连接生命周期观察点及隔离L4补丁，准备回归通过后，冻结三控制/九低档/条件性六高档清单。实际在第三控制发生工具收口错误，严格停止，无重试或续采。不能将此结果称为有效负面性能诊断，也不能据额度负控认定真实容量瓶颈。

## 实际执行

| 项目 | 结果 |
| --- | --- |
| 连接额度拒绝控制 | 2连接；占位已发布，探测四元组唯一关联Gateway outcome2 |
| 预约拒绝控制 | 2连接；占位已发布，探测四元组唯一关联Gateway outcome3 |
| L4对端reset控制 | 1业务连接；reset-peer退出码-15，控制FAIL |
| 1920req/s U/O/T三重复 | 9项全部未开始，开销门槛未验证 |
| 3840req/s U/T三重复 | 6项全部未开始，无归因/可信度结果 |
| Reviewer独立矩阵 | 未启动：同冻结工具已有真实收口失败，改为独立只读审计 |

第三项保留完整合成请求ID、客户端/L4入站及L4出站/测试后端四元组；独立解码可核对L4首次观察上游侧errno104。该事件证据不消除测试后端异常退出，原结果metrics=null和failed账本保持。源码确有批量通知后单进程close再次通知TERM的路径；现场没有信号投递与handler恢复的精确时间，不能断言第二次信号就是此次致命原因。

## 验证与边界

| 准备检查 | Builder | Reviewer |
| --- | --- | --- |
| Gateway Release U/O完整回归 | 21/21、22/22 | 21/21、22/22 |
| L4 Release U/O TCP | 各13/13 | 各13/13 |
| Gateway ASan+UBSan受影响路径 | 7/7 | 核验日志和编译参数，未另跑 |
| 最终无网络工具/矩阵/测试前提检查 | 12/12、9/9、3/3 | 12/12、9/9、3/3 |

L4既有测试曾因accept尚未就绪、后端仍SYN_SENT、源耗尽形成伪背压平台失败。依[返工001](../../leader/reworks/V0.6/S2-trace-rework-001.md)/[002](../../leader/reworks/V0.6/S2-trace-rework-002.md)仅修隔离测试前提，保留原计数、双向pending和停止时限断言。旧失败保留；它们不是产品性能修复。

默认Gateway观察编译关闭；本轮U二进制与既有基线相同。L4外部实际dirty源码只读，诊断代码及测试修正只在隔离副本。原capacity/capacity_diagnosis工具与旧证据不改。诊断构建不等于可接受的观察开销，尚无U/O/T性能对照。

## 资源与可审计材料

Builder清单SHA256为`502047b4ade0787b8a0da1b75f8778e0d55774dda9de0922f963ed8bdeaf83b0`。3 attempted、2 verified、15 not_started；全轮1.781080929秒，写summary后1.782314185秒。closure当时evidence共193012B，不包含随后只读派生/报告。四个子进程均wait/reap且独立检查/proc不存在；无捕获丢失、强杀或cleanup_error。短控制采样最大RSS87257088B、FD25，不是精确瞬时峰值或性能测量。

- [原冻结清单](S2-trace-manifest.json)、[原首停汇总](S2-trace-summary.json)、[只读派生核验](S2-trace-forensics.json)按原文件保留；不覆盖原始失败。
- 原始日志、binary trace、ledger、closure、逐源码清单位于本机`build-local/builder/v0.6-s2-trace/evidence/`；独立审计在对应reviewer目录。原始目录被Git忽略，未宣称随推送包含全部原始数据。
- [Builder准备001](../../builder/reports/V0.6/S2-trace-report-001.md)、[首停002](../../builder/reports/V0.6/S2-trace-report-002.md)、[Reviewer001](../../reviewer/reports/V0.6/S2-trace-report-001.md)、[Leader003](../../leader/reports/V0.6/S2-trace-report-003.md)。

本轮没有新的QPS、延迟、CPU开销或产品根因结论。此前S1已测档位保持历史结论，不因本轮工具失败升降。后续应先修停止通知幂等性并用真实短生命周期子进程验证，保留本轮失败，再单独评审冻结有限采集；不在此账本续跑、不调大产品额度、不提前创建产品优化设计。
