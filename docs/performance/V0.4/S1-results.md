# V0.4/S1 Builder 固定基线结果

一次完整新矩阵 `run-002`：PASS，57/57 cell，407.07s。正式7104、预热486，共7590唯一ID。此为Builder证据，独立Reviewer尚待执行。

原 run-001 因工具将源端口当永久身份而在第14cell失败，不能作为有效性能负面结果；原始失败保留。Approved返工1/2仅修后置关联，完整run-002重新执行原计划，不拼接/补样本/择优。

## 工具控制与比较边界

T首单/双进程/末单完成吞吐：[1319.0891143562476, 2159.9131205186054, 716.9578469079049] req/s。标记：`{'machine_drift': True, 'generator_sensitive': True, 'client_cpu_at_least_085': True, 'suspected_generator_limit': True}`。

控制标记触发时，仅报告本次受限环境的描述性数据，策略因果收益、代理容量及普遍提升未证实。不直接归因GIL。三重复不混池、不剔除受限对、不宣称置信区间。

| 配对 | 有效对数/3 | 三次后者减前者 goodput (req/s) |
| --- | --- | --- |
| H-20 | 3/3 | [3.1667, 3.3333, 3.3333] |
| H-60 | 3/3 | [11.0, 11.0, 11.0] |
| Q-60 | 3/3 | [-10.5, -13.0, -10.5] |

H后者为LI，前者RR；Q后者queue8，前者queue0。有效仅指双方未arrival_limited，不消除机器漂移/发压敏感。

## 各固定条件三次 goodput

单位req/s；三次原值和median[min,max]，每个cell按冻结SLO/原分母。

| 条件 | 三次原值 | median [min,max] |
| --- | --- | --- |
| A/D/C1/rate0/q0/nodelayFalse | [871.4824, 471.5627, 479.6146] | 479.6146 [471.5627, 871.4824] |
| A/PC/C1/rate0/q0/nodelayFalse | [678.8162, 343.4899, 329.1917] | 343.4899 [329.1917, 678.8162] |
| A/PR/C1/rate0/q0/nodelayFalse | [22.4014, 22.5369, 22.343] | 22.4014 [22.3430, 22.5369] |
| A/D/C4/rate0/q0/nodelayFalse | [1688.0762, 941.489, 1014.0199] | 1014.0199 [941.4890, 1688.0762] |
| A/PC/C4/rate0/q0/nodelayFalse | [1155.7038, 796.3801, 885.3924] | 885.3924 [796.3801, 1155.7038] |
| A/PR/C4/rate0/q0/nodelayFalse | [89.8634, 88.1512, 86.5798] | 88.1512 [86.5798, 89.8634] |
| N/PR/C1/rate0/q0/nodelayFalse | [22.491, 22.4075, 22.3516] | 22.4075 [22.3516, 22.4910] |
| N/PR/C1/rate0/q0/nodelayTrue | [677.187, 570.4451, 437.3407] | 570.4451 [437.3407, 677.1870] |
| B/D/C4/rate0/q0/nodelayFalse | [2.1548, 2.1309, 2.1027] | 2.1309 [2.1027, 2.1548] |
| B/P/C4/rate0/q0/nodelayFalse | [2.1607, 2.1269, 2.1128] | 2.1269 [2.1128, 2.1607] |
| H/RR/C0/rate20/q0/nodelayFalse | [15.0, 15.0, 15.0] | 15.0000 [15.0000, 15.0000] |
| H/LI/C0/rate20/q0/nodelayFalse | [18.1667, 18.3333, 18.3333] | 18.3333 [18.1667, 18.3333] |
| H/RR/C0/rate60/q0/nodelayFalse | [45.0, 45.0, 45.0] | 45.0000 [45.0000, 45.0000] |
| H/LI/C0/rate60/q0/nodelayFalse | [56.0, 56.0, 56.0] | 56.0000 [56.0000, 56.0000] |
| Q/P/C0/rate60/q0/nodelayFalse | [28.0, 27.0, 28.0] | 28.0000 [27.0000, 28.0000] |
| Q/P/C0/rate60/q8/nodelayFalse | [17.5, 14.0, 17.5] | 17.5000 [14.0000, 17.5000] |
| R/D/C2/rate0/q0/nodelayFalse | [2.2786, 2.258, 2.019] | 2.2580 [2.0190, 2.2786] |
| R/P/C2/rate0/q0/nodelayFalse | [2.1399, 2.2344, 1.9166] | 2.1399 [1.9166, 2.2344] |

