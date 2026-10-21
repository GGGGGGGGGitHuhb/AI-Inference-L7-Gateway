# V0.4/S2 Leader：同轮B继续确认004

2026-10-21，At Risk；累计返工 **2/2，不新增轮次**。

## 第一部分：PM 决策摘要

**结论：诊断证据满足既定条件，可以进入本轮B最小测试修复。** 唯一诊断捕获到测试先请求停止、清理时又向同一进程发送SIGTERM，随后进程因SIGTERM退出；队列拒绝行为与六项资源已正确归零。修复测试对停止请求的所有权，产品保持不变。

**计划与实际：** A已完成并保留失败证据，未通过重复运行寻求PASS。现在允许修正既有测试的一处清理路径，保留严格零退出与所有队列/停止/资源要求，然后定向验证、三套完整回归及原21cell实验；尚无性能结果。

**重大偏差与风险：** 这是最后一轮内的条件B，仍为2/2。首次失败未记录退出码，不能回填为已确定的SIGTERM；本次诊断的信号发送与−15是实测，解除屏蔽的精确内核时点仍是源码解释。后续新阻塞须停止，不自行开始第三轮。

**PM决策：None。** [返工002](../../reworks/V0.4/S2-rework-002.md)已规定该条件例外，本确认只认定A证据满足B条件，不新增范围或放宽验收。下一步由Builder最小修复并提交新报告，再交独立Reviewer；完成后文档收口、本地提交不推送的规则不变。

## 第二部分：详细工作记录

供PM按需查阅。

### 已核查证据与结论边界

读取[Builder003](../../../builder/reports/V0.4/S2-report-003.md) SHA256 `93e0432f750add661867b64e30c6480f9ed5f8bb3525ce4fad6636b47cd87f13`，及`build-local/builder/v0.4-s2/evidence/admission-diagnostic-001/`中的events.jsonl、diagnostic.diff、identity.json、case-3-communicated-trace.json。events SHA256 `e735959a88dba50465d881f086ca0286fa311d25e51263f9364780e353066e40`。同ASan AdmissionRuntimeHost SHA `1f5157330bb1388149c69ecc25b08ab92a4b5fc6cb173bed2ada64b7d5be21ba`、原脚本SHA `a5d3326d46ba11d7ec4f80701ef43ba34a97e536810540a78eb4a494799165de`保持；副本只增观察/保存，不改变原控制流和断言，但有仪表开销。

case3 PID24621在73344221880845ns由negative_checks请求SIGTERM；73344223941210ns close poll=None，73344224490388ns又请求SIGTERM，两次调用均返回；第二次前SigBlk=0x4002。73344226743962ns communicate返回−15，stdout/stderr空。case1/2各一次SIGTERM且退出0，三个PID均reaped。case3最终trace六项全零，queued outcome gateway_stopping且dispatch0，active流cancelled；原503断言已通过，非零退出断言仍失败。

这确认诊断场景存在重复停止控制及SIGTERM终止，结合SignalSource析构恢复信号掩码足以进入既定测试所有权修复。没有直接记录sigprocmask恢复或pending瞬间，不将这些内核时点称为实测；首次无日志失败的精确原因不回填。原诊断失败保留，不能标为通过。

### B精确允许范围与验证顺序

仅按返工002 RW02例外修改`tests/admission/RunAdmission.py`：测试Gateway统一管理已经请求停止的状态，使显式shutdown和finally清理共享幂等停止入口，避免清理再发送重复SIGTERM。允许Builder选择最小清晰实现；不能依赖sleep、弱化returncode==0、接受−15或跳过停止场景。保留非零退出/ASan/UBSan失败与六项资源零值检查，保留队列503 gateway_stopping及正常/强制停止的已有产品测试保障。产品src、CMake及另外235保护项原字节保持。

必要的确定性小反例在同一测试文件或独立证据脚本验证“重复请求只发一次”和“子进程非零退出仍失败”；不得用重复整个AdmissionE2E取代机制验证。失败信息可增强为实际退出码/已发信号等有界诊断，不能改变退出判定。

1. 保存精确diff、保护hash及binary身份，执行上述确定性控制。
2. 同ASan host对修后AdmissionE2E定向执行一次，记录全部结果；失败立即停止。
3. 修后Debug/Release/ASan完整CTest各一次，分别记录，保留修前21/21、21/21、20/21历史，不拼接为修后通过。
4. 三套成功后执行原唯一正式21cell run-001。S2工具和host binary若精确不变，controls-002按身份复用，不重新执行无关控制；原SLO、分母、推荐门槛及预算不变。
5. Builder写新报告004，Reviewer按原计划和两返工独立验收，核查条件例外与失败留存。任何新阻塞停止，没有第三轮纠正授权。

继续使用各角色v0.4-s2独立tmp/cache/evidence、原生WSL bash login=false及显式环境、已知socket/LSan窄权限。Leader本次只核查和新增本报告；原Approved返工002 SHA `2ba1b374c572cdf92a8b9b18d27126c36b237a2450752c7565e2ec6a472ca542`不改写，设计/审查门槛全部保持。git diff --check通过，B尚未执行，阶段未完成。
