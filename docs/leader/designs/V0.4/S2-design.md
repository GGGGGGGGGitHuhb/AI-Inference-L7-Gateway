# V0.4/S2：缩短过载等待预算

状态：**Approved / 待实现**。2026-10-21，Leader按用户“开始s2工作”和持续技术决策委托“你来决策吧”、ROADMAP阶段采纳规则批准；决策包见[Leader001](../../reports/V0.4/S2-report-001.md)。本阶段返工0/2，独立于已关闭S1的4/4；修改本基线须新增S2返工权威。

## 1. 目标、证据与取舍

唯一方向是**请求等待成本控制**：利用已经实现的`admission.queue_timeout_ms`，比较固定500ms基线与100ms预注册候选；交付可复现配置、实验及适用边界，不为改代码而新增算法。100ms不是最优值，也不保证收益。

依据[S1结果](../../../performance/V0.4/S1-results.md)和[Reviewer002](../../../reviewer/reports/V0.4/S1-report-002.md)：Q60的queue8相对queue0在两个角色各三重复都降低达标goodput，独立差值−17/−13/−16.5req/s；增加HTTP成功不等于提高SLO成功。S1的等待500ms已超过TTFT250ms，并等于E2E500ms，构成缩短无效等待的可检验假设，**不是已证实根因**。发压敏感限制保留，旧数据不用作新配对。

源码确认：`src/app/GatewayConfig.cpp`接受10–300000ms；`ProxySession::nextDeadline()`在Waiting取原total期限与入队时间+queueTimeoutMs的较早值，`checkDeadline()`在队列超时返回504 queue_timeout；FIFO和资源回收已实现。只改配置就能研究该方向，无需改变产品状态机。未选择反馈路由、成本预测或多Worker，因为S1没有足够证据支持新增依赖/复杂性；NODELAY仅合成诊断，不能据此宣称产品瓶颈。

## 2. 范围和产物

REQ-01：产品`src/`、既有测试/CMake和`tests/experiments/`全部原字节保持；S1及更早权威、报告、原始数据保持。新工具放`tests/queue_budget/`，仅复用S1的Budget、Cell、Host、Association、Client/Worker、Statistics等现有机制。允许新runner通过局部子类覆盖Cell的gateway配置构造，禁止改写/monkey-patch旧模块全局函数。禁止复制整套客户端/预算/采样器形成第二实现。若旧机制不能满足关键要求，先报告Leader，不擅改保护范围。

REQ-02：交付三份完整、可由现有gateway `--config`读取的JSON：`tests/queue_budget/configs/no-queue.json`、`baseline-500ms.json`、`candidate-100ms.json`。静态例子listen127.0.0.1:8080、backend-0/1分别18081/18082，模型gateway-qwen，RR，global inflight2/perbackend1，queue bytes65536，queue count分别0/8/8，timeout分别500/500/100。它们是合成实验的可复制起点，不能直接宣称适合真实生产后端。runtime端口可由runner为自有子进程分配，保存完整实际配置。给用户说明按实际端口/模型调整和回滚至基线的方法，不更改全局默认1000ms或既有示例。

REQ-03：新计划/runner/统计审计/操作说明及`docs/performance/V0.4/S2-results.md`。不新增C++、依赖、模型下载、管理API、产品指标、调度策略、重试、fairness保证、S3/V0.5工作。无需真实模型实验：本次问题只验证确定性异质合成请求的队列预算；不能作真实GPU/模型收益声明。

## 3. 冻结实验

每角色独立一次完整run，**21cell，2760正式+210预热=2970唯一ID**，包括三重复；不得额外乘三或择优重跑。

