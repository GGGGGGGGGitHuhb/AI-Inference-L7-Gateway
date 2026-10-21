# V0.4/S1 独立验收报告002

2026-10-20，Reviewer（Athena）。**PASS；F-001关闭，累计返工4/4，无剩余发现或待接受债务。** 两次新增用户授权、rework002/003/004及Stop001/002全部保留。原Reviewer001的Release失败没有子条件值，首次根因仍不能回溯确认；本报告接受的是纠正后的观察契约、确定性迟滞/生命周期证据和完整独立回归，绝不把旧失败改写为环境抖动或已复现根因。

独立正式run-001一次完成57/57，7590唯一ID，退出0、388.725520s。性能结论限定于本次环境：H/Q有效到达配对满足门槛，但发压敏感与客户端CPU限制触发，**策略因果收益及网关容量未证实**。交Leader同步收口；协调者随后本地提交、不推送，不启动S2。

## 权威、路线及范围

读取原Approved设计/审查、rework001–004、Leader005、Stop001/002、Builder002及原Reviewer001。最新rework004 SHA为f86734b600db29be1275385a8e348431c6a831cb149b80df93015763c448a586，Leader005为b4a0252509b33d5fcf48d1cf422ea50b38e67f43079f86c23c0d97284c7f90ff，Builder002为c21269b692b09fd95ce8b76e92445ae03987f8554dbc7132d6e99ee470f8b0b3。新4/4来自两次明确新增授权，不追溯重置旧额度；本轮没有第五轮纠正。

重新读取agent-execution-route，复用personal-cpp-standards完整规则及正反例、plan-project-docs Reviewer模板；无项目Reviewer指南，使用模板回退。原生WSL，`/bin/bash login=false`，cwd=/home/power/projects/AI-Inference-L7-Gateway，分支codex/v0.4-s1-performance-baseline，HEAD44266088f5d93880983eb58a27117b796af7075b。角色目录`build-local/reviewer/v0.4-s1/{tmp,cache,evidence,debug,release,asan}`，构建/Python/测试显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；socket/LSan首次窄权限，不禁检测器、不下载、不调系统、不跑P1/旧长soak。

以下E指该角色evidence。仅创建独立证据和本报告，没有修改实现、测试、Builder/Leader材料或旧报告。正式测量在Builder停止之后独立进行，使用自有二进制/端口/PID/目录，资产只读共享；没有复用Builder样本。

## F-001及后续测试失败闭合

审查两测试完整diff与资源owner：Backpressure每cycle在实际上游事件处理返回、下游写之前取本session triggerPending/token，要求真实high触发、pause累计恰增1与token注销；随后poll允许合法高低水之间状态。保留三种HTTP定界、两轮暂停恢复、暂停期间不读、旧token无效、恢复新token、快请求、RST/信号停止、正文与排空保障。没有直接赋值paused/pending/计数，也没有借用历史全局峰值替代本cycle证据。

新增Runtime用实际FakeIo/SessionIo方法构造未完整chunk响应，独立三套原始日志均显示high32842→middle16384→low+1=8193仍paused/token0、不新增上游读取；到恰8192真实resume，累计resumes增1、新token非零且不同旧token。旧token分派不读、新token可读，五个非法快照负控全部拒绝。纯快照负控仅补充真实方法路径，未替代它。

SSE验证显式kAllowEventStream，按≤16KiB wire片段和consumedBytes前进、立即复制bodyFragment；三片16384/16384/172消费全wire32940，decoded32769，精确32768个h加z，message().body为空且HTTP状态kComplete，没有用finishInput补造终态。默认buffered负控明确unsupported_stream。rework002模式错误与rework003资源时点失败原日志、Stop原文仍保留。

资源层次已由rework004 A日志和本轮独立成功用例共同证实：finished但对象仍活时reservation有效且reserved恰16777216，streamCapacity/pending/paused、stream/upstream lease、token/timer/pool全零；完整正文/负控后销毁session，budget/loop/pool仍活，reserved及其余资源全零，FD13→12，重复空reset不重复归还。异常诊断守卫只在原异常传播后清理并取证，不在断言前提前reset洗零；共用Fixture默认行为和产品生命周期未变。

