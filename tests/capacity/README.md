# V0.6/S1 有界容量工具

仅标准库 Python 3.11+、本仓 Release Gateway 和只读 L4 源构建；不改变产品行为。批准依据为 `docs/leader/designs/V0.6/S1-design.md`。E1 是探索，不是正式容量。正式72-cell矩阵必须由Leader先冻结清单；正式CLI为 `Run.py --mode formal --manifest docs/performance/V0.6/S1-manifest.json`，另传output/gateway/l4lb路径；其他CLI配置覆盖均拒绝。正式先验证Frozen状态、72唯一组合、按rate-index+repeat旋转、参数/SLO/预算一致、工具hash与选档证据hash、实际两仓源码不变，再保存清单hash与所有未来cell计划。正文/协议损坏停止采集，不删除已发生cell。

现有证据目录和冻结清单已用于本轮验收，不得覆盖或重新发压。下文命令仅展示历史路径与用法；新实验须使用新的证据根目录、校准和批准清单。返工及续采章节是本轮历史记录，不是通用恢复授权。

## 运行

原生 WSL，在仓库根设置角色目录；每个角色只用自己的证据与构建。所有工具命令设置 TMPDIR/TMP/TEMP 指向角色tmp，XDG_CACHE_HOME 指向cache，PYTHONPYCACHEPREFIX 指向cache/pycache。初次创建这些目录。以下Builder示例仅示意参数路径，Reviewer使用自己的根。

```sh
python3 tests/capacity/Environment.py --output build-local/builder/v0.6-s1/evidence --gateway build-local/builder/v0.6-s1/gateway/ai-inference-gateway --l4lb build-local/builder/v0.6-s1/l4lb/bin/l4lb
python3 tests/capacity/SelfTest.py
python3 tests/capacity/Run.py --mode explore --output build-local/builder/v0.6-s1/evidence/run --gateway build-local/builder/v0.6-s1/gateway/ai-inference-gateway --l4lb build-local/builder/v0.6-s1/l4lb/bin/l4lb
python3 tests/capacity/Analyze.py build-local/builder/v0.6-s1/evidence/run/E1-A-G-60
```

`Negative.py`接收同样output/gateway/l4lb，运行timeout、bad_body、overload（同时无槽漏发）三个诊断cell。`InterruptTest.py`接收同样参数及唯一`--id`，在真实在途请求中向自身控制器发TERM，验证所有ID终态和子进程回收。故障负控用diagnostic额度；失败也计数。测试不得与其他角色同时发压。

单点控制：`Run.py --mode cell --id 唯一ID --kind E2 --path B|G|M|L --workload A|S --rate N --warm 2 --duration 5`，另接相同路径参数。`--workers 1|2`、`--backends 1|2`、`--capacity 32|64`、`--reuse`、`--nodelay 0|1`仅用于Leader认可的单变量控制；采用为正式条件须重新校准候选档。客户端默认总槽128，各worker均分；不追补迟到或漏发。

## 负载与资源

A固定1024B JSON；S固定16KiB SSE，16段、相邻目标2ms。ID由cell、phase、整数index构成；cell最长48个ASCII字符。每请求新下游连接、Connection close；主曲线上游max_idle=0，后端同时实现persistent HTTP以支持后续复用控制。

G/M/L聚合连接、上游池、全局/每backend准入均32（可控64）；M/L每实例均分。逻辑会话预约按产品16MiB/session，聚合512MiB（64为1GiB），并非已分配RSS。每实例队列0。B与代理路径使用相同后端集和客户端槽；未固定CPU quota或专核，所有affinity原始值保存，结果仅限同机拓扑观察。

每cell在任何子进程启动前写累计ledger，并预留45s活动额度；异常不重置，未收口的running ledger阻止新cell。E1最多28、E2最多8、正式最多72、diagnostic最多12；角色总数120、累计活动90分钟。每cell全活动（包括setup、健康等待、drain）绝对45s；清理仅自有PID，TERM一次、最多5s后KILL/wait。输出目录重复拒绝。

