# V0.4/S2 返工002：AdmissionE2E退出证据优先

**Approved**，2026-10-21，Leader按用户技术委托及本阶段有限返工授权采纳，累计 **2/2，最后一轮**。依据[设计](../../designs/V0.4/S2-design.md)、[审查计划](../../../reviewer/reviews/V0.4/S2-review.md)、[返工001](S2-rework-001.md)及[Builder002](../../../builder/reports/V0.4/S2-report-002.md) SHA256 `7ce9ec31d3a5ff582ed9125eb5ead96a4e5d45ea51531552e9242a8b633761ab`。本文件不撤销返工001，不扩大产品改动授权。

## 触发与已知边界

controls-002已通过；Debug/Release各21/21，ASan20/21。旧AdmissionE2E在1.63秒内于RunAdmission.py:241的finally→Gateway.close:141非零退出断言失败，stderr空；不是120秒测试超时。原工具未记录实际returncode/signal，TemporaryDirectory退出删除了trace。首次具体退出原因**未知**，无sanitizer文本不等于证明没有问题。

源码存在显式SIGTERM后finally再poll/send_signal路径；SignalSource析构恢复oldMask，构成退出期信号竞争假设，但不能据此断定原失败原因。正式21cell尚未开始，所有原证据及236保护项保持。

## A：唯一诊断，先取证后决策

RW01（AC03/05、RV03/05）：Builder先记录当前ASan AdmissionRuntimeHost SHA、旧RunAdmission.py SHA及诊断差异。仅在`build-local/builder/v0.4-s2/evidence/admission-diagnostic-001/`建立原脚本的独立诊断副本/包装，不改受保护原脚本或产品，不重编binary。副本保留原negative_checks场景及顺序、全部断言、超时、信号发送次数/时机决策、清理逻辑；只添加有界日志与保存原临时config/trace，不通过sleep、重试、提前wait或减少信号改变行为。

使用同一ASan host binary**最多一次**针对AdmissionE2E原负控路径的诊断运行，不运行mixed/全量/正式矩阵。沿用原环境与socket/LSan窄权限，不禁sanitizer。日志至少包含monotonic时刻、case标识、PID及启动/ready、每次poll结果、每次显式及close中的信号调用来源/信号值/结果、communicate开始/结束/异常、实际returncode（负值对应信号）、stdout/stderr、可用最后trace及临时配置、父异常与回收结果。可以同步记录/proc下进程信号掩码/状态，读取失败也留痕；不以进程消失猜测具体信号。诊断副本与差异一并保存，限16MiB日志、120秒外层期限，只清理自有进程。

**A结束必须停止并向协调者和Leader回报证据，不能自动执行B。** 一次诊断PASS不关闭首次失败；若未复现或仍缺关键因果证据，判定诊断不足，保留未知，不继续循环/称flake/靠历史通过接受。原失败不能改写为已复现。

## B：有证据才可有限纠正

RW02：只有A与源码链共同证明明确的**测试teardown重复控制信号**导致退出失败、且不需改变产品语义时，Leader才可在本轮已有授权内记录B允许继续的具体证据与范围，并由协调者交Builder。条件不满足、出现产品缺陷或需额外实验时保持停止，不授权产品修复或第三轮返工。

符合条件时，REQ01“旧测试不修改”仅对`tests/admission/RunAdmission.py`作以下条件例外：最小修正测试停止请求的所有权/幂等性，避免清理重复请求；保留正常/强制停止的原产品测试场景、严格returncode==0、sanitizer无错误、六项终态零值、队列gateway_stopping断言、期限和全部负控。不得接受−SIGTERM等非零值、catch忽略错误、跳过场景或增加sleep等待“稳定”。诊断取证可作为有界测试错误信息保留。其余235原保护文件、产品二进制、S1权威/历史全部保持；不改CMake或产品信号实现。

RW03：B获准后先新独立输出运行修后目标测试一次，再按原设计完成三预设全量各一次；既有成功历史保留为修前证据，不混称修后。必要的幂等清理反例应确定性证明一次请求和仍能发现非零退出，而不是重复整套赌概率。随后执行原唯一21cell正式run，负控工具未变可按精确源/产物身份复用controls-002。后续任何新阻塞失败停止，**不得启动第三轮纠正**。

## 独立复核与收口

Reviewer核查A原始退出/信号证据与局限、B继续的书面依据、精确例外diff和保护hash；独立运行修后测试/三套和原完整矩阵，检查停止/零资源/非零退出负控。无证据或关键路径不确定为BLOCKED，缺陷为FAIL，不能降级债项。

所有设计参数、SLO、分母、推荐门槛、21cell/2970ID、预算、用户默认1000ms和提交不推送保持。新Builder003与Leader后续报告保存诊断/修复/未完成；不得覆盖Builder001/002、controls001/002、原ASan失败或原Approved。独立接受前阶段未完成；本返工仅两阶段有限授权，不提前宣布根因或PASS。
