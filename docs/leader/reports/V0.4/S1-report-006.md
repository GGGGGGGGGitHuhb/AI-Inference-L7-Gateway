# V0.4/S1 Leader 最终收口报告006

2026-10-21，Completed / On Track，累计返工 **4/4**。

## 第一部分：PM 决策摘要

**结论：On Track，V0.4/S1开发验收完成。** Reviewer002已独立PASS，全部发现关闭，无待接受债务；本轮没有新增纠正或第五轮返工。

**计划与实际：** 冻结的公平基线工具、两角色各57cell/7590ID、完整统计和文档已交付。独立Debug/Release/ASan+UBSan各21/21，矩阵一次388.725520s完成，H20/H60/Q60有效配对各3/3。剩余工作仅由协调者本地提交、不推送；V0.4整体未完成或发布，S2未开始。

**诊断结论：** 新测试失败源于检查时点错误：finished但session仍活时四项为16MiB/0/0/0，正常析构后全部为0。修复将活对象与析构后保障分开，未修改产品释放时机。原首次Release背压失败未记录子值，仍不能回溯断定其根因。

**重大偏差与风险：** 两次额外返工授权累计至4/4，历史失败全部保留。固定合成负载中LI达标goodput较高，增加队列反而降低达标goodput；发压敏感和客户端CPU限制仍触发，策略因果收益、网关容量及GPU收益均未证实。这是已批准基线的声明边界，不是待接受债务。

**PM决策：None。** 用户已授权诊断、有限修复、文档同步和完成后本地提交。Leader建议按独立PASS关闭S1，不需再次批准；下一步由协调者校验并提交，完成条件为本地提交及状态核验。S2须另行设计/启动，不随本收口自动开展。

## 第二部分：详细工作记录

供PM按需查阅。

### 权威与角色边界

已读取用户提供的跨项目AGENTS规则；仓库及父目录未发现额外AGENTS.md，没有项目Leader指南，回退至plan-project-docs的Leader模板，已读取其PM关系和双层报告契约。TECH-DEBT-TRACKER.md不存在，Reviewer无待接受债项，本轮不制造空债务文档。复用agent-execution-route：原生WSL、bash login=false、cwd=/home/power/projects/AI-Inference-L7-Gateway；Leader独立`build-local/leader/v0.4-s1/{tmp,cache,evidence}`，脚本显式设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX。仅文档编辑与只读校验，无构建、测试、负载、安装或网络操作。

基线为[Approved设计](../../designs/V0.4/S1-design.md)、[审查计划](../../../reviewer/reviews/V0.4/S1-review.md)，叠加[返工001](../../reworks/V0.4/S1-rework-001.md)、[002](../../reworks/V0.4/S1-rework-002.md)、[003](../../reworks/V0.4/S1-rework-003.md)、[004](../../reworks/V0.4/S1-rework-004.md)。最后用户明确要求先查四项资源与生命周期再针对原因修复；累计4/4不重置历史额度。[Stop001](S1-stop-001.md)、[Stop002](S1-stop-002.md)和原[Reviewer001 FAIL](../../../reviewer/reports/V0.4/S1-report-001.md)保持原字节。

收口输入：[Builder002](../../../builder/reports/V0.4/S1-report-002.md) SHA256 `c21269b692b09fd95ce8b76e92445ae03987f8554dbc7132d6e99ee470f8b0b3`；[Reviewer002 PASS](../../../reviewer/reports/V0.4/S1-report-002.md) SHA256 `2270f1d1fef82d9f5421546bc3c0f4ad11ba2c65b52b03a63a7d2d519c0a01d2`。当前分支`codex/v0.4-s1-performance-baseline`，提交前HEAD `44266088f5d93880983eb58a27117b796af7075b`；所有阶段脏文件保留，提交归协调者。

### 诊断、修复与接受追溯

首次工具失败是源端口复用关联错误，返工001仅修后置唯一关联后，Builder完整重跑57cell，不拼接旧失败数据。Reviewer初次Release背压联合断言失败未记录token/pending子值；返工002纠正真实high触发与poll后合法迟滞的观察区别，并新增确定性机制验证。新增测试又分别遇到默认buffered模式校验SSE、活对象预约全零的错误，形成Stop001/002与两次用户新增授权；不能将这些测试问题改写为产品缺陷或环境抖动。

返工004先一次保留失败传播的诊断：完成前reserved16777216/streamCapacity262144/pending8192/paused0；flush、checkCleanup、正文及异常析构前为16777216/0/0/0，reservation有效、session finished，其他流lease/token/timer/pool均0；session正常销毁后四项全0，budget/loop/pool仍存活。证据确定Fixture::checkCleanup不是析构，预约由成员RAII随对象析构归还。仅修测试为两层断言，先完整迟滞/正文/终态，再销毁检查，未提前reset掩盖问题、未改变共享Fixture或产品。

独立Reviewer确认high32842→16384→8193仍暂停，恰8192恢复且新token不同；旧token不读、恢复token可读，五个非法快照拒绝。SSE三片消费全wire32940/decoded32769，精确正文、空message.body、HTTP完成；finished活对象16MiB与析构后全零及FD13→12分别验证。F-001与新增测试问题均关闭，原Release根因不回溯声称已复现。

| 验收 | 最终独立证据与结论 |
| --- | --- |
| AC/RV01 | 57cell、7590唯一ID；7104正式=6783成功+321 queue_full；486预热=477+9；无未发/未开始/超时/协议或传输错误，逐ID独立复算通过 |
| AC/RV02 | A连接模式及N限定诊断；B正式pause/resume84/84、74/74、84/84，逐波快流先完成，正文与排空通过 |
| AC/RV03 | H20/H60/Q60各3/3有效对；LI−RR分别三次+3.333333/+11req/s；Q8−Q0为−17/−13/−16.5，负面结果保留 |
| AC/RV04 | 六R cell各12正式/2预热全成功；固定CPU双实例各0→1→7聚合generation，正式P走gateway，无逐ID后端推断或GPU声明 |
| AC/RV05 | 三预设各21/21；资源账/FD归基线，RSS增量≤32MiB；1GiB运行期预算、239PID回收及身份审计通过 |

Reviewer T为1294.710178/2157.664633/1149.669975req/s，machine_drift=false，其余发压敏感/CPU限制均true；Builder漂移true历史保留。有效到达配对满足门槛并不取消工具限制，无容量或因果收益结论。详见[结果追加比较](../../../performance/V0.4/S1-results.md)，两个角色数据不合池。

### 文档、保护与交接

同步README、ROADMAP、ARCHITECTURE、CHANGELOG的当前状态及验收入口；README当前CTest数量为21，旧阶段实跑数量保持历史。ARCHITECTURE仅阐明既有对象所有权及新增测试工具边界，不改变产品架构。结果文件原Builder内容完整保留，仅追加独立接受、双角色比较和限制。本报告为新编号006，不覆盖任何旧报告或Approved权威。

证据目录`build-local/leader/v0.4-s1/evidence`保存closeout006-before.json、closeout006-check.json/.log：核对既有docs/src/tests/CMake身份，唯一允许既有文档差异为结果文件追加，原结果全文为新文件前缀；源/测试/旧权威/报告/Stop不变。另检查六份收口文档本地链接、代码围栏与git diff --check；精确Reviewer/Builder SHA及分支HEAD保持。未再次执行已接受测试/矩阵。

独立接受已具备，Leader据此关闭S1；无债务接受、无范围放宽、无新优化，未启动S2。本报告为提交前快照：协调者随后精确选择阶段文件、本地提交并核验，不推送；不因提交哈希追加循环改写本报告。
