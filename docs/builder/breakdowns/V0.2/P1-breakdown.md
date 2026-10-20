# V0.2/P1 实施拆解

2026-10-19；Ready for Review，初次实现，累计返工0/2。权威为[设计](../../../leader/designs/V0.2/P1-design.md)及[审查计划](../../../reviewer/reviews/V0.2/P1-review.md)。无项目 Builder 指南，使用 plan-project-docs 全局 Builder 模板。

| 子阶段 | 目标/模块 | 依赖 | 验证 | 状态 |
| --- | --- | --- | --- | --- |
| M1 | tests/performance 独立计时客户端、固定后端、调度/资源/汇总 | Approved | HTTP完成/EOF/内容事件及异常完整性负控 | 已完成 |
| M2 | Release构建及完整回归 | M1 | CTest与离线负控 | 已完成 |
| M3 | 69cell及3控制，独立固定CPU资产 | M1/M2 | 计数、身份、原始样本、资源和回收 | 已完成 |
| M4 | 用户结果报告、Builder报告及审计 | M3 | 逐cell重算/历史保护 | 已完成 |

使用原生WSL bash login=false，build-local/builder/v0.2-p1 独立tmp/cache/evidence/release，显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。产品、旧工具与历史保持；正式压测顺序进行，不提交或推送。

## 自测进度

M1/M2已实现并最终Release15/15（26.65秒）；初次--check路径冲突exit2日志保留，最终修复后负控通过。M3首run-001完整72cell/744.68秒，19,380含预热唯一attempt、0失败；交付前自查双发压中断结果保存，协同停止已通过实际SIGTERM：单/双均16已开始=16保存，112未开始，外层exit1、双子进程exit0并回收。未交付前自测不计返工，P1仍0/2。最终run-002在固定新身份下进行唯一一次完整重跑；两次数据均报告，源码/输入/负载差异明确。

## 最终交付

M1–M4全部完成Builder实现/自测，等待Reviewer，累计0/2。run-002完整72cell/698.969秒、19,380含预热唯一样本、0失败；最终Release15/15。54项测量源/2运行二进制与当前匹配，12项Release产物另列；143保护项仅授权CMake变化。所有102服务进程及双发压子进程已回收。用户结果与两次完整cell附表、Builder001及final-audit交付；未提交/推送。详细依据见[Builder001](../../reports/V0.2/P1-report-001.md)。
