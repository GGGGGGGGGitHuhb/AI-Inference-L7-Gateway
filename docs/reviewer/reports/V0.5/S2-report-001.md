# V0.5/S2 独立审查报告001

2026-10-29，**PASS**。全部阶段关键验收路径通过，无待返工发现或需接受的技术债。仅接受本机固定负载的描述性成本与构造偏斜结论，不接受生产容量、稳定加速或横向扩展收益声明。

## 范围与依据

依据 [Approved设计](../../../leader/designs/V0.5/S2-design.md)、[审查计划](../../reviews/V0.5/S2-review.md)、[Builder001](../../../builder/reports/V0.5/S2-report-001.md)，并读取 ROADMAP、ARCHITECTURE、S1 工具及下游单请求关闭边界。项目无专用 Reviewer GUIDE，继续回退全局 plan-project-docs Reviewer 模板；使用 agent-execution-route。仅写 Reviewer 报告及自有证据，没有修改 Builder 文件、产品或历史报告。

独立角色根 `build-local/reviewer/v0.5-s2/`，原生 WSL2 Linux，本仓库 cwd；TMPDIR/TMP/TEMP 为自有 tmp，XDG_CACHE_HOME/PYTHONPYCACHEPREFIX 为自有 cache。独立 Release 构建及所有测量使用自有产物/进程/端口/新输出目录，Builder 最终 run 完成后才开始发压。未复用 Builder 样本，无外网、模型下载、XDP、GPU或系统配置变更。

## 实现审查及测量前纠正

检查新增 Common、Backend、Client、Analyze、RunCosts、Skew、DetectorTests 与 README。核对 S1 Owned/Identity/Matrix 和 integration WireResponse 为原字节复用，产品源码、CMake、旧测试、S1 历史均未变。

测量前审查建议已落实：首次 wire recv 与首 body 分开；CPU 用实际窗口和 ticks；L4 预热与正式会话隔离、重复 session 和端口漂移检测；累计证据预算保留旧 cell 占用；全 cell 30s 活动期限；发送短写每轮重算绝对请求剩余期限；批次中断后保留已提交任务的实际结果/字节，只有未提交任务记 not_started。上述为实施期间纠正，不改变冻结负载或接受门槛。

成本 D/M/L 总准入均32，D单进程32、M/L各16，每 backend 与池同步；入口64、max_idle=0、后端 Connection close。后端独立 Python 进程，固定 TCP_NODELAY，未改变产品。网络读取/写入计数包含 HTTP 头和 chunk framing，按逻辑边只计一次，未把 TCP/IP 包成本推算进结果。

构建前保存两仓 `*-inputs-before.json`，测量后 `*-inputs-after.json` 精确相同。L4LB 工作树实际 hash/dirty diff 记录在自有 manifest，未把 f0d41f7a5c5378c63b42ee0f9cfe8b87afe6428c 冒称为干净构建；Gateway 起点92fcf3d。两套 Release 构建均成功，未写入 L4LB 源仓库。

## 独立执行与原始证据

命令均在上述显式环境执行，完整输出保存于 evidence：

```bash
python3 tests/l4lb/Identity.py --source . --output build-local/reviewer/v0.5-s2/evidence/gateway-inputs-before.json
python3 tests/l4lb/Identity.py --source /home/power/projects/L4-LoadBalancer-withXDP --output build-local/reviewer/v0.5-s2/evidence/l4lb-inputs-before.json
cmake -S . -B build-local/reviewer/v0.5-s2/gateway -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-local/reviewer/v0.5-s2/gateway -j4
cmake -S /home/power/projects/L4-LoadBalancer-withXDP -B build-local/reviewer/v0.5-s2/l4lb -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DL4LB_BUILD_XDP=OFF -DL4LB_BUILD_XDP_LOADER=OFF
cmake --build build-local/reviewer/v0.5-s2/l4lb -j4
python3 tests/l4lb_cost/DetectorTests.py
python3 build-local/reviewer/v0.5-s2/evidence/InterruptedBatch.py interrupted-batch-002
python3 tests/l4lb_cost/RunCosts.py --gateway build-local/reviewer/v0.5-s2/gateway/ai-inference-gateway --l4lb build-local/reviewer/v0.5-s2/l4lb/bin/l4lb --output build-local/reviewer/v0.5-s2/evidence/run-001
python3 build-local/reviewer/v0.5-s2/evidence/IndependentAudit.py build-local/reviewer/v0.5-s2/evidence/run-001
python3 build-local/reviewer/v0.5-s2/evidence/IndependentNegative.py
ctest --test-dir build-local/reviewer/v0.5-s2/gateway --output-on-failure
```