- Q：到达率5req/s（不过载对照候选）和60req/s（过载）；每rate三配置×三重复，共18cell，各120正式+10预热。5req/s只是预选低负载，必须按实际无/低排队和拒绝情况判断其是否真正不过载，不能仅凭名称断言。
- 三配置标记Z(queue0/500)、B(queue8/500)、C(queue8/100)，始终group Q、path P、1发压进程。每重复先5后60；配置顺序repeat0 Z/B/C、repeat1 C/B/Z、repeat2 B/Z/C。
- T沿用S1 group T直连A后端、C8、200正式+10预热：开始单进程、紧接双进程、末尾单进程，共3cell。不得对T改变后端NODELAY或生成模型。
- Q后端/请求完全复用S1：两合成实例20/100ms，每四ID第四个延迟乘4，固定1024byte合法SSE、max_tokens32、请求内容/分配标签/正文校验不变。NODELAY固定off，新TCP/Connection close。健康、池、缓冲、total15000ms等其余配置与S1 Q一致；唯一B/C处理差异是等待期限。
- Q用自有Release ExperimentRuntimeHost（同产品库），T直连合成backend。三个静态JSON与实际runtime配置在去除listen/backend端口后应匹配Q模板，杜绝文档候选和实测不一致。
- 每cell先预热并排空，保留预热账；正式排空、FD和RSS检查。不以额外推理/探测改变工作负载。

计时/分母沿用S1：均匀scheduled，迟到>50ms或无128槽记not_sent不补发；TTFT≤250ms、E2E≤500ms均从scheduled起算。成功且双SLO满足数除以固定120/rate为goodput；HTTP成功、503 queue_full、504 queue_timeout及所有失败/未发互斥保留，后两者不能成为成功。完成吞吐用末次关闭wall，不能替代goodput。分位nearest-rank，p50≥20/p95≥100/p99≥1000，不跨重复合池；短/长请求分别报告全部计划数、终态、SLO成功数及goodput（同总窗口分母），不能仅报告幸存请求延迟。

REQ-04：逐ID关联客户端、host队列/派发/结束、后端实际请求，复用S1唯一关联校验；queue_timeout必须有入队、没有派发/后端请求，等待时间与100/500ms配置吻合（定时器可能延迟，不能声称精确实时），不得把到达后总时长当入队等待。完整列出排队后派发和超时等待分布、取消/重复终结异常、全资源回归。字段缺失或歧义必须失败，不能靠推断端口/轮询序号填补。

## 4. 质量、决策与停止界限

REQ-05：每rate至少2/3个Z/B/C完整三元组均非arrival_limited（not_sent≤1%、dispatch_lag p95≤5ms）；否则测量关键条件BLOCKED，不能称已完成有效比较。5req/s必须在B/C全部有效重复均无queue_full/queue_timeout，才能称不过载对照；否则记录无法验证低负载误杀边界并BLOCKED，不自动降rate重跑。

预注册候选推荐门槛（不是阶段PASS的必需正收益）：两个角色分别满足60有效配对中至少2对C−B>0且配对相对改变量中位数≥5%；5有效配对C相对B goodput中位退化≤5%；任何短/长类的配对goodput中位退化≤5%（基线为0的类不算比率，须绝对不降）；无协议/资源/生命周期退化。计算各配对比值再中位，不用比值的比值，全部原点保留。T机器漂移>20%、双/单变化>15%、客户端CPU≥0.85任一触发时，**无因果/容量或通用推荐声明**，即使上述数值通过也只报告受限描述性观察，保留产品默认与一般配置建议。只有工具控制未触发、两角色达到门槛时，才可作已测合成条件内的有限候选推荐，仍不推广到真实推理。零/负结果在有效测量、正确性和资源保障齐备时可PASS，结论必须明确“不推荐替换基线”，不得追加参数搜索。

REQ-06：复用原1GiB运行期硬预算（512MiB直接预留+448MiB managed累计+64MiB错误池）、每直接文件512KiB RLIMIT_FSIZE/core0、有界IPC/summary；不可按每子进程重新给完整预算。全run900s，每cell60s，现有client16s。最多21cell×12直接文件=126MiB预留，远低于512MiB。失败保存当前attempt及后续not_started，所有子进程TERM/KILL/wait闭合；报告未执行项，不删除失败run。账本峰不超过配置，排空全零、FD回基线、RSS≤预热B+32MiB。采样目标100ms/1s非硬实时，报告实际间隔。

