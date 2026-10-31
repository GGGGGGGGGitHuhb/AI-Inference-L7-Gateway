# V0.6/S1 返工004：统一退出读取异常与独立复验续采

Approved，2026-10-29。依据用户S1执行授权、新增Reviewer精确取证及其独立安全判断，Leader批准统一既有窗口外退出确认机制；不增加正常采样等待，不修改产品、正式矩阵、SLO或累计预算。Builder完整72项保持，Reviewer原33项不重发。

## 触发证据

Reviewer以v4 SHA256 `a559456acd9851c51a14b877fcfb42bdfe829c144bd4c61efdf71ebc245fe692`从头采集，第33项`F-A-L-3840-r1`收口首停：cleanup阶段l4lb PID166168的`/proc/166168/stat`已不可读，抛FileNotFoundError，即时poll无退出码。v4仅对PermissionError等待，故该分支没有进行有界确认。事件在formal_end后43.195092ms、最后client close后37.035458ms；6个子进程最终exit0且回收，33项原始请求/资源已独立复算通过。

第33项真实结果为63869成功、12821传输失败、110漏发，达标83.16276%，不得删除失败或因采样修正重发。Reviewer目前42cell=9控制/负控+33正式，39正式及末2诊断尚未执行。原始失败、未执行计划、来源与累计账本保留。

## 有限修正与安全门槛

1. PermissionError/FileNotFoundError/ProcessLookupError统一使用“自有子进程、实际时间≥formal_end、阶段为request-drain/fd-drain/cleanup”门槛。仅窗口外可用即时退出码或无信号wait≤min(100ms,cell剩余活动期限)确认退出；确认退出才跳过该样本。三类异常在窗口内或控制器自身均fatal，即使即时poll已返回也不得绕过。已确认消失TID的细粒度处理保持原边界，进程总ticks仍权威。
2. 保留原异常时刻/phase/PID、初始poll、wait起止/实际耗时/结果/超时/调用栈及动作。仍活、超时或其他wait异常均fatal。正常100ms采样、请求时间戳、正文和统计逻辑不变；不据此宣称已证明具体内核或CPython退出竞争根因。
3. 定向负控覆盖三类异常的窗口内拒绝、窗口外真实退出、延迟确认、超时仍活、控制器异常和不发送信号；窗口标签不替代实际时间检查。只复验必要工具测试，不重复产品构建/回归或重新发压已有正式点。
4. 为现有固定恢复机制增加唯一Reviewer profile：`reviewer-v4-prefix33`。父清单和初始formal-plan/provenance均为原v4，前32项complete、第33项仅上述精确ENOENT首错；绑定Reviewer原plan/provenance SHA、唯一失败PID/事件、源码/二进制、所有输入指纹、磁盘spec、完整进程集合及累计账本。不能把Builder的33项前缀或其他run套用此profile，也不要求Reviewer具备Builder的v1/r2/r3采集文件。
5. Reviewer在自有证据目录生成33项派生审计及summary，保留原failed/result；Builder仅实现工具，不写Reviewer证据。Leader保留v4清单为`S1-manifest-v4.json`并冻结v5，保持72项全部参数/顺序/数值语义。Reviewer独立核对最终hash、父链、33项守恒、预算后仅续采39个新ID，再执行原附加诊断计划的反向两项控制。

## 验收与范围

该变更是已有安全退出确认机制对同类读取异常的完整覆盖，不是忽略错误、降低资源门槛或产品优化。全部活动继续计入Reviewer原120cell/90min/2GiB上限，派生与预检也记实际开销；不重新开账本。Builder原72项数值及证据不变，只记录其工具版本边界。任何窗口内或等待超时等失败仍立即停止，不延长等待或自动放行。

原REQ01–08、AC01–04与S2产品证据门槛保持。Reviewer最终报告应披露本次独立首停、完整历史修正链、真实低达标点与未解决归因，不将“恢复后完成”写成“首次无错误”。

附加诊断计划的数值参数、Builder32→64与Reviewer64→32顺序保持；原计划中的v4工具引用留作采集前历史记录。Reviewer末两项依本返工使用v5窗口外退出确认，报告必须披露该工具版本差异，不改写已执行Builder控制的计划或证据。
