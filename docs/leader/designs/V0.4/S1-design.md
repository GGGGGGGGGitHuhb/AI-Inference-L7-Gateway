# V0.4/S1 公平性能基线设计

2026-10-20，**Approved / 待实现**，新阶段返工0/2。用户“那好，做v0.4/s1吧”与既有技术委托授权本范围内决策；[Leader001](../../reports/V0.4/S1-report-001.md)记录决策。分支codex/v0.4-s1-performance-baseline，起点44266088f5d93880983eb58a27117b796af7075b；V0.3/S3已本地提交，其2/2历史保持，推送未核验。

## 1. 范围与资产

分别研究代理连接成本、慢读背压稳定、RR/Least Inflight和有限准入排队。只新增`tests/experiments/`工具、短检测器、必要只读测试host及`docs/performance/V0.4/S1-results.md`，不改产品、旧tests/performance或tests/mvp及历史数据。允许只读复用其严格HTTP解析、进程清理与预算思想；新入口不得改变旧模块全局状态/默认行为。正式Release程序用于无内部账本需求的成本/真实路径；策略、排队和慢读可用链接同一产品库的host，相关D/P对照明示观察开销，不能当正式程序无扰动成本。

不实施优化、调系统参数、不重写调度，不开始S2/L4LB。现有Router按请求inflight而非idle连接计数；额度在上游终态释放，连接lease可能等待下游排空。队列只等待容量，count先于byte，0count拒绝503 queue_full，byte超限503 queue_bytes_exceeded，等待超时504 queue_timeout，无健康503 no_available_backend，池满503 upstream_capacity均单列，不重试。

只读使用原b7481/Qwen0.5B Q4_K_M资产，源/许可及固定SHA沿[V0.3/S3设计](../V0.3/S3-design.md)。server SHA45938e6847d403ff6486cd692de9441aeb330e971a5dd8ad6f695b60bae2d081、模型SHA74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db；执行者重验archive/库/许可。真实两实例每个threads2/batch2/ctx2048/parallel1/GPU0/alias gateway-qwen，共享CPU/内存，不声称独占实例或GPU收益。无下载/安装。启动120s/实例、RSS2GiB/实例护栏；仅自有127.0.0.1端口/PID，TERM5s后KILL/wait。

## 2. 固定工作负载、配置与SLO

客户端全部新TCP、Connection close；D直连，PC网关上游max_idle0，PR保留上游max_idle4/idle5000ms；所有流结束不归池。记录accept/request计数和预热连接实际复用，不能仅根据配置假设。合成后端HTTP/1.1固定头/body分开写，默认TCP_NODELAY关闭并记录getsockopt；诊断仅改变后端套接字NODELAY，不改网关。

A：1024byte有效JSON，原P1相同冻结字节/hash；成本闭环C1/C4。B：原P1的4MiB固定SSE，C4四请求波次，1慢3快，慢读首读前0.5s后每16KiB等5ms，SO_RCVBUF请求65536并记录实际值，12正式=3波。H：单模型双合成实例，快实例基础20ms、慢实例100ms，每四个ID前三短/第四长，长乘4；处理时等待上述目标时间再发送同一1024byte合法SSE内容及正常尾块。每请求独立延迟、没有模拟CPU争抢/隐含串行队列，记录实际handler开始/首发/结束，不把sleep目标当实际服务时长。快慢响应字节相同，实例延迟异质仅支持该模型的有限因果说明。

R：既有短prompt、temperature0、max_tokens32、stream=true/n1；C2闭环，D由客户端按ID轮转两实例，P网关RR，均可有后端slot等待；相同模型/cache输入不保证相同输出或CPU占用。按路径预热，记录后端timing和实际实例分配。R是小规模真实交叉观察，不用其D/P差异归因纯代理开销。

固定成功SLO（须HTTP正确完成，流还须首非空content）：A E2E≤100ms；B快E2E≤500ms/慢≤5000ms；H TTFT≤250ms且E2E≤500ms；R TTFT≤2000ms且E2E≤5000ms。阈值实验前冻结，非产品承诺，不因结果差而放宽。

