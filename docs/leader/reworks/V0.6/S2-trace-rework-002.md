# V0.6/S2-trace 返工002：发送就绪与双向背压测试前提

Approved，2026-10-31。依用户本轮实施/验证授权，由Leader采纳两个有直接证据的隔离测试修正；不改变产品行为、性能门槛或原断言。补充[返工001](S2-trace-rework-001.md)，001五处accept就绪要求全部保留。本文件仅扩大[S2-trace设计](../../designs/V0.6/S2-trace-design.md)§2隔离测试补丁范围和§6准备回归方式。

## 触发事实与限制

1. metrics在接入就绪修复后，独立U出现“TCP bytes must be immediate before close”。Builder临时取证为send=-1/errno11、TCP_INFO state=2、bytes=0/active=1（l4-metrics-send-debug.log）。测试将s.connecting强写false，但内核连接尚在SYN_SENT；不能据此认定产品漏计正send字节。
2. Reviewer U的TCP shutdown forced场景为pending=[0,65160]，PID已回收。源两向各提交173760字节，握手每向8字节；periodic c2b=173768表示该方向已全部正send给内核，b2c=108608的差额65160与屏障一致。脚本把“源曾EAGAIN、之后计数平台”当作双向用户队列非空，却没有检查源是否已经耗尽。记录只证明此前提不足，不证明EAGAIN的内核/调度根因。Builder一次该场景通过不抵消Reviewer失败；finally触发的forced日志不是正式场景通过证据。

## 修正要求

- RW01：隔离tests/metrics_tcp_test.cpp首个实际后端连接，在人工设s.connecting=false及即时7字节断言前，增加后端fd POLLOUT的单调截止≤1秒等待，并检查SO_ERROR==0；错误/超时明确FAIL。只用于这条要求真实可写的连接，不应用于后续故意挂起/错误/超时的连接，不修改产品SO_ERROR读取或accept/send循环。保持7字节、11字节、active及关闭幂等断言。
- RW02：隔离tests/v04_shutdown_product.py仅修改deadline/forced场景的负载准备逻辑。使用原64KiB模式块继续有界补充两方向数据，每次正send后撤销该方向“当前受阻”标记；EAGAIN仅表示当前状态。持续采集periodic，要求两向都有未转发差额（完整提交量加握手减正send计数为正）、至少两个相同的有效periodic计数且两个源当前受阻，才允许发送第一个停止信号。不能把源已经全部转发后的平台当成背压。
- RW03：负载准备总截止不超过原两步8+8=16秒；每方向实际提交硬限16MiB，达到上限而前提仍不成立即FAIL。复用固定块，不累计存储全部payload，非阻塞循环需有有界等待避免忙等。记录提交量、选用的periodic快照、差额和当前受阻状态。指标差额本身不是用户态队列证明：消费停止信号后的原结构化pending屏障仍须两向非零。
- RW04：保留第二SIGINT、1秒生产deadline、listener摘除、无丢失伪称、错误路径与PID/FD清理等全部原断言和失败报告；不将all(pending)改成any，不新增跳过，不把cleanup中的信号日志当作正式通过。其余场景及外部L4原脚本不动，补丁只在本仓隔离副本使用。

## 核验与收口

Builder保留全部首错与临时取证，更新版本化补丁和实际源身份；先用无进程的谓词用例证明“源已耗尽平台”不会通过，以及提交量/时限边界，然后按原命令完成暂停的U/O TCP相关回归。Reviewer核对原断言保持和两类前提，再在自有副本独立完成U/O回归；仅测试改动不触发无关Gateway重复回归。

本次是建立测试前提，不是修复产品或宣称默认转发收益。仍禁止性能采样，直到准备回归、观察设施和清单冻结通过；18cell/1200秒/4GiB及所有开销/归因阈值不变。若修正后再失败，保留真实现场并评估，不能继续无限补测或删掉相关测试。最终报告披露两份返工及实际独立结论，本文件不提前判定PASS。