**F-001关闭边界**：原Release联合断言哪一项失败仍未知；已纠正不符合迟滞状态机的观察要求，并完整独立验证high触发、合法迟滞、low恢复、协议正文与owner生命周期，而不是凭一次旧binary诊断通过接受。

## 实际命令与独立验证

每预设运行一次`cmake --build build-local/reviewer/v0.4-s1/MODE -j4`，然后一次`ctest --test-dir build-local/reviewer/v0.4-s1/MODE --output-on-failure`。本轮没有额外循环定向复测。

| 执行 | 结果 | 证据 |
| --- | --- | --- |
| Debug修后完整CTest | 21/21，42.80s，退出0 | E/build-debug-r4.log、ctest-debug-r4.log、last-test-debug-r4.log |
| Release修后完整CTest | 21/21，38.89s，退出0 | 对应release-r4三日志 |
| ASan+UBSan修后完整CTest | 21/21，61.44s，退出0，无sanitizer错误 | 对应asan-r4三日志 |
| C++格式/人工 | 两测试clang-format-18 dry-run通过，类内/相邻函数空行、职责分组、局部guard与借用寿命人工通过 | E/format-r4.log；18.1.3 |
| 唯一独立完整矩阵 | 57/57、7590ID、388.725520s、退出0 | E/run-001/、run-001.log、run-001.exit |
| 自写逐ID完整复算 | 全分母、时钟/SLO、分位/goodput、配对、资源/预算、实例关联与进程闭合通过 | E/Audit.py、audit.json、audit.log |
| 资产/资源/原始身份 | 固定资产/库/许可与全部原始文件哈希通过 | E/FinalAudit002.py、final-audit002.json/.log、run-001-raw-sha256.json |

正式命令：

```bash
python3 tests/experiments/RunExperiments.py \
  --host build-local/reviewer/v0.4-s1/release/ExperimentRuntimeHost \
  --gateway build-local/reviewer/v0.4-s1/release/ai-inference-gateway \
  --assets build-local/integration/v0.2-s3 \
  --output build-local/reviewer/v0.4-s1/evidence/run-001
```

完整三套通过后才执行该命令。Reviewer以前未启动正式矩阵，本次就是一次run-001；未重测挑优/补样本/修改到达或SLO。Builder旧run-001失败、修后run-002及本Reviewer数据互不拼接。

Reviewer001已完成持久短控及自写独立控制按实验源码、测量binary不变明确复用：7条整体迟到真实Worker批次全部not_sent且无补发；200首content后非法chunk为protocol_failure；两个进程与多文件受管预算触限非零并保留失败record/回收；真实同formal同四元组两连接唯一映射，逆序输入仍正确，重叠host拒绝。证据E/IndependentChecks.py、independent-controls.json/.log、detectors-001。原相关19PID回收记录保留。本轮全CTest仍包含ExperimentDetectors，但没有谎称另行重跑这些自写独立控制。

## AC01：冻结计划、分类与统计

E/Audit.py不导入项目Statistics/Analyze或Builder审计；独立构造57cell顺序和组合、逐ID加载原始JSON并检验唯一性/请求hash、预热/正式隔离。正式7104=6783success+321个503/queue_full；预热486=477success+9个503/queue_full。全7590无not_sent/not_started、HTTP timeout、transport/protocol failure、client deadline或interrupted。成功正文长度/hash、完整HTTP及流content/finish/DONE复核，拒绝不算成功或SLO子集。

每ID时钟单调，H/Q scheduled=t0+i/rate，开环SLO从scheduled算、发送后时延另列；offered和scheduled-goodput窗口为120/rate，窗口后完成仍属于原ID。闭环从屏障到最后closed计吞吐、SLO从connect调用前dispatch起算。独立重算所有cell/phase的min/median/max、nearest-rank门槛（n20/p50、n100/p95、n1000/p99）、SLO计数、goodput、completion throughput、dispatch/send lag及长短/快慢分组，与原始汇总精确一致；零样本null，不把缺记录当0。三重复各自计算并报三点及median[min,max]，不池化、不称置信区间。

## AC02：连接成本、N诊断与真实背压