Gateway实验配置：max_connections128/reserved2GiB、stream总32MiB、原192/64KiB水位；池每实例max32/idle按路径，health failure2/cooldown1000ms。request5000/connect1000/upstream_write2000/response10000/stream_idle5000/downstream_write10000/total15000/shutdown3000ms；真实仅response/stream_idle/total换120000/30000/150000ms，其余不变。策略H不启用admission；队列Q启用global2/perbackend1/count0或8/bytes65536/queue_timeout500ms，RR策略固定；配置差异全记录。Q使用H相同实例和输入，不把开关队列与改变路由同时归因。客户端单请求绝对期限合成16s、真实155s。

## 3. 冻结矩阵、顺序与计数

cell为独立配置+预热+正式批次+排空单位。各组合3重复r=0,1,2，任何尝试不得覆盖；预热与正式分开，成功分位数不跨重复混池。所有正式配置和输入在首轮前生成schedule/manifest并hash。路径顺序r0正序、r1逆序、r2正序；三路径A为D-PC-PR、PR-PC-D、PC-D-PR。各C/速率按表升序执行，各重复先A、B、H、Q、R；控制按下述专门位置插入。

| 组 | 组合 | cell数 | 每cell正式/预热 | 正式总数 |
| --- | --- | ---: | ---: | ---: |
| A 成本 | C1/C4 × D/PC/PR ×3 | 18 | 200/10 | 3600 |
| B 慢读 | C4 × D/P ×3 | 6 | 12/4 | 72 |
| H 策略开环 | 20/s、60/s × RR/LI ×3 | 12 | 120/10 | 1440 |
| Q 准入开环 | 60/s × count0/count8 ×3，RR相同 | 6 | 120/10 | 720 |
| R 真实 | C2 × D/P ×3 | 6 | 12/2 | 72 |
| T 发压控制 | A D、C8；全程开始单进程/紧接双进程/全部结束单进程 | 3 | 200/10 | 600 |
| N PR诊断 | A PR C1，后端NODELAY off/on ×3 | 6 | 100/10 | 600 |
| 总计 | 含控制57cell | 57 | 正式7104/预热486 | 7104 |

57cell已包含三重复，每角色各自完整执行57cell，不再乘3。预计每角色测量约5–15分钟（仅规划估计，不是已测事实），完整run硬限3600s；独立构建/回归不计入测量墙钟。全计划7590个唯一ID（正式7104+预热486），每个cell的预热也按同一输入模式、在途限制独立排空；B预热一波，R预热每实例一次。N放每轮A后、同轮off/on顺序交错，不以诊断代替基线。T双进程各C4/100正式/5预热，合计与单进程相同C8/200/10，不加总负载；两子进程共享绝对启动门闩，父进程收全唯一ID。T最后单进程在全部其他cell后执行。

合成每cell硬护栏60s（含预热/排空），R每cell240s；全run含启动护栏3600s、日志预算见第6节，同一角色同一时刻仅1cell。超护栏保存未发/未完成并有限清理，不自动扩时。两个角色测量不得重叠；不重跑P1或旧长soak。

## 4. 开环时钟、发压能力与统计

H/Q固定均匀到达：正式i=0..119，scheduled=t0+i/rate，观察窗T=120/rate（6s或2s）。提前预序列化120请求与任务ID，实际发送使用单调时钟；调度器不等待先前HTTP完成，不以完成补发。最多128活动请求，调度迟到>50ms或无发压槽时该ID记not_sent（含原因与检查时刻），不追赶突发、不静默丢弃；没有到执行时刻的ID在中断时记not_started，区别已到期not_sent。预热10请求按同rate但独立时钟/分母。