每个普通文件最多1MiB；逐ID记录、采样和日志分片，L4日志按字节读块轮转，跨文件残行在审计时拼接。文件名前缀区分数据与日志；日志捕获在线程中，不阻塞asyncio生成器/后端事件循环。总预算2GiB、预留16MiB收口池；每cell reservation为：

```
N = rate * (warm + duration)
N * (512 + 192 * backend_workers + (256 if L else 0)) + 3MiB
```

客户端每writer按ceil(N/workers)+2个ID分配，每条512B硬限、另64KiB；后端每writer N*192B+64KiB、每条192B硬限；L4日志N*256B+128KiB、其他进程日志各64KiB、采样2MiB，其余配置/结果/终态占固定余量。行超限抛错，保留首错，不截断字段伪造完整记录。启动实例数受限≤6，子进程AS限128MiB和FD600；采样每约100ms检查控制器（含capture线程）和全部子进程合计RSS≤1GiB、FD≤2048，超限停止。采样峰值并非连续真实峰值；主机其他进程未计入角色预算，但E0记录系统空闲信息。

## 原始记录与口径

`spec.json`保存完整确定性计划（索引范围包含未来未执行ID），`client-W-NNNN.jsonl`每行数组字段顺序见`Common.COLUMNS`：id,phase,scheduled,dispatch,connect,send,wire,body,http,eof,closed,outcome,status,tx,rx,digest,error。时间为同机monotonic ns，未发生字段null。每个计划ID恰一个终态；非成功也保留已入队发送、收到字节。backend逐请求记录[id,connection,begin,end,rx,tx,outcome]，summary另记accept数。正文逐字节与按ID构造的期望比较后保存SHA256，不把数百万正文留在内存。

wire/body/http是应用观察时间，并非NIC时间戳；http为完整HTTP framing解析完成，EOF和close单列。E2E SLO以scheduled到http为准，A≤100ms，S≤250ms且首body≤50ms。此前V0.5 http使用最后recv观测，本工具使用完整解析观测，两者边界不同，不能直接减值声称产品延迟变化。所有正式窗口计划ID均为分母，排空期内完成且自身SLO达标的请求计入goodput；除以固定窗口秒数，另报实际完成吞吐。

P50/P95/P99至少20/100/1000成功样本；生成器门槛not_sent≤1%、dispatch lag P95≤5ms。HTTP503为拒绝，不是正文/协议损坏；会降低goodput。预热与测量正文损坏均使cell正确性不成立。客户端或后端tx是asyncio transport入队字节，不是内核确认sent；失败时不能据此强制三段字节相等。L4实际sent从完整session日志核对；全部成功时客户端入队/接收与L4 sent严格相等。未采包，不宣称真实包量/NIC利用率。

`resources-*.jsonl`保存每个PID及线程ticks、RSS、FD、affinity和实际采样起止时间。结果保留真实CPU窗口、HZ与一tick误差、每个忙线程core，不以20核平均数掩盖饱和。捕获read等待时间不是产品阻塞时间；capture_write_ns及线程CPU单列，未测到产品pipe阻塞时保留未知。

## 当前实现边界

旧ThreadPool/ThreadingHTTPServer工具每并发需要线程且逐ID大字典/整批保留；新工具只保留有界在途任务、单条正文与流式文件。生成器/后端是否先饱和必须通过E1/E2证实，不能凭语言推断。

E0首次中断暴露Python server.wait_closed等待活跃连接，5秒后fixture被KILL，失败证据保留。修正为先取消并记录所有活跃请求，再等待server关闭；重测验证ID守恒与正常退出。E0早期smoke的closed口径不作选档，E1统一使用http SLO。


## 正式冻结前预算证明（Builder）

正式包含预热2,219,040请求，正式窗口1,929,600请求。A双worker按ID分片授予writer额度，不给两个worker各一份全量记录额度。