只有Builder与Reviewer串行发压；各角色独立build、进程、端口、tmp/cache/output，必须使用不存在的run目录。第一次正式run失败后保存证据，由Leader决定是否返工；S2最多2轮，不因S1额度重置为无限。禁止扩大矩阵、改变门槛、择优剔除数据或修改产品以制造收益。

## 5. 实施顺序、验证及验收

M1 Builder先创建新计划/有限runner、完整配置与说明，并完成负控；M2完整回归与一次21cell；M3独立Reviewer自有构建/负控/一次21cell及自写复算；M4 Leader同步文档收口，协调者精确本地提交不推送。

无需新增CTest注册：三预设现有21项各完整运行一次，新Python DetectorTests单独执行并记录，不把21/21冒称包含新测试。新工具使用已有host产物；不要重新运行S1 57cell或旧soak。角色目录`build-local/ROLE/v0.4-s2/{tmp,cache,evidence,debug,release,asan}`，显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；原生WSL bash login=false。socket/LSan首次走已知窄权限，不禁检查、不下载/调系统。

现有命令按role展开：`cmake --preset debug -B build-local/builder/v0.4-s2/debug`、`cmake --build build-local/builder/v0.4-s2/debug -j4`、`ctest --test-dir build-local/builder/v0.4-s2/debug --output-on-failure`；release/asan同理，Reviewer替换role。以下是本阶段要求Builder交付的新CLI，不声称已存在：

```bash
python3 tests/queue_budget/DetectorTests.py --host build-local/builder/v0.4-s2/release/ExperimentRuntimeHost --output build-local/builder/v0.4-s2/evidence/controls-001
python3 tests/queue_budget/RunQueueBudget.py --host build-local/builder/v0.4-s2/release/ExperimentRuntimeHost --output build-local/builder/v0.4-s2/evidence/run-001
```

| 要求 | 验收 | 独立方法 |
| --- | --- | --- |
| REQ01/02/03 | AC01：保护文件hash不变，完整配置仅规定差异且实际host加载成功，CLI/文档一致 | RV01 diff/hash、启动每配置并检查运行时模板 |
| REQ03/04 | AC02：2970ID与21cell冻结、所有分类/分母/时刻/等待/后端一致，负控拒绝伪成功 | RV02逐ID独立复算、计划/分母/SLO/超时关联负控 |
| REQ04/06 | AC03：原始资源、进程/预算/失败留存齐备，queue_timeout不派发且终态清理 | RV03真实超时路径、预算/失败负控、完整run审计 |
| REQ05 | AC04：两rate有效三元组和不过载对照满足；候选取舍按预注册判定，可有效负结果PASS | RV04独立配对/分组/限制复算，不调整门槛 |
| REQ01–06 | AC05：各角色三套21/21及新负控，通过报告/独立PASS/文档收口 | RV05执行与证据身份、历史保护、声明检查 |

关键新负控：漏/重ID、把queue_timeout记success、以send替代scheduled洗掉SLO失败、忽略拒绝改变分母、关联已过期却派发、有效配对不足、低负载误杀、边界5%/零分母、预算耗尽/子进程退出后所有ID和PID闭合。至少一条真实100ms排队超时（保持slot直到超时）确认504/no backend dispatch/资源清零；detector可构造小样本，不属于正式性能数据。沿用预算/关联机制的既有CTest通过，不需重造全套负控。

本阶段文档更新README/ROADMAP当前状态、ARCHITECTURE测试边界，完成后CHANGELOG、结果及各角色报告。TECH-DEBT-TRACKER不存在；不把负面实验结论或未开始任务制造为技术债。无新增成本、依赖、外部发布授权。

## 6. 修订记录

2026-10-21：据源码和S1负面Q观察建立本阶段初版，Leader在用户委托范围内采纳；固定候选100ms、5/60req/s、21cell及预注册负结果处置。后续实质变更走S2返工。