记录scheduled、dispatch/connect开始、request_send_complete、首头/首body/首非空content、HTTP合法完成、关闭、结果。send_lag=request_send_complete−scheduled（连接建立包含其中），另记dispatch_lag以区分调度与网络。开环SLO从scheduled计算，发送后时延另列，不能只统计已发送成功样本掩盖coordinated omission。定义open offered=120/T，scheduled-goodput=成功且scheduled到终态满足SLO的数量/T，窗口后完成仍按其原计划ID归属并披露；另列完成吞吐=成功数/(最后terminal−t0)，不能互换。闭环吞吐/达标goodput以屏障至最后关闭墙钟为分母，SLO起点为客户端connect开始；请求发送后时延另列。

所有ID形成互斥终态：success、HTTP rejection（状态/code）、HTTP timeout、transport/protocol failure、client deadline、not_sent、not_started；计划无取消，出现取消或外部中断必须单列失败。HTTP200但正文/终态错误不是success；reject也不能算完成成功。总数恒等、发往后端次数和池复用差量审计。queue_wait仅enqueued且dispatched，用host时钟差；未派发超时等待单列，跨进程绝对时间不相减。SLO不达标是成功内子集，不另加分母。

各cell成功n≥20报p50、n≥100报p95、n≥1000方可报p99；否则仅min/median/max+n，真实不报尾分位。nearest-rank，零成功null；三重复各指标报median[min,max]和三点原值，不混池/择优/称置信区间。配对差是cell统计差，不是单请求额外延迟分位数。快慢/长短独列，不能用总体均值掩盖饥饿。

工具控制：逐进程CPU秒/墙钟（100%=一逻辑核）、RSS/FD/context-switch及机器负载、亲和性、核心数、版本记录。T前后单进程吞吐变化>20%标machine_drift，双/首单变化>15%标generator_sensitive；任一客户端CPU≥0.85核且吞吐随负载不稳定标suspected_generator_limit，不直接归因GIL。H/Q not_sent>1%或dispatch_lag p95>5ms标arrival_limited；全部send_lag仍报告。控制触发时相关比较不作策略/代理容量因果结论，不隐去数据、不改rate寻好结果。N仅报告off/on及实际复用/头body写入时序：约44ms若复现是负面结果，若消失也不能直接宣称产品修复或根因已证实。

## 5. 背压、资源与负面结果

B的P三重复必须实际观察pause/resume且正常数据完整，快流在慢流未结束时能进展；否则该机制测量未满足。H/Q记录实际实例/请求inflight/队列count/byte峰、queue wait及拒绝，验证不越配置、无隐式重试。预算和FD在每cell结束后等idle到期≤8s回基线；全部活动账、session/reserved/stream/pending/paused/leased/inflight/queue/timer清零。idle FD不是泄漏，正式drain后才比较。Gateway预热排空RSS B、后续排空≤B+32MiB；超出保留并诊断，不能直接用allocator理由豁免。

账本目标100ms、CPU/RSS/FD目标1s，保存实际间隔；采样峰不是真峰，累计产品/host计数与确定性测试补充资源限额。host不能在每次采样重复保存无界完整请求历史，逐ID状态转换有固定记录上限。后端/客户端资源分列，内核socket buffer不等于预约；性能cell不启用详细热路径日志，每ID结构化摘要在有限缓冲后写出，缓冲/写盘方式及影响说明。

阶段可接受有效负面结果：策略无收益/更差、排队降低goodput、拒绝或SLO失败，只要发生于完整固定负载、正确分类且协议/资源契约保持。工具控制提示限制作受限基线结论而非虚构容量；H至少一个预定速率的RR/LI在三对中至少两对双方均非arrival_limited，Q三对中至少两对双方均非arrival_limited，否则相应目标Blocked。所有三对都完整呈现，不剔除受限重复后伪装完整三重复结论；足够有效对仅支持该受控负载的描述性比较，受限对限制外推。若无法证明计划到达被施加，不能仅以限制文字PASS。T漂移/发压敏感或客户端CPU标记本身允许接受带限制的描述性基线，但相关因果/容量判断必须写未证实。未知瓶颈、缺样本、分类错误、资源越界、机制未触发、资产错或环境不能运行为未通过/Blocked；不允许为了得到正结果改产品。机器漂移使方向不稳定可作为“无法归因”的有效观察，报告单次身份，不接受无依据的普遍收益。