## 每cell分母、终态与时延

E2E/TTFT为成功样本median(ms)，成功n不足门槛时不报尾分位；p50/p95及send时延、长短/快慢分组见原analysis.json和formal-summary.json。SLO失败属于success内部子集，不增加总分母。开环goodput分母固定120/rate，完成吞吐分母lastterminal−t0，两者不同。

| cell | counts | SLO达标 | goodput | 完成吞吐 | E2E median ms | TTFT median ms | arrival_limited |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 00-T-0-D | {'success': 200} | 200 | 1319.0891 | 1319.0891 | 2.257 | null | False |
| 01-T-1-D | {'success': 200} | 200 | 2159.9131 | 2159.9131 | 2.918 | null | False |
| 02-A-0-D | {'success': 200} | 200 | 871.4824 | 871.4824 | 0.804 | null | False |
| 03-A-0-PC | {'success': 200} | 200 | 678.8162 | 678.8162 | 1.160 | null | False |
| 04-A-0-PR | {'success': 200} | 200 | 22.4014 | 22.4014 | 43.703 | null | False |
| 05-A-0-D | {'success': 200} | 200 | 1688.0762 | 1688.0762 | 1.406 | null | False |
| 06-A-0-PC | {'success': 200} | 200 | 1155.7038 | 1155.7038 | 2.583 | null | False |
| 07-A-0-PR | {'success': 200} | 200 | 89.8634 | 89.8634 | 43.544 | null | False |
| 08-N-0-PR | {'success': 100} | 100 | 22.4910 | 22.4910 | 43.672 | null | False |
| 09-N-0-PR | {'success': 100} | 100 | 677.1870 | 677.1870 | 1.195 | null | False |
| 10-B-0-D | {'success': 12} | 12 | 2.1548 | 2.1548 | 144.133 | 4.009 | False |
| 11-B-0-P | {'success': 12} | 12 | 2.1607 | 2.1607 | 183.876 | 10.321 | False |
| 12-H-0-RR | {'success': 120} | 90 | 15.0000 | 18.8883 | 63.619 | 63.619 | False |
| 13-H-0-LI | {'success': 120} | 109 | 18.1667 | 18.8822 | 44.456 | 44.456 | False |
| 14-H-0-RR | {'success': 120} | 90 | 45.0000 | 50.2280 | 67.446 | 67.446 | False |
| 15-H-0-LI | {'success': 120} | 112 | 56.0000 | 51.6935 | 25.552 | 25.552 | False |
| 16-Q-0-P | {'success': 60, 'http_rejection': 60} | 56 | 28.0000 | 28.2835 | 24.839 | 24.839 | False |
| 17-Q-0-P | {'success': 76, 'http_rejection': 44} | 35 | 17.5000 | 31.1699 | 255.155 | 255.155 | False |
| 18-R-0-D | {'success': 12} | 12 | 2.2786 | 2.2786 | 865.141 | 31.535 | False |
| 19-R-0-P | {'success': 12} | 12 | 2.1399 | 2.1399 | 895.486 | 33.720 | False |
| 20-A-1-PR | {'success': 200} | 200 | 22.5369 | 22.5369 | 43.564 | null | False |
| 21-A-1-PC | {'success': 200} | 200 | 343.4899 | 343.4899 | 2.432 | null | False |
| 22-A-1-D | {'success': 200} | 200 | 471.5627 | 471.5627 | 1.645 | null | False |
| 23-A-1-PR | {'success': 200} | 200 | 88.1512 | 88.1512 | 43.774 | null | False |
| 24-A-1-PC | {'success': 200} | 200 | 796.3801 | 796.3801 | 3.872 | null | False |
| 25-A-1-D | {'success': 200} | 200 | 941.4890 | 941.4890 | 2.634 | null | False |
| 26-N-1-PR | {'success': 100} | 100 | 570.4451 | 570.4451 | 1.271 | null | False |
| 27-N-1-PR | {'success': 100} | 100 | 22.4075 | 22.4075 | 43.622 | null | False |
| 28-B-1-P | {'success': 12} | 12 | 2.1269 | 2.1269 | 300.678 | 17.513 | False |
| 29-B-1-D | {'success': 12} | 12 | 2.1309 | 2.1309 | 238.889 | 5.656 | False |
| 30-H-1-LI | {'success': 120} | 110 | 18.3333 | 19.8874 | 25.001 | 25.001 | False |
| 31-H-1-RR | {'success': 120} | 90 | 15.0000 | 18.8868 | 65.091 | 65.091 | False |
| 32-H-1-LI | {'success': 120} | 112 | 56.0000 | 51.7238 | 24.676 | 24.676 | False |
| 33-H-1-RR | {'success': 120} | 90 | 45.0000 | 50.2590 | 64.325 | 64.325 | False |
| 34-Q-1-P | {'success': 76, 'http_rejection': 44} | 28 | 14.0000 | 29.9418 | 270.064 | 270.064 | False |
| 35-Q-1-P | {'success': 58, 'http_rejection': 62} | 54 | 27.0000 | 27.3539 | 24.120 | 24.120 | False |
| 36-R-1-P | {'success': 12} | 12 | 2.2344 | 2.2344 | 897.223 | 34.109 | False |
| 37-R-1-D | {'success': 12} | 12 | 2.2580 | 2.2580 | 879.260 | 32.383 | False |
| 38-A-2-PC | {'success': 200} | 200 | 329.1917 | 329.1917 | 2.563 | null | False |
| 39-A-2-D | {'success': 200} | 200 | 479.6146 | 479.6146 | 1.615 | null | False |
| 40-A-2-PR | {'success': 200} | 200 | 22.3430 | 22.3430 | 43.583 | null | False |
| 41-A-2-PC | {'success': 200} | 200 | 885.3924 | 885.3924 | 3.436 | null | False |
| 42-A-2-D | {'success': 200} | 200 | 1014.0199 | 1014.0199 | 2.496 | null | False |
| 43-A-2-PR | {'success': 200} | 200 | 86.5798 | 86.5798 | 44.109 | null | False |
| 44-N-2-PR | {'success': 100} | 100 | 22.3516 | 22.3516 | 43.688 | null | False |
| 45-N-2-PR | {'success': 100} | 100 | 437.3407 | 437.3407 | 1.744 | null | False |
| 46-B-2-D | {'success': 12} | 12 | 2.1027 | 2.1027 | 319.394 | 5.620 | False |
| 47-B-2-P | {'success': 12} | 12 | 2.1128 | 2.1128 | 326.707 | 20.677 | False |
| 48-H-2-RR | {'success': 120} | 90 | 15.0000 | 18.8844 | 67.251 | 67.251 | False |
| 49-H-2-LI | {'success': 120} | 110 | 18.3333 | 19.8863 | 25.408 | 25.408 | False |
| 50-H-2-RR | {'success': 120} | 90 | 45.0000 | 50.1758 | 65.912 | 65.912 | False |
| 51-H-2-LI | {'success': 120} | 112 | 56.0000 | 51.6674 | 26.306 | 26.306 | False |
| 52-Q-2-P | {'success': 60, 'http_rejection': 60} | 56 | 28.0000 | 28.2913 | 24.893 | 24.893 | False |
| 53-Q-2-P | {'success': 74, 'http_rejection': 46} | 35 | 17.5000 | 31.6882 | 254.157 | 254.157 | False |
| 54-R-2-D | {'success': 12} | 12 | 2.0190 | 2.0190 | 986.134 | 35.852 | False |
| 55-R-2-P | {'success': 12} | 12 | 1.9166 | 1.9166 | 1042.055 | 38.238 | False |
| 56-T-2-D | {'success': 200} | 200 | 716.9578 | 716.9578 | 3.945 | null | False |

