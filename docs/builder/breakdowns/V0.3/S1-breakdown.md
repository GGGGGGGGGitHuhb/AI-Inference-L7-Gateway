# V0.3/S1 实施拆解

依据 Approved S1-design / S1-review，2026-10-20，初次实现，返工0/2。使用全局 Builder guide 回退，无项目角色指南。

| 子阶段 | 范围/模块 | 依赖 | 验证 | 状态 |
| --- | --- | --- | --- | --- |
| B1 | GatewayConfig 严格多模型配置 | 无 | 正负配置及旧兼容 | 实现及自测完成 |
| B2 | routing 选择/健康/请求租约 | B1 | 确定性时钟 Routing | 实现及自测完成 |
| B3 | Runtime 多池/Session 终结映射与epoch归池 | B2 | 生命周期及旧回归 | 实现及自测完成 |
| B4 | 多后端端到端与文档 | B3 | RoutingE2E/三预设/格式 | 实现及自测完成 |

执行路线：原生WSL，/bin/bash login=false，仓库根目录；独立 build-local/builder/v0.3-s1/{tmp,cache,evidence,debug,release,asan}。构建/Python设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME；socket/LSan精准升级。无依赖下载、不改历史/P1/Approved、不提交推送。自测不是独立验收。

当前全部子阶段完成Builder自测，独立验收待Reviewer。最终三套17/17，Routing277断言、RoutingE2E183检查；报告S1-report-001.md记录失败自检、类型化解析分类、补齐测试和最终身份。无提交推送。

## 首次有限交付返工

2026-10-20，累计1/2。Reviewer001功能通过、F-001空行Minor待纠正。已严格仅补两文件7处函数边界空行，14文件格式检查及人工复核通过；86其他源及双方39产物保持，按明确许可复用初审功能证据，不重建/重测。Builder001人工检查结论由Builder002纠正，独立复验待执行；未提交推送。