## 6. 运行期存储、进程与负控

本阶段新run上限**1GiB=512MiB直接文件预留+448MiB受管累计写入+64MiB错误取证池**；不是继续套用S3小矩阵96+28+4MiB。每个子进程直接文件RLIMIT_FSIZE软硬512KiB、core0，完整路径（stdout、state、partial、history、backend摘要等）在spawn前预留；最多1024路径，固定计划每cell≤12路径、57cell≤684路径，另共享≤32路径，总≤716，不能漏原子替换双份。超过预留即拒绝启动，不靠末尾遍历。产品不改文件输出；可将新host输出变为有界IPC，由父进程受管保存，必须记录实际方案并证明所有写路径覆盖。

受管字节按锁内写前序列化计费、覆盖不退款；跨发压进程只父进程写受管run目录，子进程用有界IPC回传，防每进程各自拥有完整额度。每attempt摘要≤8KiB，正常只保存长度/hash/有限错误前缀与时间而非4MiB正文，校验仍完整增量执行；新host每ID最多16条转移事件、每条≤1KiB，其余采样每条≤4KiB。全run 7590attempt、最多121440事件及每秒资源/100ms账本受总448MiB硬界约束，达到即失败，不静默裁样本通过。

每cell有界缓冲≤256attempt，完成/异常finally唯一持久化；剩余未开始ID从固定plan映射终态，不伪造已发请求。预算失败64MiB池用于所有尚未持久化的当前cell≤256条每条≤16KiB、进程回收及run错误，仍硬计费；已落盘不删。误配置越界不能写无限正文；触限即非零、kill/wait全部自有进程，保留partial/evidence_truncated不得标成功。直接文件硬上界不依赖监视目标周期，错误通知可受调度延迟。

并行自有进程≤8（协调驱动1、发压最多2、后端最多2、gateway/host1，其余≤2监视/辅助），不复制数十backend。按所有进程计清理/峰值，thread/task也≤256/进程。工具负控至少覆盖：多路径预留、并发累计、预算失败取证/回收、双发压中断且全部ID闭合、开环迟到/饱和未发、错误时钟/时间顺序、部分200错误尾、晚到future异常、缺失/重复ID、错分拒绝/timeout、SLO阈值与nearest-rank、容量/末态残留、缺/错模型与端口冲突。小预算真实写入必须非零，不能只测试手工错误文本。

## 7. 验收与交接

AC01/RV01：冻结57cell/7590ID计划、同输入/配置/时钟/SLO/交错顺序及负控；全部尝试保留。AC02/RV02：代理连接模式与N诊断、B背压及资源；P1限制不消失于汇总。AC03/RV03：H/Q开环施加/未发/拒绝及RR/LI/排队比较可信，负面结果按边界解释。AC04/RV04：真实少量独立进程和固定资产兼容、分母/延迟/goodput/资源与CPU共享限制。AC05/RV05：运行期预算/清理、源产物/命令/退出码/原始数据、回归/规范/历史保护和可复现报告齐全。

Builder先离线check/短负控，再三预设完整CTest（新负控CTest不跑矩阵），再一次完整矩阵。Reviewer独立三预设回归和同规模完整57cell，因为工作量有界且性能关键比较不能复用Builder数据；独立自写复算全部ID、SLO、分位数、计划/实发/未发、预算和至少3关键负控。不把工具错误当有效负面结果；若工具变更需重跑受影响cell且保留前后身份与配对完整性，由Leader判定，不自动重测选优。无重复长P1/soak。

执行路线原生WSL `/bin/bash` login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway；build-local/<role>/v0.4-s1/{tmp,cache,evidence,debug,release,asan}，脚本前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX，socket/LSan首次精确窄升级。使用全局Leader指南回退及个人C++完整规则/正反例；新增C++实际格式化/人工回调与相邻函数检查。最大两轮统一返工，当前0/2；独立接受后Leader收口、协调者本地提交不推送，S2方向由结果另行设计。
