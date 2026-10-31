# S2-trace Leader004：一次工具修复验证失败，停止

## 第一部分：PM决策摘要

2026-10-31，Blocked。依用户“先修测试工具，修一次如果还不行就停”，仅修改一次停止通知逻辑并执行一次验证。现有SelfTest 12/12、MatrixTest 9/9通过；新增真实退出测试因验证命令参数冲突退出2，测试主体未运行。随后重置控制和性能均未启动。已停止，不追加修改或重试。

修复有效性未确认，不能关闭Reviewer001的M1，也不能宣布工具或阶段通过。这次失败属于协调者构造验证入口的失误，不是产品故障，也不证明新的停止逻辑无效。按用户既定要求提交推送失败快照；不合并或发布，不自动继续任务。

## 第二部分：实施、证据与停止边界

依据[返工003](../../reworks/V0.6/S2-trace-rework-003.md)，在原生WSL及本轮独立tmp/cache/evidence目录执行，协调者直接完成，无新代理或依赖。停止通知统一为Owned.request_stop，先标记请求再检查进程/发送TERM；close_all和Owned.close共用一次请求。通知错误、非零退出、原截止与kill/reap规则保持。更新既有mock，并新增两个真实子进程退出窗口测试。未修改Gateway/L4产品、ResetBackend或旧capacity工具。

唯一验证序列：SelfTest.py -f（12/12，0.017s）；MatrixTest.py -f（9/9，0.013s）；ShutdownTest.py -f（退出2）。后者入口已指定unittest.main(failfast=True)，unittest因此不提供-f参数，命令报unrecognized arguments: -f。没有启动该脚本的真实子进程，重置控制control_started=false。虽然可判断参数问题，本轮依用户限制不删除参数重跑、不再改实现或测试。

全验证0.345396608秒，结果failed。本机原始记录在build-local/leader/v0.6-s2-trace-fix1/evidence/{inputs.json,validation.json,SelfTest.py.log,MatrixTest.py.log,ShutdownTest.py.log}；[发布的结果副本](../../../performance/V0.6/S2-trace-fix1-summary.json)保留原数据。执行前保存新工具与旧失败run逐文件SHA，停止后只读核对均未变化。原冻结manifest、旧3项控制失败和15项not_started不回填。本次没有新网络控制或性能样本。

README/ROADMAP及诊断说明仅追加此次停止状态；不覆写历史报告，不写入代表验收完成的CHANGELOG。提交只是保存未完成修复，M1、AC2/3/4和S2入口继续未验证/BLOCKED。没有进一步执行授权请求；本轮到此停止。