| 分配 | 硬界及依据 |
|---|---|
| client行 | 512B；48字符ASCII cell ID、phase/index、9个64位时间戳、固定终态、SHA256及受控异常；构造最长时间戳/ID负控通过，4096字符错误明确触发硬限且不写截断行 |
| backend行 | 192B；有界ID、连接序号、2时间戳、最多4096B请求/16KiB响应计数、固定终态；出界非零停服 |
| L4逐请求日志 | 256B覆盖accept与closure、回环端点、session序号、sent计数及固定reason/errno；额外128KiB供启动/健康/收口。异常日志超限明确infra failure，不能称产品容量失败 |
| 其余固定分配 | ≤3MiB/cell：采样2MiB；最多6进程日志(含L4 base)448KiB；客户端base128KiB；backend base64KiB；各配置/结果≤32KiB、client/backend summary≤16KiB，余量用于收口 |
| 整个72cell最坏 | 1,930,715,136B |
| 已保留证据 | 冻结前约121,875,693B，包含首次中断失败、原始E1和派生校正、控制及微基准，不复制大证据 |
| 剩余2诊断预留 | 15,753,216B（各A-G960、2+5秒） |
| 全run收口池 | 16,777,216B |
| 合计 | 2,085,121,261B < 2,147,483,648B；约62.36MB余量。运行前重新核算实际占用，不能照抄静态值 |

`Formal.run`要求完整72cell最坏分配、剩余diagnostic预留、累计实际证据和收口池同时可容纳才启动；每cell仍独立重新核算。角色E1/E2/负控失败已占44cell，正式后116cell；剩余6名额只有各子预算允许时才可用。活动已用约366s，加正式45s×72仍低于5400s。

9组无网络SelfTest包含L4 session行跨1MiB边界/截断失败、formal corruption立即停止且72计划保留。live负控中断首次失败和修复后记录均保留。正式主曲线采样间隔冻结0.1s，0.5s仅诊断。额外WriterBench只测标准库序列化/页缓存写开销，角色活动/证据计账，不当产品容量或实际磁盘持久化吞吐。

请求绝对期限从scheduled计5s；测量计划窗口结束后，最后一批在途请求最多再排空5s。请求终态落盘后另有最多2s的FD回归确认，它仍计入全cell45s活动上限；进程清理另有TERM5s、必要时KILL/wait的有限grace。资源排空不是仅凭“HTTP成功”推断。

冻结清单自然语言`HTTP framing and body validation observed complete`按REQ05作明确口径说明：`http`时间戳只在完整HTTP framing解析完成时采集；随后必须EOF及完整正文校验通过才成为success。该时间戳不包含随后正文校验CPU。数字SLO、成功条件和原始记录均未改变。

## Approved rework001：首停与唯一续采入口

首批正式第7项`F-A-L-1920-r0`在审计收口停止：原regex误认为L4 reason无空格，漏解析38条完整`shutdown SHUT_WR`结束行。原capture 5,898,202B完整，44,160 accepted/closed与双向字节均可守恒；真实transport_failure保持失败。

依据`docs/leader/reworks/V0.6/S1-rework-001.md`，当前parser对完整session行fullmatch，以明确` sent_c2b=`结束reason，校验端点/SID唯一性；未知session行直接失败。11组SelfTest含多词reason、重复/缺事件、端点不符、跨片/截断与受控前缀/指纹负控。

`Resume.py --output ... --gateway ... --l4lb ... --parent docs/performance/V0.6/S1-manifest-v1.json`只派生复审原7cell、不发压。输出`formal-reaudit-r2`，原输入SHA、原result/ledger快照/plan/provenance/binary身份与派生结果hash全部绑定；前6metrics须与旧结果相同，第7只允许精确的指定原审计错误。派生工具处理活动另计账。

Leader冻结v2、Reviewer核对并授权后，Builder使用`Run.py --mode resume --manifest docs/performance/V0.6/S1-manifest.json`及相同output/gateway/l4lb路径。入口仅接受固定的7项原前缀、6 complete+1 failed、全部实际spec及原始指纹吻合、全部进程原exit0、无running cell或auxiliary reservation、源/二进制不变、同72项顺序/参数/数字语义，随后仅发余65个新ID；任何不符拒绝。不重发原7项，不改failed状态，不覆盖最初formal-plan/provenance；独立写续采provenance。此入口不是通用resume。Reviewer使用v2的`--mode formal`从空的自有证据开始，同样验证v1 parent及相同矩阵。