A/PC后端accept与request相等，PR预热和正式两个区间均实际accept<request；按后端请求ID集合核对成功请求、无重复或隐式重试。N逐请求getsockopt确认只有后端NODELAY变化，记录头/body实际写入时点。A/PR C1的达标goodput约22.5req/s，N off约22.5–22.8/on约708–839req/s；仍是本次有限诊断，**未改网关，不宣称P1问题已修复或已证明普遍根因**。实际E2E分位/三重复见audit.json及下表。

B代理三次**正式相对预热**pause/resume增量分别84/84、74/74、84/84，且每波快流在慢流结束前取得HTTP完整终态；不是借预热pause冒充覆盖。四MiB原始正文逐字hash/长度一致，慢读socket实际缓冲与时间保留。B的快流SLO存在未达标属于真实负面结果，没有删样本；每cell完整排空。

## AC03：开环策略与排队

H20、H60与Q60的有效配对均3/3，两边均非arrival_limited，满足“至少一个H速率及Q各至少2对”而非仅靠限制说明放行。全部计划施加且send/dispatch lag原样保留，未按完成补发。队列等待使用唯一关联host Session的enqueued/dispatched，未派发不补0，不跨进程相减；按同四元组、双方各自生命周期顺序唯一映射，数量/非重叠/消费守恒独立重算。

LI−RR scheduled-goodput在20/s三次均+3.333333req/s，在60/s三次均+11；count8−count0三次−17/−13/−16.5req/s。Q未越global2/per1/count0或8/bytes65536；321正式queue_full保留。队列增加等待并降低本SLO下达标goodput，是允许的负面基线，不能用HTTP成功数代替达标收益。

T首单/双/末单完成吞吐分别1294.710178/2157.664633/1149.669975req/s。本次machine_drift=false；generator_sensitive=true、client_cpu_at_least_085=true、suspected_generator_limit=true。虽到达有效对充足，相关代理/策略**因果容量结论仍未证实**，不归因GIL，不外推独占硬件收益。

## AC04：真实CPU交叉观察

六个R cell分别12正式/2预热，全成功。只读复核server/model/archive固定SHA、491400032bytes模型、归档中部署库/许可证及Qwen LICENSE SHA832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e；版本以固定b7481服务器身份锚定，没有下载替换。

每cell自有双CPU实例各threads2/batch2/ctx2048/parallel1/GPU0；每实例generation task启动/释放/timing集合在三次排空边界0→1→7，metrics GET不新增生成计数。正式P是ai-inference-gateway而非host；P未提供逐ID后端归因，按Leader澄清仅报告聚合分配，不凭RR推断。R每重复12成功不足尾分位门槛，仅min/median/max；同机CPU/cache/slot等待使D/P差异不能当纯代理成本。

## AC05：资源、预算、身份及清理

每host末态sessions/reserved/capacity/pending/paused/timers/upstreams/leased/idle/pool_total/inflight/queue/bytes全零；每live drain FD回相同基线。Gateway最大排空RSS5406720bytes、最大较对应预热基线上升1310720bytes，满足B+32MiB；后端采样峰614064128bytes<2GiB。startup空backend_peaks只允许首次无活动前缀，之后必须非空，不将缺活动峰默认0。实际账本最大间隔0.120139s、资源1.010980s，100ms/1s为目标而非硬实时；采样峰不作瞬时真峰。

运行期1GiB三池审查及正式账本相符：direct197656576bytes（377条直接路径×512KiB）、managed12094171bytes、emergency79368bytes，各在512/448/64MiB内；每个直接文件小于硬限，全部Python写前序列化锁内扣账、覆盖不退，子进程只有有界IPC由父统一保存。全部7590摘要≤8KiB，host每ID≤16转移且每条≤1KiB，state≤4KiB。固定plan finally闭合，没有隐藏缺样本/截断成功。

239个自有子进程start/reaped一一配对、exit0且/proc不存在；由事件计算含父峰5进程，低于8，采样线程均≤256。正式父命令退出0，没有模型服务遗留。

FinalAudit第一版离线RSS分类错误把命令参数alias gateway-qwen也当gateway角色，导致后台RSS被计入Gateway项；原脚本/输出FinalAudit.py、final-audit.json/.log保留。FinalAudit002严格按可执行文件basename分类纠正后结果如上。仅Reviewer离线显示分类修正，原始样本、工具、产物及正式run未改/重跑；核心逐ID统计Audit.py首次执行通过。不得引用第一版错误的Gateway RSS值。

