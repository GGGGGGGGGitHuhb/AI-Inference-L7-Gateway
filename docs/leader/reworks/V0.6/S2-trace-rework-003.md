# S2-trace返工003：一次停止通知修复

状态：Approved，2026-10-31。用户明确“先修测试工具，修一次如果还不行就停”。授权仅一轮工具修复和验证；任何验证失败立即停止，不进行第二轮修改、不恢复性能矩阵。

依据Reviewer001 Major M1：close_all与Owned.close重复发送TERM；上轮reset-peer退出-15。重复路径已确认，具体致死信号时序没有证据。本次不将假设改写成旧现场根因。

只修改TraceRuntime停止通知为同一子进程幂等请求，两条清理入口共用；保持批量先通知、共享截止、kill/reap、非零退出FAIL。补真实子进程在恢复SIGTERM默认处理后的退出窗口验证，并更新既有测试替身。Gateway/L4产品和旧冻结工具、原失败清单/账本不变。

验证固定一轮：现有SelfTest/MatrixTest及新增两项真实进程测试按failfast执行；通过后只运行一次peer-reset控制（一个业务连接、原60秒/16MiB限制），使用旧已核验诊断二进制，另建fix1证据目录及新工具指纹。任何失败均不重试、不再改实现；后续只记录结果、回收与提交推送。即使通过，也只表明本项工具缺陷修复，未验证性能或整个取证阶段，不解锁原15项性能。

路线沿用原生WSL；本次tmp/cache/evidence位于build-local/leader/v0.6-s2-trace-fix1，显式环境变量，无依赖安装/系统配置/外部L4写入。协调者直接完成此窄修，使用agent-execution-route和plan-project-docs；不新增角色或扩大工作。
