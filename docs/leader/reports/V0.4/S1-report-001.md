# V0.4/S1 Leader 规划报告001

2026-10-20，**Approved / Ready for Builder**，新阶段累计返工0/2。

## 第一部分：PM 决策摘要

**结论：On Track，可以开始公平性能基线。** 用户明确启动V0.4/S1及此前技术委托授权本方案。当前仅完成规划，尚未实现/测量，不宣称性能收益。

**计划与实际：** 已冻结每角色57个cell（含三重复）、7104正式+486预热请求，分别测代理连接成本、背压稳定、RR/LI及准入排队，真实CPU少量交叉验证。预计测量5–15分钟、完整run硬限60分钟，构建回归另计。S3已本地提交4426608，其2/2历史关闭；本阶段独立从0/2开始。

**关键选择：** 固定到达与SLO，开环保留每条计划/实际发送/未发；闭环与开环分母分开。三重复预定交错，单/双发压及前后控制识别工具限制；约44ms只做后端NODELAY外部诊断，不修产品。新运行期总存储上限1GiB，逐attempt保留有界摘要，覆盖子进程和异常清理。

**风险与取舍：** 同机CPU、Python发压及机器漂移可能使结果受限；有效负面结果可以接受，不要求提升。到达控制不足或数据缺失不能伪装PASS。真实共享CPU不支持GPU/独占实例收益。新依赖、实质范围偏差、债务或阻塞：None。

**PM决策：None。** Builder实现新工具和固定矩阵，Reviewer独立同规模测量及复算，Leader最后收口；完成后协调者本地提交、不推送。S2优化方向由数据另行设计，未启动。

## 第二部分：详细工作记录

供PM按需查阅。

### 依据与权威

起点codex/v0.4-s1-performance-baseline / 44266088f5d93880983eb58a27117b796af7075b，初始clean；S3本地提交事实已知，远端未核验。读取ROADMAP V0.4/S1、P1完整结果/工具说明、S3预算实现及最终接受、S1 Router与S2准入设计/配置语义。P1约44ms、双发压差异与机器漂移均纳入控制，而非当待修复性能缺陷。

[Approved设计](../../designs/V0.4/S1-design.md) SHA256 `f7ef361e4119d450fbf43353d70b26ed2695276f5f37ecca2b10d912f2b7d987`；[Approved审查计划](../../../reviewer/reviews/V0.4/S1-review.md) SHA256 `de8af37d9fa47aef1fe5d517ec25107cd0d3224690a4466ee35bbcd2dff5f57d`。用户阶段启动与既有委托为批准依据，无例行待批项。无项目专用Leader指南，沿plan-project-docs模板回退、Olympus、agent-execution-route及个人C++规则正反例。

### 设计选择及自查

57cell=18成本+6慢读+12策略+6队列+6真实+3发压控制+6外部诊断，已含三重复。正式7104、预热486；每个正式/预热ID都有互斥终态，open-loop不因响应变慢自动降低计划到达。SLO从scheduled起算用于开环达标goodput，同时保留发送后时延；闭环采用屏障至最后关闭墙钟。失败/拒绝/未发不混进成功分位数，n不足只报median/min/max，不把小样本p99作为结论。

异质合成后端按固定快慢延迟/长短分布，明确无模拟CPU争抢；H仅改RR/LI，Q固定RR仅改count0/8，避免同时改路由/准入混淆因果。池lease与请求inflight不同，排空需等idle过期。0count对应503 queue_full、byte503 queue_bytes_exceeded、queue deadline504 queue_timeout；无健康、传输池满及连接级关闭分开，工具不增加重试。

T漂移>20%/双发压变化>15%和CPU标记允许限定的描述结果，禁止相关容量/因果归因；H至少一速率与Q各要求三对中至少两对双方到达控制有效，否则Blocked。工具记账、时钟、协议/分类、缺样本和预算错误必须FAIL，不能用“负面结果有效”豁免。全部重复呈现，不删抖动或择优；PR诊断只改变模拟后端NODELAY。

运行期总上限1GiB分512/448/64MiB，直接路径按512KiB提前预留且硬限、受管写入累计计费、错误池保留当前cell至多256待落盘记录；跨进程不能各自复制完整预算。最坏716直接路径预留358MiB低于512MiB池，所有写路径仍须实现核验。旧S3预算思想复用但旧实现/默认行为不修改，新工具负控验证真实累计越界和异常回收。真实固定资产只读、不下载；两CPU后端各2线程，少量交叉观察不当作独占资源调度证据。

### 路线与交接

原生WSL `/bin/bash` login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway；各角色build-local/<role>/v0.4-s1/{tmp,cache,evidence,debug,release,asan}，脚本前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX，socket/LSan已知边界首次窄升级。角色独立构建、端口、进程和原始数据，正式测量顺序执行；资产只读共享。

本轮只读审视和规划，未实现、未跑负载。新增设计/审查/本报告，根README/ROADMAP/ARCHITECTURE同步当前阶段和S3提交事实；旧权威/报告/源/工具保护，检查见build-local/leader/v0.4-s1/evidence/planning-check.log，SHA见planning-identity.json。Builder先负控与三套回归，再完整矩阵；Reviewer独立完整57cell及复算/追加负控。当前0/2，未提交/推送，交Builder后停止修改。