## 原始证据、资源和限制

全部终态（含预热）：`{'success': 7265, 'http_rejection': 325}`。239次子进程start/reaped闭合，采样进程峰5；实际目录14124027 bytes，预算计费`{'direct': 197656576, 'managed': 12108355, 'emergency': 79196}`。

实际账本采样最大间隔0.120247s，资源采样最大间隔1.118998s；采样峰不代表瞬时真峰。每cell排空FD回基线、RSS≤B+32MiB、活动账清零，B代理三次formal pause/resume及快流推进均由原始drain/状态校验。

R固定b7481/Qwen资产只读校验，双CPU各2线程共享主机；每实例generation task的started/released/timed在三边界实测0→1→7，分别12正式中6/6。P逐ID目标未观测，不按实例归因客户端延迟；少量真实样本仅min/median/max，不外推生产/GPU。

N仅新合成后端NODELAY off/on，原P1约44ms限制没有产品修复；A/N原始后端accept与request及实际getsockopt保留。无重试/额外推理探针，metrics GET不计推理attempt。

完整原始证据位于build-local/builder/v0.4-s1/evidence/run-002，身份/独立复算与命令见Builder001；本结果不替代Reviewer独立完整矩阵。

## 独立验收与最终比较（2026-10-21 追加）

上文保留Builder001当时的数据与待审查状态；当前已由[Reviewer002](../../reviewer/reports/V0.4/S1-report-002.md)独立PASS、[Leader006](../../leader/reports/V0.4/S1-report-006.md)收口，累计4/4、无债。Builder原run-002按产品、发压和测量binary精确身份复用；仅两测试源及六测试binary变动。Reviewer另行完整执行一次run-001，未复用或拼接Builder性能样本。

