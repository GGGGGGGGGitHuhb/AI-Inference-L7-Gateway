# V0.2/S2 Builder 拆解

Approved S2-design/S2-review及Leader001，初次实现0/2；原生WSL/builder/v0.2-s2独立路线。无项目指南，使用全局Builder/stage-design模板。保留S1历史及Leader根文档。

| 步骤 | 目标/依赖 | 验证 | 当前 |
| --- | --- | --- | --- |
| M1 | 配置、唯一预算、容量凭证/快照 | 类型/边界/失败回滚/真实capacity | 完成自测 |
| M2 | 依M1接入水位及租约DEL/新token | CL/chunked/EOF真实双轮暂停恢复、无recv与精确正文 | 完成自测 |
| M3 | 依M2接入idle冻结/write进展及幂等终结 | IO跨截止矩阵/取消/停止/资源基线 | 完成自测 |
| M4 | 完整回归/身份/格式/报告 | 三预设、旧关闭20、S1反例、人工逐函数复核 | 完成自测 |

角色不提交、不推送、不扩S3。完成仅交独立Reviewer，非阶段接受。

M1—M4自测完成，三套12/12、旧关闭窗口20/20、S1 response/total各18/18，正式交付Builder001与当前来源记录。仍累计0/2，待Reviewer独立审查；首轮测试预期/后端缓冲失败及修正日志保留。