## Approved rework002：退出读取边界与第二次唯一续采

正式第18项`F-S-M-480-r0`收口监控PermissionError首停。原197个正式窗口样本/19.884787034s资源窗口可复算；按冻结旧循环最后完整row后100ms等待，可能出错的下一轮最早在formal_end+83.714568ms、最后client.close+46.517916ms。原错误没有PID/操作/栈，不能命名已确认的退出竞争根因；只确认未截断正式窗口采样。

当前Monitor仅在资源读取失败后再次确认自有子进程已退出时跳过该退出样本；存活子进程/控制器PermissionError仍fatal。`monitor-events-*.jsonl`上限64KiB，保留time/PID/name/阶段/异常/调用栈和skip或fatal动作，计入原3MiB固定分配（最坏固定约2995KiB）。控制器task枚举只跳过已确认TID目录消失的ENOENT；活TID缺stat和PermissionError不吞。总CPU ticks仍权威，线程CPU仅在首末均存续的TID间计算。

Resume沿用同一CLI，仅再增加Approved rework002固定18前缀及两种精确已核对原错，余54全新ID；v1初始plan/provenance、v2首续采provenance和全部旧输入保留，v2工具源码按原hash另存角色证据。r3派生第18项明确标记sampling_coverage，不重发请求、不抹掉监控首错。进程集按冻结backends/workers/path推导精确名称、数目/PID唯一性及exit0/capture_error；S/B只有backend+单generator两进程也须完整核验，不能套用A双generator的最低3进程假设。

15组负控/自测覆盖已退出skip、存活/控制器fatal及取证、消失/存活TID边界、两个固定前缀和全部拓扑进程集。初次r3派生预检触发旧最低3进程假设，日志保留；该次无发压、无新增cell。若再遇无法安全恢复的未知采集错误，按Approved rework002停止并交付受限结论，不继续扩展恢复入口。

## Approved rework003与Builder收口

后续返工003依据第33项精确退出期事件补充有限确认：只有自有子进程PermissionError、实际now≥formal_end及request-drain/cleanup等允许窗口外phase同时满足，才无信号wait至多100ms且受剩余cell45s限制；实际取得退出码才skip，超时/窗口内/控制器仍fatal。原phase、wait与退出证据保留。17组自测覆盖实际时间、phase、退出/超时边界。固定33项前缀及三种明确原错复审后，v4只续39项新ID。

Builder最终72/72及12诊断均已完成，完整摘要为角色证据run/formal-summary-builder-complete.json，最终报告为docs/builder/reports/V0.6/S1-report-006.md。原始三个正式failed、旧33项受限摘要与39项未来计划快照保留历史，不代表当前仍未完成。全部结果仍需Reviewer独立复核，不凭Builder完成宣告阶段通过。

## Approved rework004：Reviewer独立复验续采

Reviewer从v4独立采集在第33项cleanup l4lb /proc/stat ENOENT、即时poll尚null首停。v5工具将PermissionError/FileNotFoundError/ProcessLookupError统一受实际窗口外、自有子进程及允许阶段门槛约束；仅实际退出才skip，窗口内或控制器即使poll退出也fatal。等待仍≤100ms及剩余cell期限，无信号、不改变正常采样。19组自测包括三类异常×7场景。

唯一新增profile为reviewer-v4-prefix33：原始plan/provenance直接绑定v4及Reviewer两个精确SHA，前32complete/第33唯一ENOENT failed；事件/result SHA与PID166168固定，不能套用Builder原33项。Reviewer在自有根执行Resume.py原derive参数另加--profile reviewer-v4-prefix33、--parent docs/performance/V0.6/S1-manifest-v4.json，生成formal-reaudit-r5。只有Leader冻结v5、Reviewer核对后才可Run --mode resume余39，不改原failed、不重发。Builder已完成72项的工具边界仍是v4及其批准派生，不将v5修复追溯称为Builder原采集版本。
