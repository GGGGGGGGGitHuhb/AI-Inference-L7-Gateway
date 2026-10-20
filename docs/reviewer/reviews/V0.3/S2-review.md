# V0.3/S2 独立审查计划

2026-10-20，`Approved`，待实现，0/2。用户明确启动S2及既有技术委托授权；[设计](../../../leader/designs/V0.3/S2-design.md)为行为权威，[Leader001](../../../leader/reports/V0.3/S2-report-001.md)为批准包。本计划只细化方法，不扩S3/V0.4或修改设计。

## 输入与路线

读取当前Approved、Builder最新拆解/报告/来源/原始混合样本、S1最终Reviewer002/Leader002、根文档及受影响源码。无专用Reviewer指南则全局plan-project-docs模板回退；读取agent-execution-route和personal-cpp-standards规则正反例。原生WSL /bin/bash login=false，仓库/home/power/projects/AI-Inference-L7-Gateway，codex/v0.3-s2-admission-queue，起点b704df268e2865bda146ba4c816dd105e6c8302c。独立build-local/reviewer/v0.3-s2/{tmp,cache,evidence,debug,release,asan}，显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME，socket/LSan精确首次升级。无模型/依赖下载，无P1长性能矩阵；不共享Builder进程、端口、构建或可变数据。

## 逐项方法与通过依据

| RV/AC | 独立检查与必需实证 |
| --- | --- |
| 01 配置兼容 | 枚举admission每字段上下界/错误类型/bool/未知/重复、legacy拒绝、缺省禁用及直接构造验证；旧S1/legacy全部断言保留，旧样例不变；新示例可解析/启动 |
| 02 容量与路由 | 门控global2/perbackend1双模型四实例，逐次检查global=sum(router inflight)、每实例限额；容量不足不占Trial/推游标。多个idle/下游持lease而inflight0、pool满中立503，无改投；出队重选当前健康实例 |
| 03 队列与预算 | 从保留请求独立计算charge，UTF-8/头/body/1024全覆盖；count/bytes恰满与超1、零额度、单项过大、异步取消/异常插入/重复finish守恒。检查Waiting无route/connection/stream lease，只有原Session预约，不复制正文进queue或预分配大上限 |
| 04 时间健康 | 可推进时钟验证queue/total先后、恰等与同时total优先，派发前再检查，total跨等待不刷新；排队期间健康摘除/恢复/LI负载变化，健康全无503移除而非等待冷却；Trial中立及旧epoch保护 |
| 05 事件停止 | 实际socket完整请求后SHUT_WR仍获响应，RST移除队首/中部；无新请求时释放容量能立即推进；>32项有界续轮无漏唤醒；纯阻塞无task自旋；停止包含Waiting/运行流/idle/续轮task且所有账/FD/timer清理 |
| 06 混合与交付 | 独立执行设计固定24请求一次，原始时刻/ID/实际FIFO/24成功和限额守恒；按model及长短重算等待median/max及样本分母；三预设完整CTest与额外关键组合、格式/人工空行/源产物及历史身份齐备 |

Reviewer独立编写关键组合序列或小探针，至少覆盖：取消FIFO头后另一模型进展、队首total恰到期且同事件释放容量、pool仍满但请求容量已释放、>32项续轮与停止相遇。不得仅导入Builder统计函数冒充独立复算；小型标准库复算混合样本即可，不要求通用统计框架。

正式运行三套：cmake --preset debug -B build-local/reviewer/v0.3-s2/debug；cmake --build同目录 -j4；ctest --test-dir同目录 --output-on-failure，release/asan分别替换。预期新增Admission/AdmissionE2E，实际ctest -N确认数量并记录命令/exit/时间/日志。混合入口读取Builder实际新增CLI，在自己目录独立运行Release一次；不得凭计划声称执行。C++格式clang-format-18覆盖修改范围，人工函数边界检查不可只信工具。旧测试不改预期掩盖回归。

## 生命周期重点

Controller只存稳定ID/逻辑charge，Session保留正文一次，Runtime拥有所有对象；RequestLease是实例inflight唯一可变真值，全局求和。入队、出队、取消和停止各分支强异常/幂等；失败落盘和未派发计数不能遗漏。下游半关闭不是可证明取消，完整close无法与SHUT_WR区分时依赖deadline是明确边界。

容量释放只标记dirty，具名调度在回调结束后执行；续轮至多一个task，安全owner/token与stop顺序可证，不能保存悬空Session捕获。模型头FIFO与跨模型轮转须按实际进入顺序验证，线程启动顺序不是入队顺序。健康全无立即拒绝意味着没有等待冷却的存量队列；不要遗漏健康变化通知，也不能新增主动探针。

## 判定与报告

全部AC实际验证且无未接受发现才能PASS。队列无界/漏账/重复派发/超发/悬空回调/取消误删SHUT_WR/期限刷新/关键验证缺失必须纠正，不得转为性能局限。环境阻塞关键验收用BLOCKED并保留证据。固定混合24成功为正确性场景要求；额外过载负控的503/timeout分开报告。有限样本不证明长期无饥饿、严格公平、开放负载SLO或性能收益。

创建Reviewer新编号报告，列逐AC、实际命令/日志、源码binary SHA、所有进程回收、未测范围、发现和返工次数；不覆盖历史/Approved/实现。根状态交Leader最终同步，协调者本地提交不推送；用户报告S1已推送不是Reviewer独立远端核验。当前阶段最多2轮返工，无自动债务接受，不提前宣布V0.3/MVP完成。
