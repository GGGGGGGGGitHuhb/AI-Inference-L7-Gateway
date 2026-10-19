# V0.1/S2 Leader 第1轮返工决策报告 002

日期：2026-10-18。Leader (Zeus)。阶段 `返工中`，编排 `Reworking`；S2累计 **1/2**，S1历史2/2不变。

## 第一部分：PM 决策摘要

**当前结论：At Risk，可继续第1轮统一修正。** S2已有可运行代理，现有三套测试各7/7通过，但独立关闭窗口探针20次中1次丢失整个首响应，Reviewer结论FAIL，不能关闭阶段。

**决定与取舍：** 完整响应提交后先关闭写方向，继续有界读取丢弃额外输入，再在对端结束或固定期限关闭。正常路径最多1秒且不超过总截止；错误路径共享原错误排空窗口，不额外延长。关闭期间保留会话额度，因此客户端不结束时会短暂占槽；原容量、停止及公平要求不变。

**计划与实际：** 已形成 Approved [返工002](../../reworks/rework-002.md)，同时要求修正本阶段新C++函数间空行和职责分组。当前仅完成决策，产品尚未修复或复验；不把改变后端延迟后的测试通过当作问题解决。

**重大范围变化或债务接受：None。PM决策：None。** 按既有技术委托落实单请求可靠关闭，不加入第二请求、连接池或新依赖。有限关闭不能保证在RST、网络失败、强制停止或期限耗尽后客户端仍必然读完；原有限120/150ms跨窗口反例必须保留完整响应验收。

**下一步：** Builder (Hephaestus) 修复两发现并交002报告；Reviewer (Athena) 独立复验原反例、截止/资源及完整回归。当前累计1/2，任何再次纠正计入第2轮，第三轮前按Olympus停止。

## 第二部分：详细工作记录

本部分供PM按需查阅。

### 输入与决策依据

读取S2 Approved设计/审查、Builder001、Reviewer001与`build-local/reviewer/s2/evidence/close-window.log`，检查ProxySession、SessionIo、Runtime终结入口和现有状态。沿用agent-execution-route、personal-cpp-standards及完整正反例、plan-project-docs/Leader模板回退，重读返工指南。项目仍无专用角色指南，不建立第二套编码规则。

用户技术授权“你来决策吧”和最新阶段授权“推送好了，开始s2吧”涵盖本阶段常规生命周期修正；原§5关闭表述与额外输入不影响首响应的要求存在实现时序冲突，故通过新返工权威明确，不改原Approved文件。全仓rework-002对应S2第1轮，与S1 rework-001无覆盖关系。

实际观察：20次关闭探针中索引8响应0字节，其余19次105字节；后端120ms返回而客户端150ms继续发送。writeDownstream成功即finishSession、下游直接close。RFC 9112 §9.6支持分阶段关闭方向，但未抓包，不声称已确认内核RST序列。参见 [RFC关闭说明](https://www.rfc-editor.org/rfc/rfc9112.html#section-9.6)。

### 修订与验证边界

返工RW-01—03明确closing状态：一次写半关闭、EAGAIN继续等待、EOF或绝对期限结束；正常 `min(totalDeadline, outputCompletedAt+1000ms)`，错误共享原errorDeadline；shutdown强制截止、第二停止信号和RST优先。保留单次上游、有限每事件处理、全额预约至cleanup、无二次响应和延迟Channel销毁。没有加入无界等待或应用层ACK协议。

RW-04将Reviewer的Minor排版项同轮修复：限定S2自有改动，clang-format后人工逐文件确认函数/成员分组，不能只依赖dry-run成功。若涉及S2复用目标，只更新对应目标hash和差异理由，不动源身份。

复验必须保留原20次120/150ms反例和新的握手时序覆盖，真实Socket/接缝证据分开；错误响应、EOF先到、EAGAIN、持续额外输入、总deadline、共享错误窗口、停止优先级及容量恢复均有对应RV。三套完整回归仍必需，不能只延迟后端或放宽响应断言。

### 权威、状态与交接

新增Approved `docs/leader/reworks/rework-002.md`和本报告，必要根文档当前状态同步为S2返工中/1轮，并链接新权威；不生成已完成变更日志。原S2设计hash `a8d0206472e85bbb8facc5ba668c1aa4964803f48d7737cca659855aafc9de51`，审查hash `c8ad195e1c0a75155f91912179dc92bcd9187bf281329a063ef49b733a63c471` 保持；原报告和S1历史不变。

执行路线继续WSL `/bin/bash` login=false，cwd仓库，分支codex/v0.1-s2-proxy，HEAD bb318d8c55f5851d27cd52e6cd3367f450a5d8dd。Leader临时/缓存/证据使用build-local/leader/s2并显式设置环境；兄弟只读。未改产品/测试、未构建或重跑探针、未提交推送或派生角色。

文档链接/围栏/空白/两层报告、原权威散列和当前计数校验记录 `build-local/leader/s2/evidence/r1-authority-doc-check.log`。下一手为Builder002，随后Reviewer002；两项发现仍未关闭，不宣称任何新增验收结果。
