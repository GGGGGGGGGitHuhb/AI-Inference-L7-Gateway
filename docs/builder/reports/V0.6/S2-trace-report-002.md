# V0.6/S2-trace Builder报告002：首个工具失败停止

状态：BLOCKED，未进入性能采样。2026-10-31。Leader冻结并授权执行清单`build-local/builder/v0.6-s2-trace/evidence/manifest-frozen-001.json`，SHA256 `502047b4ade0787b8a0da1b75f8778e0d55774dda9de0922f963ed8bdeaf83b0`。按批准首错规则停止，工具/原始结果/账本未修改，没有重试或续采。

## 已发生与未发生

| 项 | 实际证据 | 结果 |
|---|---|---|
| N-connection-limit | 2条客户端连接；占位连接published；探测连接唯一tuple关联Gateway outcome2，active1/reserved16777216 | complete |
| N-reservation | 2条客户端连接；占位连接published；探测连接唯一tuple关联Gateway outcome3，active1/reserved16777216 | complete |
| N-peer-reset | 1条完整合成请求；收口reset-peer PID33783 returncode=-15；L4 PID33785 returncode0 | failed |
| 低档1920 U/O/T×3 | 全9项未开始 | not_started |
| 高档3840 U/T×3 | 全6项未开始，无低档解锁 | not_started |

全轮3尝试/2验证/15未开始，不能将第三负控补判PASS。原始错误为`['close reset-peer:-15']`，只证明进程因SIGTERM退出。源代码中close_all批量发TERM后Owned.close可能再次发TERM，存在退出边界竞争候选；原现场没有两次信号投递及handler移除的精确时序，不能把候选写成已确认根因，更不能归因网关/L4产品错误。

## 原始关联的只读核验

原失败result保留metrics=null。另写派生`build-local/builder/v0.6-s2-trace/evidence/stopped-forensic-001.json`，SHA256 `be38ceada756ec08474ac61bf9c291a2bc2d94f2b6d93fd20f8c5fa919314611`，不覆盖采集结果。

派生核验：reset-peer保留完整ID `N-peer-reset-probe`和reset tuple；L4入站与客户端唯一关联，出站tuple与该后端记录一致；L4业务generation3首次观察侧2/errno104、reason SO_ERROR，原日志sent_c2b228/sent_b2c0。L4总3记录含2条显式kind3健康探针，drop0、重复0、live计数0，header及终态顺序通过。上述表明reset事件证据存在；仍不消除测试后端异常退出，第三控制和整轮均保持failed/BLOCKED。

## 回收、预算和保护

4个启动PID33777、33780、33783、33785均有returncode且后查/proc不存在；所有capture记录无cleanup_error、loss_bytes0，未触发deadline_killed。第三cell L4导出header跨度189091ns，原始TRACE_EXPORT_BEGIN也保留；控制器processes.export_begin_ns为null（该child已退出时未进入轮询读取），不冒称此字段观测到开始时间。

全轮summary elapsed1.781080929s，summary后closure计时1.782314185s；账本cell活动合计1.708549211s，3项分别0.113497069/0.099237869/1.495814273s。closure证据193012B，budget_pass=true；该值为当时全evidence目录，不含后续小派生文档，离4GiB有充分余量。每项采样如下（短负控采样稀疏，不代表精确瞬时峰值）：

| 项 | samples | sampled peak RSS B | sampled peak FD |
|---|---:|---:|---:|
| connection-limit | 2 | 31641600 | 10 |
| reservation | 1 | 27455488 | 6 |
| peer-reset | 14 | 87257088 | 25 |

测后冻结38files hash全部一致；Matrix.verify再次核Gateway源、隔离L4全部原文件与新增集合、外部L4原275文件、patch和二进制/CMakeCache均通过。没有修改产品、工具、外部树或旧阶段证据。一次离线脚本以Decode先导入引发旧capacity/Negative同名模块解析错误，未写结果或发压；按正式Matrix入口导入顺序完成上述只读派生，不修改冻结工具。

## 结论与交接

观察设施准备回归结果仍引用报告001，但AC2开销与AC3高档归因没有性能数据，S2产品优化入口保持BLOCKED。交Reviewer独立只读核验，由Leader决定是否提出后续有限方案；Builder不自行改冻结工具、不重跑、不续采、不把配额拒绝负控作为性能瓶颈证据。
