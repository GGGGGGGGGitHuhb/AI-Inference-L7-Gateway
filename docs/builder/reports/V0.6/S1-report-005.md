# V0.6/S1 Builder 005：第三次采集首停与受限证据交接

2026-10-29。依据Approved S1设计、返工001/002及Leader停止指令。状态：**当前正式矩阵BLOCKED，33/72已采、39未采；未验证任何三重复容量档位，不主张S1 PASS或S2入口**。是否进行新的有限修正以Leader后续明确授权为准，本报告记录当前事实。

v3 SHA256 `66b57cde541599fcc8e2666b618d7f5910913a7b9c025a6319cac5db4d026198`下，第33项`F-A-L-3840-r1`再因监控PermissionError停止，runner退出1；未自行修改冻结py、重跑或继续其他cell。已发生的是r0全部24项+r1前9项，不是三重复。

新增取证明确：generator-0 PID158143，phase=request-drain，读取`/proc/158143/fd`抛PermissionError，立即重新poll仍为null。现有规则要求存活/未确认退出子进程的权限异常fatal，工具按规则停止。事件时间在formal_end后16.364018ms、最后client.close后9.708117ms；稍后6个自有子进程均exit0、drain存在。不能把稍后退出逆推为当时已经确认退出，也不以此忽略原监控错误。

该点实际请求结果必须与监控首错分开：正式76800计划=65469 success+11196 transport_failure+135 not_sent；SLO good85.24609375%，lag P95 1.274021ms，生成器门槛通过，正文/协议损坏0。L4共88140 accepted/closed，client全部阶段tx20338392B=sent_c2b、rx89081208B=sent_b2c。前一重复同点good99.158854%与本次差异显著，原因未隔离；不得将本次低成功率改为采样错误或移出分母。

## 交付证据

- `build-local/builder/v0.6-s1/evidence/run/formal-summary-builder.json`：33项紧凑摘要，前18项引用批准r3派生，后15项引用原结果，第33保留error标记；每项含repeat/path/rate、outcomes、scheduled SLO、P95/P99、CPU/资源、来源hash。
- `.../run/not-started-formal-cells.json`：39项未执行cell，明确全部预热/正式ID前缀及索引范围；原72项plan不变。
- `.../run/F-A-L-3840-r1/monitor-events-0000.jsonl`：本次时间/PID/phase/traceback/returncode=null/fatal，原result与failed ledger保留。
- `.../source-after.json`与`source-before.json`完全一致：两仓实际源码hash、dirty diff和两个Release二进制均未变；冻结v3全部py hash一致。

总正式计划1929600；已发生33项的正式计划950400=920169 success+12647 transport_failure+163 not_sent+17421 HTTP拒绝；另外979200正式请求未执行。所有已观察正文/协议损坏0。任何group均不足完整三重复，本报告不提供“已验证可持续档位”。

角色累计77cell=27 E1+7 E2+10 diagnostic+33 formal，活动1226.1218s；没有running reservation。已确认263个自有PID全部回收。证据约558.22MB，最大单文件1048576B；33项采样峰RSS160346112B、FD461，均低于1GiB/2048门槛。上述峰值是采样观测，不称连续真实峰值或长期无泄漏。

校准/诊断结论仍限于：SSE固定4MiB stream总额度导致约16流并发的配置限制；A单双发压工具敏感，复用配置有单次时延效应。当前无法建立可行动产品热点与有效三重复前测，不能为了推进版本强行开启产品优化。

此前15组工具负控及21/21产品Release回归通过，不抵消本次真实采集阻塞。Builder已停止发压并向Reviewer交接，避免角色并发；没有Git提交/推送，由Leader统一处理。
