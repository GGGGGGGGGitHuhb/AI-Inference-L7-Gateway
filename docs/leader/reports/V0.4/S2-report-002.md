# V0.4/S2 Leader 返工报告002

2026-10-21，Approved返工，S2累计1/2。

## 第一部分：PM 决策摘要

**结论：At Risk，可以按一轮有限修正继续。** 新测试后端按大小写敏感方式查HTTP字段，不兼容网关正常的小写字段；上游很快失败，真实占位条件未建立，控制测试因此停止。当前没有正式性能结果，也没有证据表明产品队列有缺陷。

**计划与实际：** 已完成Release构建、离线控制和三份配置加载；真实排队超时控制失败，完整回归和21cell矩阵尚未进行。先修新控制工具的字段识别与失败留存，再按原门槛执行，不改变范围、SLO或候选参数。

**重大偏差与风险：** 已消耗S2第1/2轮返工。首次线程异常未落盘，只能报告源码不兼容与外部观测一致，不能冒称捕获了具体KeyError。旧失败全部保留。

**PM决策：None。** 这是既有授权范围内的测试纠正，无产品行为、依赖、预算或验收标准变化，Leader批准[返工001](../../reworks/V0.4/S2-rework-001.md)，无需重复确认。下一步Builder修正单个新Python文件并完成原验证，随后独立Reviewer；再失败先保留证据交Leader，不无限循环。

## 第二部分：详细工作记录

供PM按需查阅。

已读Builder001 SHA256 `bd90d6135e6eca9ced74990acedd6280067bd4d40b7e754e6a2f2ba622f98658`、controls-001.log、real-timeout/transitions.jsonl、failure001-audit.json及DetectorTests源码。两个会话均dispatch至backend0/1，随后upstream_error；gate记录为actual two occupied slots超时。新后端普通dict用`X-Experiment-Id`索引，与正常小写字段不符；errors只在内存，第一次具体异常无法追回。四Host start/reaped闭合，236保护项原字节保持。

[返工001](../../reworks/V0.4/S2-rework-001.md) SHA256 `87a4aa4eb633c7a0710c0c9393a43c015a9f1a85b4aa83c1668c420b808d5eb4`。仅授权DetectorTests字段名大小写无关与小写/混合控制、finally有界取证，允许新说明/拆解/Builder002同步。原design/review SHA及REQ/AC全保持，不替换权威；明确真实占位→入队→504未派发→释放→排空完整路径。先新controls-002，成功才继续原三套与唯一正式run-001。

执行路线沿用原生WSL bash login=false、仓库原生路径、各角色v0.4-s2独立tmp/cache/evidence及显式环境变量；Leader仅文档和只读核查，无代码修正/构建/测试，Builder已停止且无并发修改。共享Leader模板回退继续适用。新增两文档，旧报告/失败证据/Approved设计均保留；git diff --check及权威hash核对通过。Reviewer仍须独立接受，当前阶段未完成，不提交或推送。