E/identity-r4.json逐项确认仅两测试源、三预设各BackpressureTests/RuntimeTests共6binary变化，45项测量/其他产物与212项保护文件不变；旧Reviewer001 SHA仍01297ec01a22e62ea29599de220b51cc489387faf0d26737641c450a8e7f70fa。完整118源清单E/source-r4-sha256.json SHA70d541db05eda72dff539f461dd059c729cdcc89eaaf58587e6e61250ff38df6；51独立产物清单E/binaries-r4-sha256.json SHAff3c39582cbd2fa0a7ff8f9cf3ac30114c6c521a8c89010272419f1a28de276c。正式8439文件清单E/run-001-raw-sha256.json SHA1f20cdc79c0e500a4b423cff91ebc9fb66f1b3da4ffbb83ec135db043a6223a5。

环境为Linux6.6.87.2 WSL2 x86_64/glibc2.39，20逻辑CPU、affinity0–19；机器负载、逐PID CPU/FD/RSS/context-switch、实际配置及源/产物/输入hash见run-001/manifest.json和resources.jsonl。固定环境身份不代表独占资源。

## 全57cell独立复算表

下表仅正式分母，拒绝不算success，SLO是success内子集；goodput/completion单位req/s，E2E为起点按开闭环契约计算的秒。所有TTFT、发送后时延、长短/快慢拆分、分位数和预热原值在E/audit.json，未省略其原始记录。

