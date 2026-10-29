# V0.5/S2：额外成本与扩展边界

Approved，2026-10-29。依据用户“开始s2吧”及持续技术决策委托，在ROADMAP既定范围内由协调者采纳；[Leader001](../../reports/V0.5/S2-report-001.md)。S1已在92fcf3d独立验收并推送；本阶段独立计数，不改S1历史。

## 目标、边界及输入

REQ-01：以真实产品程序比较D（直连1Gateway）、M（客户端逐请求RR直连2Gateway）、L（经用户态TCP L4LB访问2Gateway）的有限成本；报告CPU、延迟、用户态TCP载荷传输量及长流分布边界。只新增 tests/l4lb_cost 工具与文档，不改产品、原工具/CMake、L4LB用户工作树，不做优化、GPU/真实模型/生产容量或XDP验证。

输入为S1已核对的TCP/健康语义与单进程准入；下游每请求新连接，上游 max_idle=0、后端Connection close，显式排除连接复用差异。所有Gateway共用一个独立Python后端进程，后端是可控合成服务，不是无限算力或推理引擎。后端TCP_NODELAY固定on以避免fixture发送分段导致的延迟确认干扰，产品不修改。D准入32，M/L各16，总额度32；每backend/上游池同步，入口max_connections64，每进程reserved预算沿有效配置，不以单进程不足隐藏拓扑差异。L健康开启，固定生产探测参数；M没有L4健康探测，其成本包含在M↔L差异中。

## 冻结矩阵、计时与计数

REQ-02：18cell = A/B两workload × 3重复 × D/M/L。A固定1024byte JSON；B固定16KiB SSE、16段、相邻段2ms sleep目标（不是硬实时）。每cell12预热+240正式、正式均匀60req/s（4秒计划窗口）、32客户端槽、新TCP；同workload各repeat按DML、MLD、LDM顺序。每ID完整唯一，全部4536次计划应用请求，不能删失败/挑最好重复或合池。额外偏斜案例单列，不计入成本矩阵。

发压采用开环。计划时刻无槽或实际dispatch晚于计划50ms记not_sent、不补发；所有未来未开始ID须保留not_started。每请求绝对5s期限，每cell30s，全run600s。每cell正式前预热完成并排空；CPU窗口从首scheduled之前的快照至全部正式终态/连接排空后的快照，保存真实window，不用计划4秒硬除CPU。

REQ-03：客户端记录scheduled/dispatch/connect/send/首次wire recv/首body/HTTP framing完成/关闭及status、实际tx/rx、正文hash。TTFB定义为首次非空recv（包含HTTP头）；TTFBody单列，均从scheduled起。E2E以完整CL或终止chunk被收到的观测时刻为终点，EOF/close验证另列，禁止用send起点缩短E2E。nearest-rank p50≥20、p95≥100、p99≥1000；本矩阵不报p99。计划窗口完成率与实际完成吞吐分开。不声称token级TTFT。

REQ-04：同窗口读取/proc的CPU ticks、RSS、FD，含所有Gateway、L4（如有）、后端及客户端/采样协调者。CPU秒=ticks/CLK_TCK，报告原ticks、量化精度、wall利用率和每成功请求CPU；<5ticks标低分辨率，0tick不能表述零成本。采样目标100ms，实际间隔保存；峰RSS/FD是观察值，不证明瞬时上界。排空后Gateway FD最多ready+2，L4最多ready+2，所有自有进程必须回收。

REQ-05：网络只报告各段**用户态正返回TCP字节数**，不称物理网卡流量/包开销。D/M各逻辑边只计一次：客户端tx+rx（客户端→Gateway）加后端counted read/write（Gateway→backend）；L额外加L4关闭session日志的sent_c2b+sent_b2c（L4→Gateway）。后端对原始HTTP读取/写入计数，含头和chunk framing；不根据规范化header重建猜测。单独分离预热和正式L4会话，正式关闭日志完整且总c2b/b2c须等于正式客户端tx/rx；不重复算L4接收边。每客户端ID与后端ID一一核对，后端成功且accepts=全部请求（无复用）。TCP/IP头、握手、ACK、重传及零载荷健康probe的网络成本未测；连接数与这一缺口明确列出。任何失败请求已发送字节不得从账中删除。

## 长流偏斜及测量质量

REQ-06：复用S1 Matrix/Fixture/Owned建立偏斜案例，显式将两Gateway及每backend准入提高到8、池8。按实际L4 accepted日志确认8新连接的归属，交替4长流门闩保持、4短请求完成，要求总连接4:4、快照在途4:0；放行后全部内容完整、ID唯一、进程清理。不得猜测归属或冒称随机生产分布。这个构造反例说明轮询连接数不能保证在途工作量均衡，且已建立流不能重新分配。

REQ-07：成本cell只有全部正式/预热请求成功、无收件/字节/时钟异常才可进入数值比较；否则保存完整结果并FAIL，不能仅统计幸存成功。每cell dispatch lag p95≤5ms、not_sent≤1%、client/backend平均CPU≤0.85core为测量质量标记；超标不删cell、不改参数，报告受限描述性观察，不作因果/容量声明。即使标记未触发，固定60req/s、小样本及同机共享CPU仍不能证明饱和容量或横向扩展。M↔L才是增加L4层的对照，D↔M同时改变Gateway进程数；报告每重复配对差值，不跨重复池化，不预设正收益门槛。

## 资源、证据、实施与验收

REQ-08：角色隔离 build-local/ROLE/v0.5-s2/{tmp,cache,evidence,gateway,l4lb}，原生WSL；TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX显式设置，无下载。source manifest构建前后记录两仓实际文件hash/dirty diff，L4源只读。每产品输出文件1MiB硬上限；structured文件≤2MiB；run总证据≤64MiB，逐cell预留16MiB并另预留4MiB收口，预算不足在启动前失败。全部输出新目录，错误保留原始证据，TERM一次/5s后KILL并wait，不得操作他人进程。独立Reviewer按技能角色规则使用独立构建/测量/自写审计；角色串行发压。

M1文档与负控；M2 Builder完整18cell+偏斜+Release既有21CTest；M3独立Reviewer相同矩阵/偏斜/负控、至少一个自写统计/字节审计及ReleaseCTest；M4结果和Leader收口、本地提交不自动推送。新命令为待实现 `python3 tests/l4lb_cost/RunCosts.py --gateway <binary> --l4lb <binary> --output <new-dir>`，完整命令由操作说明固定。无需重新做S1故障矩阵或旧性能实验。

- AC-01：REQ01/02/08，源保护和实际身份、18cell/4536ID固定、产物与CLI可复现，独立证据齐备。
- AC-02：REQ03/04，正确计时/CPU窗口、全部失败分母、CPU量化和采样限制，检测器拒绝错误时钟/缺失或重复ID/伪成功。
- AC-03：REQ05，原始字节与会话分阶段闭合，逐ID后端和正文一致、无隐藏复用，禁止物理网络声明；负控破坏字节应失败。
- AC-04：REQ06/07，实测偏斜、每重复D/M/L差异与质量标记完整；无扩容/生产/因果外推。
- AC-05：REQ08，故障/预算/重复目录负控、资源回收、既有21项回归通过。环境限制阻断关键验证则BLOCKED，不以功能联通冒充成本测量完成。