| 观察 | Builder run-002 | Reviewer run-001 |
| --- | --- | --- |
| 完整矩阵 | 57cell / 7590ID / 407.07s | 57cell / 7590ID / 388.725520s |
| 正式7104分类 | 6788成功 / 316 queue_full | 6783成功 / 321 queue_full |
| 预热486分类 | 477成功 / 9 queue_full | 477成功 / 9 queue_full |
| H20 / H60 / Q60有效配对 | 各3/3 | 各3/3 |
| H20 LI−RR goodput三点（req/s） | 3.1667 / 3.3333 / 3.3333 | 3.333333 / 3.333333 / 3.333333 |
| H60 LI−RR goodput三点（req/s） | 11 / 11 / 11 | 11 / 11 / 11 |
| Q60 count8−count0 goodput三点（req/s） | −10.5 / −13 / −10.5 | −17 / −13 / −16.5 |
| T首单/双/末单吞吐（req/s） | 1319.089114 / 2159.913121 / 716.957847 | 1294.710178 / 2157.664633 / 1149.669975 |
| machine_drift | true | false |
| generator_sensitive / client_cpu_at_least_085 / suspected_generator_limit | 均true | 均true |

两角色全部计划ID闭合，无not_sent/not_started、超时或协议/传输错误；拒绝与SLO未达标保持原分母。队列增加成功数未必增加达标goodput，不能用HTTP成功替换SLO收益；跨角色不合并样本或估计置信区间。两角色仍受发压与共享CPU限制，**策略因果收益及网关容量未证实**；Reviewer无machine_drift不抹去Builder漂移。

Reviewer B正式pause/resume为84/84、74/74、84/84，每波快流先于慢流完整结束；六R cell每个12正式/2预热全成功，固定双CPU实例聚合generation计数各0→1→7。R-P走正式gateway，无逐ID后端归因，小样本不报尾分位。A/PR C1约22.5req/s、N off约22.5–22.8/on约708–839req/s仅本次合成观察，未改网关或证明P1普遍根因。

Reviewer三套完整CTest各21/21；各cell排空账本全零、FD回基线，最大Gateway排空RSS5406720bytes、相对预热最大增长1310720bytes，低于32MiB门槛。239个自有子进程全部回收；direct197656576/managed12094171/emergency79368bytes均在预算内。采样目标非硬实时，最大实际间隔0.120139s/1.010980s；不把采样峰当瞬时真峰。

独立逐ID复算、57cell全表与三重复分布见Reviewer002；原始数据位于`build-local/reviewer/v0.4-s1/evidence/run-001`，自写`Audit.py`/`audit.json`、`FinalAudit002.py`/`final-audit002.json`和原始文件清单同角色evidence目录。旧FinalAudit按命令参数alias误分类RSS的离线输出保留，当前采用按可执行basename分类的FinalAudit002值，未重跑/更改原始矩阵。完整原始文件清单SHA256为`1f20cdc79c0e500a4b423cff91ebc9fb66f1b3da4ffbb83ec135db043a6223a5`。build-local证据为本机保留，不随Git文档自动发布。