| cell | success/reject | SLO | goodput | completion/s | E2E min/median/max (s) | arrival_limited |
|---|---:|---:|---:|---:|---|---|
| 00-T-0-D | 200/0 | 200 | 1294.71018 | 1294.71018 | 0.001068/0.002289/0.007305 | False |
| 01-T-1-D | 200/0 | 200 | 2157.66463 | 2157.66463 | 0.002009/0.003051/0.004705 | False |
| 02-A-0-D | 200/0 | 200 | 730.44046 | 730.44046 | 0.000655/0.001045/0.002559 | False |
| 03-A-0-PC | 200/0 | 200 | 501.30357 | 501.30357 | 0.001104/0.001635/0.003257 | False |
| 04-A-0-PR | 200/0 | 200 | 22.48183 | 22.48183 | 0.003615/0.043637/0.048376 | False |
| 05-A-0-D | 200/0 | 200 | 1475.36503 | 1475.36503 | 0.000820/0.001617/0.005793 | False |
| 06-A-0-PC | 200/0 | 200 | 1406.03137 | 1406.03137 | 0.001362/0.002135/0.004338 | False |
| 07-A-0-PR | 200/0 | 200 | 89.63721 | 89.63721 | 0.003649/0.043447/0.049972 | False |
| 08-N-0-PR | 100/0 | 100 | 22.77277 | 22.77277 | 0.003230/0.043637/0.048033 | False |
| 09-N-0-PR | 100/0 | 100 | 838.94257 | 838.94257 | 0.000657/0.000830/0.002789 | False |
| 10-B-0-D | 12/0 | 12 | 2.16170 | 2.16170 | 0.122389/0.142083/1.847308 | False |
| 11-B-0-P | 12/0 | 12 | 2.16015 | 2.16015 | 0.172002/0.188710/1.847590 | False |
| 12-H-0-RR | 120/0 | 90 | 15.00000 | 18.88847 | 0.022189/0.063275/0.403611 | False |
| 13-H-0-LI | 120/0 | 110 | 18.33333 | 19.89183 | 0.022244/0.022777/0.404448 | False |
| 14-H-0-RR | 120/0 | 90 | 45.00000 | 50.29171 | 0.022112/0.063244/0.403629 | False |
| 15-H-0-LI | 120/0 | 112 | 56.00000 | 51.74440 | 0.021869/0.022846/0.402606 | False |
| 16-Q-0-P | 60/60 | 56 | 28.00000 | 28.31025 | 0.021936/0.022366/0.402596 | False |
| 17-Q-0-P | 72/48 | 22 | 11.00000 | 31.23970 | 0.023558/0.291365/0.632928 | False |
| 18-R-0-D | 12/0 | 12 | 2.77304 | 2.77304 | 0.682262/0.711546/0.791038 | False |
| 19-R-0-P | 12/0 | 12 | 2.91479 | 2.91479 | 0.659066/0.688669/0.710455 | False |
| 20-A-1-PR | 200/0 | 200 | 22.55150 | 22.55150 | 0.005027/0.043653/0.050978 | False |
| 21-A-1-PC | 200/0 | 200 | 561.85880 | 561.85880 | 0.001013/0.001455/0.002690 | False |
| 22-A-1-D | 200/0 | 200 | 734.62421 | 734.62421 | 0.000646/0.001011/0.002486 | False |
| 23-A-1-PR | 200/0 | 200 | 89.34173 | 89.34173 | 0.004164/0.043701/0.048646 | False |
| 24-A-1-PC | 200/0 | 200 | 1393.59775 | 1393.59775 | 0.001434/0.002142/0.005626 | False |
| 25-A-1-D | 200/0 | 200 | 1574.87871 | 1574.87871 | 0.000939/0.001557/0.004513 | False |
| 26-N-1-PR | 100/0 | 100 | 717.56284 | 717.56284 | 0.000714/0.001082/0.003419 | False |
| 27-N-1-PR | 100/0 | 100 | 22.53272 | 22.53272 | 0.003338/0.043728/0.051149 | False |
| 28-B-1-P | 12/0 | 12 | 2.15929 | 2.15929 | 0.161065/0.169696/1.847771 | False |
| 29-B-1-D | 12/0 | 12 | 2.15820 | 2.15820 | 0.124512/0.147323/1.850114 | False |
| 30-H-1-LI | 120/0 | 110 | 18.33333 | 19.88953 | 0.022115/0.023300/0.407158 | False |
| 31-H-1-RR | 120/0 | 90 | 15.00000 | 18.88908 | 0.022262/0.063503/0.403969 | False |
| 32-H-1-LI | 120/0 | 112 | 56.00000 | 51.71827 | 0.022011/0.023944/0.403496 | False |
| 33-H-1-RR | 120/0 | 90 | 45.00000 | 50.28773 | 0.022047/0.063816/0.405155 | False |
| 34-Q-1-P | 74/46 | 30 | 15.00000 | 33.06777 | 0.023092/0.266002/0.637302 | False |
| 35-Q-1-P | 60/60 | 56 | 28.00000 | 28.30018 | 0.021987/0.022886/0.403360 | False |
| 36-R-1-P | 12/0 | 12 | 2.92386 | 2.92386 | 0.645412/0.679810/0.722055 | False |
| 37-R-1-D | 12/0 | 12 | 3.05589 | 3.05589 | 0.641362/0.650707/0.673262 | False |
| 38-A-2-PC | 200/0 | 200 | 428.24269 | 428.24269 | 0.001175/0.001951/0.003695 | False |
| 39-A-2-D | 200/0 | 200 | 792.09564 | 792.09564 | 0.000642/0.000987/0.002402 | False |
| 40-A-2-PR | 200/0 | 200 | 22.64891 | 22.64891 | 0.003427/0.043643/0.050495 | False |
| 41-A-2-PC | 200/0 | 200 | 1426.40244 | 1426.40244 | 0.001308/0.002072/0.005451 | False |
| 42-A-2-D | 200/0 | 200 | 1501.86434 | 1501.86434 | 0.000841/0.001606/0.004157 | False |
| 43-A-2-PR | 200/0 | 200 | 89.86368 | 89.86368 | 0.002551/0.043587/0.051499 | False |
| 44-N-2-PR | 100/0 | 100 | 22.68352 | 22.68352 | 0.003082/0.043664/0.047744 | False |
| 45-N-2-PR | 100/0 | 100 | 708.32089 | 708.32089 | 0.000756/0.001070/0.002891 | False |
| 46-B-2-D | 12/0 | 12 | 2.15600 | 2.15600 | 0.117697/0.149234/1.851654 | False |
| 47-B-2-P | 12/0 | 12 | 2.15055 | 2.15055 | 0.166604/0.189354/1.862876 | False |
| 48-H-2-RR | 120/0 | 90 | 15.00000 | 18.88045 | 0.022268/0.063305/0.405522 | False |
| 49-H-2-LI | 120/0 | 110 | 18.33333 | 19.89207 | 0.022199/0.023289/0.403695 | False |
| 50-H-2-RR | 120/0 | 90 | 45.00000 | 50.29419 | 0.022143/0.063742/0.403644 | False |
| 51-H-2-LI | 120/0 | 112 | 56.00000 | 51.74236 | 0.021974/0.023046/0.402895 | False |
| 52-Q-2-P | 60/60 | 56 | 28.00000 | 28.29935 | 0.022159/0.022698/0.403348 | False |
| 53-Q-2-P | 73/47 | 23 | 11.50000 | 28.93812 | 0.022484/0.278073/0.672521 | False |
| 54-R-2-D | 12/0 | 12 | 2.87529 | 2.87529 | 0.666383/0.696404/0.714449 | False |
| 55-R-2-P | 12/0 | 12 | 2.84841 | 2.84841 | 0.654222/0.697489/0.765427 | False |
| 56-T-2-D | 200/0 | 200 | 1149.66998 | 1149.66998 | 0.001276/0.002500/0.006227 | False |