- 独立正式矩阵 **18/18 PASS，4536/4536 计划请求成功，92.611s**；其中4320正式、216预热，not_started=0。偏斜另8请求全部成功，未混入成本样本。
- `quality_limited=[]`；最大 dispatch lag p95 **0.940936ms**，client/backend 最大平均CPU **0.116297 core**。质量标记未触发不等于无系统噪声或已证明容量。
- 独立 Release 既有 CTest **21/21 PASS，41.69s**。新矩阵/负控单列，不计入21项；未重跑未改变产品的 Debug/ASan、旧性能矩阵或S1故障矩阵。
- DetectorTests **6/6 PASS**：完整计划、失败/缺重ID/时钟/hash、原始字节计数、L4字节/预热/session/后端收件破坏、分位阈值、累计预算门槛。
- 自写 IndependentAudit 不导入 Builder 汇总函数，独立复算每 cell 时钟分位、CPU窗口/ticks/利用率/量化标记、用户态字节、实际L4正式session、全部12组配对p50/p95/TTFB/CPU/字节差，PASS；同时核对4536唯一ID、偏斜8ID及全部57个进程退出。
- 自写 InterruptedBatch：在第3个计划请求处触发截止，2个已提交任务的真实失败结果及 **tx246/rx90 bytes** 保留，另外2个才标not_started。旧控制001和最终工具控制002均保留。
- 自写 IndependentNegative：`/usr/bin/false` 提前退出使 runner 非零且保存FAIL，4536未开始ID完整、2个已启动进程全部回收；同输出目录再次运行被拒绝、非零，原文件hash保持不变。

## 独立成本结果

下表为每重复 **L−M** 原始配对，CPU合计所有Gateway与L4。三点不池化，不选最好结果。更多M−D及全部分位在独立 run-001/comparisons.json 与各cell/result.json。

| 工作负载 | E2E p95差值ms（0/1/2） | proxy CPU每成功请求差值ms（0/1/2） | 额外逻辑跳载荷字节/240正式请求 |
| --- | --- | --- | --- |
| A JSON | +0.610378 / −3.216268 / −3.356526 | +0.166667 / −0.083333 / 0 | 348000 / 348000 / 348000 |
| B SSE | −1.071261 / −0.376869 / −0.151759 | +0.291667 / +0.583333 / +0.500000 | 4063920 / 4063920 / 4063920 |

A 的独立延迟/CPU差值与 Builder 最终轮部分符号不一致。不能据此称 L4 加速、零成本或形成稳定的通用开销估计；两角色保持分列，不能用平均抹平差异。本机 CLK_TCK=100，即10ms tick；**9个process-cell少于5ticks**，低分辨率和共享CPU/调度噪声必须与数字并列。上述小数位用于核对原始复算，不表示对应测量精度。

额外逻辑跳载荷量在所有重复一致，与客户端正式tx/rx之和严格闭合；这是所选HTTP字节在多一条边上的传输量，不包括握手、ACK、重传、IP/TCP头或健康probe包开销。

## 按验收项结论

- **RV01 / AC01 PASS**：18cell、4536ID与固定顺序一致；运行配置及实际source/binary身份可核对；D/M/L均用真实产品，旧源码/工具/CMake保持。
- **RV02 / AC02 PASS**：scheduled起点、wire/body/framing/EOF时刻分开，所有时钟单调；分位和实际CPU窗口独立复算一致。正式未发/失败不被删除，本轮均成功。采样最大实际间隔104.510ms，100ms仅目标；原ticks、量化及质量标记保留。
- **RV03 / AC03 PASS**：每cell后端accepts=252、252唯一ID，无隐藏复用；正式240个L4 session与预热12个分离，accepted/closed身份、端口、正常终结及双向字节守恒；每逻辑边计一次。破坏字节、session、预热或收件的负控均失败。
- **RV04 / AC04 PASS**：偏斜由实际L4日志与后端门闩确认，8连接计数4:4而快照在途4:0；4条长流在快照后全部完整结束，无重放。全部12组配对及质量标记可独立复算；仅作为构造反例，不宣称随机流量分布或横向扩展收益。
- **RV05 / AC05 PASS**：成本54个、偏斜3个，共57个自有进程均exit0并回收，无强制清理。FD回归门槛由独立运行器实际执行。总证据 **4,631,982 bytes**，低于64MiB；逐文件caps、下一cell16MiB与收口4MiB预留成立；累计预算拒绝、早期失败、防覆盖、批次中断负控均通过。完整Release回归通过。

## 未测范围与收口

无未关闭发现、无新增债务。网络包级开销、真实推理/GPU、生产容量、饱和吞吐、长期稳定性和随机流量下的分布均未验证；固定60req/s及两个合成负载不能支撑这些声明。CPU/延迟正负波动只报告观察，不转述为因果收益。

建议 Leader 依据本报告更新结果文档、README/ROADMAP/ARCHITECTURE当前状态和CHANGELOG，再按既有授权本地提交；不自动推送或引入新优化。原始run和负控不覆盖，运行证据位于自有evidence目录；本报告仅给出阶段独立验收结论。
