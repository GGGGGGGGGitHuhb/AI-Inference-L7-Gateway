# V0.3/S2 Leader 收口报告002

2026-10-20，Leader (Zeus)。Completed / 独立验收通过，累计返工0/2。

## 第一部分：PM 决策摘要

**结论与健康状态：On Track，S2已完成。** Reviewer001独立PASS，无未关闭发现、债务或阻塞；V0.3整体/MVP仍待S3，S3未启动。

**计划与实际：** 已交付显式启用的全局/每实例请求限额、每模型有界FIFO、count/byte预算、排队取消/超时、跨模型轮转及停止清理。排队保留原请求和内存预约，不占上游租约；总期限不重置，出队重新选择健康且有容量的实例，额度恰一次释放。未配置admission时保持既有行为，无自动重试。

**验收证据：** Reviewer独立debug/release/asan各19/19，额外4组122断言及7条charge断言，FD 4→4。固定24条长短混合全部成功，22排队、2直派，FIFO一致、全局峰值2/每实例1，末态各计数归零。

**边界与风险：** 同模型FIFO仍可能让短请求等待长请求；本次有限样本不证明长期无饥饿、公平性或性能收益。队列逻辑字节不等于RSS，容量仍受原Session预约约束；有序FIN不能总被判定为取消，以期限收口。没有新真实模型/GPU实验，未处理P1约44ms现象。

**PM决策：None。** 下一步由协调者精确暂存并本地提交，不推送；本报告不宣称提交已经发生，不自动开始S3。

## 第二部分：详细工作记录

供PM按需查阅。

### 权威与阶段身份

分支 `codex/v0.3-s2-admission-queue`，起点 `b704df268e2865bda146ba4c816dd105e6c8302c`。S1推送为用户报告，本轮未独立核验远端。以下Approved规划包保持原文，待实现文字属于规划时点：

- [设计](../../designs/V0.3/S2-design.md)：SHA256 `002b00cdb5501d1e86326e02160dc9eaf785e4b11ed56fd116174a8c3078ded3`。
- [审查计划](../../../reviewer/reviews/V0.3/S2-review.md)：SHA256 `a3adaec952fcf85c4942827af108354784f3c063a3476ad3c5afd51e4b60f8c7`。
- [Leader001](S2-report-001.md)：SHA256 `c3927110ba03c6cac6136f6d123cc394320923adc5be590652bd3ed2da8f7230`。

采用全局plan-project-docs Leader模板回退；项目无专用Leader指南。沿agent-execution-route原生WSL、`/bin/bash` login=false、仓库原生路径及Leader独立tmp/cache/evidence，脚本显式设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME。无债项，不创建空债务清单。

### 实现和独立接受

[实施拆解](../../../builder/breakdowns/V0.3/S2-breakdown.md)和[来源边界](../../../references/V0.3-S2-changes.md)记录各模块。AdmissionController只拥有稳定ID与队列账；Session拥有原请求，Router拥有唯一inflight。Runtime在cleanup每次最多处理32项，必要时单合并任务续轮，弱有效期token防止停止后悬空调用。纯容量阻塞不忙轮；释放、取消、超时和健康结果触发调度。无健康时拒绝503，不等待冷却；选中传输池满为中立容量错误，不重排。SHUT_WR保留请求等待语义，RST取消；stop拒绝等待者，活动请求沿原有限排空。

[Builder001](../../../builder/reports/V0.3/S2-report-001.md) SHA256 `212ad53033fe20e0f2db04ef85733a1c9c3cc30c958ca36f38eb8a226af18fc7`。首次ASan测试时钟前提失败、修正后完整通过及最终仅Admission测试变更后的定向复测/其他18项复用均保留，不改写历史。

[Reviewer001](../../../reviewer/reports/V0.3/S2-report-001.md) SHA256 `83ad0ef3cba0cc97d21c49a1f7b0f1fcb1bda040d8c7d085d81de2ca247e474a` 独立完整重建与测试：debug 19/19（35.03s）、release 19/19（30.75s）、asan/ubsan 19/19（48.31s），无检测器错误。额外覆盖队头取消、deadline与释放同刻、请求额度释放但传输池仍满、超过32项续轮与停止等组合，122断言+charge7断言、FD 4→4；旧137项保护核验通过。Reviewer证据不是Builder或旧阶段结果复用。

独立Release混合只运行一次：两模型各12请求（9短/3长），24/24成功、68检查，22排队/2直派；实际入队和派发顺序验证FIFO。全局峰值2、每实例1，队列峰22项/26286逻辑字节，最终queue/bytes/inflight/sessions/reserved/timers均零。短请求排队中位数约480/489ms、最大765/772ms，体现本负载下长短等待，不能外推吞吐、容量、SLO或长期公平性。全部相关进程已回收。

### 收口保护与交接

独立证据目录 `build-local/reviewer/v0.3-s2/evidence/`：94源清单 `source-sha256.json` SHA256 `febfcc184489b3efe49870b91d658715e46c6f52eebe764e5c2ac69b76396c7f`；45产物清单 `binaries-sha256.json` SHA256 `233b56b7d967bfc8e5d9b6b9a050aff84cd67913a41b81e41356c57e5048805e`。收口复核清单对应文件保持一致。

本轮仅更新根README/ROADMAP/ARCHITECTURE/CHANGELOG与本报告；文首和版本表同步S2完成/S3未启动，旧日期条目及S1收口明确历史快照。Leader `build-local/leader/v0.3-s2/evidence/closing-protected.json` 保留修改前保护快照，链接/围栏/diff及身份检查见 `closing-check.log`，五份文档SHA见 `closing-identity.json`。没有修改产品、测试、Approved权威或他人报告，没有重复构建/测试。

独立接受条件满足，S2关闭；累计0/2，无rework、债务或待决策项。协调者随后本地提交、不推送；S3综合验收、V0.4性能优化及正式发布均不在此次收口内。