## 三重复达标goodput（req/s）

每行保留实际执行顺序三点，不跨重复合并；median[min,max]为描述统计。

| 组合 | 三点 | median[min,max] |
|---|---|---|
| A/D/C1/rate0/q0/nodelayFalse | 730.440456, 734.624205, 792.095643 | 734.624205[730.440456,792.095643] |
| A/PC/C1/rate0/q0/nodelayFalse | 501.303574, 561.858803, 428.242687 | 501.303574[428.242687,561.858803] |
| A/PR/C1/rate0/q0/nodelayFalse | 22.481828, 22.551502, 22.648912 | 22.551502[22.481828,22.648912] |
| A/D/C4/rate0/q0/nodelayFalse | 1475.365033, 1574.878707, 1501.864339 | 1501.864339[1475.365033,1574.878707] |
| A/PC/C4/rate0/q0/nodelayFalse | 1406.031370, 1393.597749, 1426.402441 | 1406.031370[1393.597749,1426.402441] |
| A/PR/C4/rate0/q0/nodelayFalse | 89.637205, 89.341728, 89.863679 | 89.637205[89.341728,89.863679] |
| N/PR/C1/rate0/q0/nodelayFalse | 22.772769, 22.532725, 22.683516 | 22.683516[22.532725,22.772769] |
| N/PR/C1/rate0/q0/nodelayTrue | 838.942573, 717.562839, 708.320893 | 717.562839[708.320893,838.942573] |
| B/D/C4/rate0/q0/nodelayFalse | 2.161705, 2.158199, 2.155998 | 2.158199[2.155998,2.161705] |
| B/P/C4/rate0/q0/nodelayFalse | 2.160154, 2.159289, 2.150548 | 2.159289[2.150548,2.160154] |
| H/RR/C0/rate20/q0/nodelayFalse | 15.000000, 15.000000, 15.000000 | 15.000000[15.000000,15.000000] |
| H/LI/C0/rate20/q0/nodelayFalse | 18.333333, 18.333333, 18.333333 | 18.333333[18.333333,18.333333] |
| H/RR/C0/rate60/q0/nodelayFalse | 45.000000, 45.000000, 45.000000 | 45.000000[45.000000,45.000000] |
| H/LI/C0/rate60/q0/nodelayFalse | 56.000000, 56.000000, 56.000000 | 56.000000[56.000000,56.000000] |
| Q/P/C0/rate60/q0/nodelayFalse | 28.000000, 28.000000, 28.000000 | 28.000000[28.000000,28.000000] |
| Q/P/C0/rate60/q8/nodelayFalse | 11.000000, 15.000000, 11.500000 | 11.500000[11.000000,15.000000] |
| R/D/C2/rate0/q0/nodelayFalse | 2.773041, 3.055891, 2.875291 | 2.875291[2.773041,3.055891] |
| R/P/C2/rate0/q0/nodelayFalse | 2.914791, 2.923859, 2.848412 | 2.914791[2.848412,2.923859] |

## 最终交接

所有AC/RV满足，F-001及新增测试模式/生命周期校验问题独立关闭，无债；原首次Release子条件未知、旧FAIL/Stop历史全部保持。累计4/4，未动产品或放宽门槛，无第五轮返工。独立构建/负载已结束，Reviewer停止；交Leader同步文档及阶段收口，协调者完成本地提交、不推送，S2需另行设计。
