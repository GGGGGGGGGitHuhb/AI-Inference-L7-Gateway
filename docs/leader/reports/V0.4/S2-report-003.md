# V0.4/S2 Leader 诊断返工报告003

2026-10-21，At Risk，S2累计返工 **2/2**。

## 第一部分：PM 决策摘要

**结论：先诊断，暂不继续性能实验。** 新控制工具已修好，但旧ASan准入测试在退出检查失败；目前缺少实际退出码，原因尚不能确定。Debug/Release各21/21，ASan20/21，正式矩阵未开始。

**计划与实际：** 最后一轮返工先用原二进制执行一次带完整退出/信号记录的定向诊断。诊断完成必须先回报；只有证明是测试清理重复信号的问题，才能最小修正该测试并保留全部停止/资源验收条件。不会先改产品或反复跑到通过。

**重大偏差与风险：** 已使用2/2返工额度。若诊断不足、出现产品问题或后续新阻塞，将停止并明确剩余问题，不能追加第三轮。原失败无具体退出码，不能回溯宣称其根因已知。

**PM决策：None。** 有限诊断与条件性测试纠正属于当前技术委托及阶段范围；[返工002](../../reworks/V0.4/S2-rework-002.md)批准A诊断，不自动批准进入B。下一步Builder一次取证，Leader/协调者根据证据判断能否在同轮继续；独立验收及文档收口仍未完成，不提交或推送。

## 第二部分：详细工作记录

供PM按需查阅。

输入Builder002 SHA256 `7ce9ec31d3a5ff582ed9125eb5ead96a4e5d45ea51531552e9242a8b633761ab`、ctest-asan.log及旧RunAdmission.py/RuntimeHost.cpp/SignalSource.cpp。ASan AdmissionE2E在1.63s于finally Gateway.close的returncode==0失败，空stderr；原临时文件被删除，不能识别实际signal。两次SIGTERM路径与析构恢复信号掩码是候选机制，不是结论。controls-002真排队100ms超时、无派发及drain通过，不需推翻；正式矩阵未运行。

[返工002](../../reworks/V0.4/S2-rework-002.md) SHA256 `2ba1b374c572cdf92a8b9b18d27126c36b237a2450752c7565e2ec6a472ca542`。A仅在独立evidence目录生成诊断副本，原脚本/同ASan binary保持，最多一次执行，记录PID/时刻/信号调用/实际returncode/trace与回收。诊断后强制先回报。条件B仅在因果证据明确后允许旧RunAdmission.py最小测试停止所有权修正；235其他保护项保持，产品完全不改。任何非零退出仍须失败，不以重复pass关闭。

RW01→AC03/05取证；RW02→REQ01条件例外仅旧Python测试；RW03保持原回归/矩阵与独立接受路径。原设计/审查与返工001不覆写，当前2/2为最终额度，诊断不足或新阻塞停止。具体命令/副本差异由Builder报告，Leader不代做实现/测试。

路线仍为原生WSL bash login=false，repo=/home/power/projects/AI-Inference-L7-Gateway，各角色v0.4-s2独立tmp/cache/evidence，显式环境与已知socket/LSan窄权限。没有新增依赖、下载或系统调优。新增返工002/Leader003，仅做只读核查与文档；git diff --check通过，原设计/审查hash不变。当前仍At Risk，未来PASS需Reviewer独立证据。
