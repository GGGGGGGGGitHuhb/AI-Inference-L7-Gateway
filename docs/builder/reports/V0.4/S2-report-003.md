# V0.4/S2 Builder 诊断报告003（仅A）

2026-10-21，累计返工 **2/2**。[返工002](../../../leader/reworks/V0.4/S2-rework-002.md) A已执行唯一一次，**诊断复现非零退出并已停止，未执行B**。原首次ASan失败实际退出码未知的边界保持。

## 权威、范围与执行

依据Approved返工002 SHA256 `2ba1b374c572cdf92a8b9b18d27126c36b237a2450752c7565e2ec6a472ca542`及[Leader003](../../../leader/reports/V0.4/S2-report-003.md) SHA256 `866e1f1f61c0add658061b9c5e2cca9540d59bdf98f4e49c8b6673f02ce989ed`，沿用原设计、审查、返工001和[Builder002](S2-report-002.md)。路线仍为独立Builder v0.4-s2 tmp/cache/evidence、原生WSL bash login=false和显式环境变量，loopback/LSan窄权限；无安装、重编译、产品改动或正式发压。

在`build-local/builder/v0.4-s2/evidence/admission-diagnostic-001/`创建原RunAdmission.py的诊断副本，仅包裹Popen poll/send_signal/communicate以记录返回值和时刻，ready时落日志，TemporaryDirectory退出前保存config/trace。原negative_checks顺序、断言、timeout、signal决策和清理不变；没有增加sleep、wait、retry或减少信号。诊断副本、diff、identity.json均保存。日志仪表会有执行开销，不能声称与无仪表时序完全相同。

原脚本SHA256 `a5d3326d46ba11d7ec4f80701ef43ba34a97e536810540a78eb4a494799165de`；同ASan AdmissionRuntimeHost SHA256 `1f5157330bb1388149c69ecc25b08ab92a4b5fc6cb173bed2ada64b7d5be21ba`，诊断前后相同。副本SHA256 `df985408c5dc8cf1ac137049145d37ee2e0a533661e77941f7a9a7be7b858b62`。

```bash
/usr/bin/timeout --kill-after=5s 120s /usr/bin/prlimit --core=0:0 --fsize=16777216:16777216 -- python3 build-local/builder/v0.4-s2/evidence/admission-diagnostic-001/RunAdmissionDiagnostic.py /home/power/projects/AI-Inference-L7-Gateway/build-local/builder/v0.4-s2/asan/AdmissionRuntimeHost
```

外层120s期限，脚本累计写预算16MiB；实际证据目录33909字节（此数在写本报告前统计）。唯一命令退出1，未触发timeout/预算。原异常传播为AssertionError，stdout/stderr和退出记录保留在command.log/events.jsonl。

## A实测事实

case1 PID24614、case2 PID24618各一次close发SIGTERM，communicate returncode=0。case3 PID24621为shutdown路径：

| monotonic_ns | 事件 |
| --- | --- |
| 73344221880845 | negative_checks显式调用SIGTERM；SigBlk=0x4002 |
| 73344222235370 | 第一次signal调用返回 |
| 73344223941210 | finally close的poll返回None |
| 73344224490388 | close再次调用SIGTERM；SigBlk=0x4002，SigPnd/ShdPnd当时0 |
| 73344224883276 | 第二次signal调用返回 |
| 73344226743962 | communicate完成，实际returncode=−15（SIGTERM），stdout/stderr均空 |

case3已保存最终trace：排队请求outcome=gateway_stopping、dispatched=0；active流outcome=cancelled；final_queue/final_bytes/final_inflight/final_sessions/final_reserved/final_timers六项全0。原队列503 gateway_stopping断言通过，随后returncode==0断言按原行为失败。三个子进程均通过communicate回收，parent_finish逐PID记录退出码；随后ps确认三个PID均不存在。

这些证据证明**本次诊断**确有同一PID的teardown第二次SIGTERM及SIGTERM终止；不同于此前只有空AssertionError。源码SignalSource析构先关闭signalfd再恢复oldMask，提供第二信号在退出阶段解除屏蔽后终止进程的机制链。未直接采样到恢复mask的系统调用或第二信号入pending瞬间，不能把推断的每个内核时点当实测。原首次失败没有退出码，不能回填为已确认−15。

## 交接与未完成

已向协调者回报并停在A。候选最小纠正范围是测试停止请求所有权/幂等性；具体B授权由Leader书面决定，Builder未修改原RunAdmission.py、产品或S2工具，未执行目标复测、三套回归或正式矩阵。此前Debug/Release成功、ASan失败与controls002证据保留。若Leader不批准B，维持停止；不存在第三轮自动修复授权。
