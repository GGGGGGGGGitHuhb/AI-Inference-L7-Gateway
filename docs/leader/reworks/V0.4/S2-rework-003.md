# V0.4/S2 返工003：执行边界取证与完整独立复验

**Approved**，2026-10-21。用户在[Stop001](../../reports/V0.4/S2-stop-001.md)之后明确回复“批准”，允许新增一次有限继续；累计 **3/3**，不是重置此前2/2。Leader按该授权采纳本文件及[Leader005](../../reports/V0.4/S2-report-005.md)。仅更新返工002“2/2后不得继续”的执行额度与本次复验路线，001/002其余限制及原设计/审查全部保持。

## 诊断与边界

Reviewer只读诊断：`build-local/reviewer/v0.4-s2/evidence/stop001-readonly-diagnosis.md` SHA256 `d408057c8238dda36abee95b576cd4f87756c72eba290142610e40d38a7f675c`，配套JSON SHA `e9edf5c8194a100597699aa5f0fc1fd0b904c863205c0eae42bb3724a1f9fce3`。原exec和write_stdin均await，yield1000ms并非总超时；没有未await Promise或shell timeout证据。外层session62465返回143，只说明外层退出结果，**Python实际接收信号、发送者及确切根因未知**。

原run001完成14/21，cell14处理中；raw标记跨度约212.446s，资源204.272s，不是精确终止时刻，也未显示到达原900s/cell60s期限。无result/exit/traceback，说明正常记账未完成，不证明是谁中止。两遗留backend已按精确run路径安全清理。所有旧run/Stop/失败历史保留，不能补造成功或把14cell拼入新run。

## 本轮允许与要求

RW01（AC03/05）：只在Reviewer evidence目录新增标准库生命周期supervisor，产品、测试、配置、源/binary均不变。采用诊断提案：监督进程自身启用Linux PR_SET_CHILD_SUBREAPER，runner以start_new_session启动，使用原命令/环境；记录PID/PGID/monotonic起止、收到的SIGTERM/SIGINT/SIGHUP、实际child returncode与正常/超时/异常路径。外部stop首次只转发一次，给10s原清理机会，再对仍存活自有子进程KILL/wait。外层watchdog960s，至多另10s清理，不改runner900s/cell60s/client16s。

OwnedProcess子进程各有自己的session，不能假定kill runner PGID会回收所有后代；只对supervisor直接收养子进程，记录PID/命令及归属后有限终止/waitpid，正常结束亦核对残留；禁止按泛进程名批量杀进程。监督事件≤64KiB、runner console≤1MiB，溢出失败不丢弃证据；这些是单独有界外层执行日志，不修改原实验1GiB分区预算、采样或样本。wrapper不生成请求、不安装依赖、不修改系统配置。执行始终await persistent exec，逐次await write_stdin≤30s并保留至完成，不detach/遗留promise。

该封装改善取证与回收，**不宣称已修复未知中止来源**，也不能保证宿主整体终止时仍存活。若信号来源再次不明，保留不确定性，不用PASS回填Stop001根因。

RW02（AC01/05）：复用已有独立Debug/Release/ASan各21/21、controls001、control-audit与独立反例，前提是重新核对identity-before.json（SHA `cc1b0765e887fc151957d778ff581b544deeb3986240842994b0cf43cd6100e7`）中249保护文件、9源/配置/说明及42自有binary逐项一致，保留日志hash和复用证明。新增Leader权威不属于测量源改变；不得误称旧测试为本轮重跑。若发现影响执行的身份漂移，先停报而非自动重测/改源。

RW03（AC02–04）：仅执行一次全新`run-002`，完整21cell/2970ID，不复用旧14cell、不拼Builder样本、不增加样本或补跑单元；原计划、到达/SLO/分母/有效三元组/不过载/推荐门槛与预算全保持。完整结束后独立自写逐ID审计、资源/预算/进程闭合与准确身份报告。任何新的阻塞、执行失败或需纠正的问题停止，**不得自行开始第4轮或run003**。

## 交接与接受

本轮由Reviewer执行边界封装和独立测量，Builder实现已冻结，不交回产品开发。独立审查报告必须区分历史测试复用、run001外部中断与新run002，记录wrapper开销/实际期限/清理；关键验收不足仍BLOCKED或FAIL，不能当债项隐藏。满足全部AC后才可PASS，Leader随后新报告收口、同步文档，协调者本地提交、不推送。旧Approved与Stop001均不覆盖；没有新增产品功能/真实推理收益声明或后续阶段。
