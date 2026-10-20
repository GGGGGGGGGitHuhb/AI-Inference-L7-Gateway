# V0.3/S1 独立审查计划

2026-10-20，`Approved`，待实现，0/2。用户明确启动V0.3/S1并保留技术委托，Leader批准；[S1-design](../../../leader/designs/V0.3/S1-design.md)为行为权威，[Leader001](../../../leader/reports/V0.3/S1-report-001.md)记录批准包。该计划仅规定验证方法，不扩S2队列/准入、S3真实综合验收或V0.4优化。起点e231fda25879060fcd730f562982f06448f2ba11，codex/v0.3-s1-routing-health。

## 审查输入与路线

读取根ROADMAP/ARCHITECTURE、Approved设计及后续正式rework（如有）、Builder最新报告/拆解/来源、P1及V0.2/S3最新接受记录、实际受影响C++/配置/测试。无项目Reviewer guide则用plan-project-docs全局模板并披露；读取personal-cpp-standards规则正反例。原生WSL /bin/bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway；独立build-local/reviewer/v0.3-s1/{tmp,cache,evidence,debug,release,asan}，执行前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。socket/LSan首次按已知边界精准升级，不关闭sanitizer；无下载、真实模型或P1长矩阵。Builder停止自身负载后再执行，不共享可变端口/进程/构建。

## 必需审查矩阵

| RV/AC | 方法与独立通过证据 |
| --- | --- |
| 01 配置兼容 | 逐个负控设计§3的重复键、深度、未知/缺字段、空数组、非法策略、类型/数量/乘积上限、自指含端口0、两模式冲突；验证旧JSON/程序构造及任意有效model透传。检查配置≤64KiB和实际有界数据结构；日志保留失败启动exit而非仅捕获异常后不检查 |
| 02 选择隔离 | 独立C++确定性序列断言RR和LI tie-break，socket门控保持不同请求inflight；实际造多个idle与长流，证明决策由请求计数而非连接计数。2model各2backend记录请求model/body/Host/实例计数；同物理地址跨model池独立。未知模型404/model_not_found和全不可用503/no_available_backend没有上游新请求 |
| 03 健康语义 | 用可推进单调时钟测试阈值边界/中立/重置/冷却/唯一Trial/失败与中立重新冷却/恢复；旧epoch晚到成功及失败均不影响新状态；独立受控服务TCP可达但返回404/503，不能恢复。分别验证400/429中立、401/403/3xx/5xx失败；完整响应前不早记status，迟到截断仅一次Failure |
| 04 生命周期 | 静态追踪每个终结调用，验证route lease和ConnectionLease独立。门控下游排空前观察非流/流上游HTTP已完成且inflight=0；已记录成功后取消不覆盖；pool满/本地预算/total/downstream timeout中立、明确上游故障失败。摘除清idle且老epoch lease不可再归池；Trial取消/停止释放、没有新健康timer/悬空observer；构造失败/重复finish/析构保持幂等 |
| 05 端到端回归 | 新RoutingE2E在正式网关上完成每实例≥3次摘除/试探恢复；同请求只发一次；失败原请求502/504、后续无实例503；已提交流断流无第二HTTP状态或伪成功零块。SIGTERM覆盖idle/活动流/Trial并在原shutdown护栏收口，进程/FD/账本/定时器清理证据齐全 |
| 06 构建文档身份 | 独立debug/release/asan完整CTest、格式实跑与人工回调/空行审查；核对源/二进制hash与测试日期/命令/退出码。README新配置/被动恢复及协议健康局限、旧命令仍可用；S1不提前写MVP已完成或性能收益；原Approved/历史报告/第三方不改 |

三预设配置命令：cmake --preset debug -B build-local/reviewer/v0.3-s1/debug；cmake --build同目录 -j4；ctest --test-dir同目录 --output-on-failure。release/asan同样分别选对应preset/独立目录。新增预期CTest名Routing和RoutingE2E，审查前ctest -N核对实际注册，报告实际命令/数量；不根据预期目标虚构通过。格式使用仓库clang-format-18，覆盖本次改动C++；不要求全仓排版。纯状态测试可引用Builder实现，但Reviewer须独立检查预期、额外构造旧epoch/Trial取消/多idle的关键序列，不能只复述Builder结果。

## 高风险解释与判定

健康Available启动仅代表配置许可；完整2xx是现有HTTP协议成功，非生成文本/模型权重/GPU真实性证明，TCP/首片不构成恢复。被动冷却不自发发请求，无流量不恢复；用户请求本身承担试探且无重试。计数在上游终结释放而非下游完成，残留ConnectionLease独立防止跨epoch归池；这些必须在报告与测试断言一致。

因本地背压暂停到期response deadline为Neutral，未暂停明确response/stream_idle timeout为Failure；total始终Neutral。并发先终结结果唯一，不能用粗FinishReason覆盖。池满503不标健康Failure，不对另一个实例自动补发；S1不实现S2容量调度。

PASS仅当全部AC已执行验证、无未接受Blocker/Major/Minor且证据可复查；行为错误、丢/重复计数、迟到事件复活、缺关键回归为必返工。环境限制使关键验证不能执行则BLOCKED并保留原始输出，不降级成假通过。重大债务不得自接；无预设性能目标，不因测值波动加产品优化。当前最多2轮返工，累计跨原因/角色；Reviewer只写下一编号报告、不改权威/实现、不提交推送。PASS后Leader再收口，协调者本地提交不推送。
