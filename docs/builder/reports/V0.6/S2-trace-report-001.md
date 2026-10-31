# V0.6/S2-trace Builder报告001：采集前准备

状态：准备完成，待Leader/Reviewer核对冻结与采集授权；不是阶段PASS。2026-10-31。依据Approved设计、review及返工001/002。无18cell功能负控或性能请求已发出；候选目录为空，账本未开始。不提交/推送，由Leader统一处理。

## 实现与范围

Gateway `GATEWAY_CONNECTION_TRACE`默认OFF；U不编译观察字段/调用，O仅启动时判断环境且热路径无新增时钟/端点查询，T固定256B聚合记录原位补齐。成功accept互斥分类、独立代数、closing/finished/实际移除分别计数；处理startSession在发布前结束及异常路径，不改资源释放/调度/HTTP语义。L4仅本仓隔离实际dirty副本，TCP/health原同线程维护共享池，保留首次已读errno/侧而不重复SO_ERROR查询；显式健康出站tuple，未知仍unknown。

每进程131071槽+256B头恰32MiB；高档含warm88320请求按每个Gateway都可能接收全量计算，额外42751槽用于健康/其他。满则drop并失败，不覆盖。停止后分片导出、头最后写；进程SIGALRM10秒与控制器同绝对cell期限双重约束。每自有child无论通知/等待异常均进入kill/reap；共享60秒清理期限，不逐child重新延长。

新Client/Backend适配器在U/O/T一致记录端点，原计划ID/正文/时钟/终态保持。解析器核header、数目、PID、接入分类、阶段顺序、结束/移除、客户端metadata ID与时刻；tuple+相交生命周期唯一才关联，复用冲突/缺端点/未知健康不猜。Matrix固定18项、不可CLI覆盖关键条件、失败首停无resume、每cell独立checkpoint和最终summary；early reserve后错误收为failed；summary后再次核全轮时间/证据。新工具详见tests/connection_diagnosis/README.md。

## 本轮验证与真实失败

| 验证 | 实际结果 | 本机证据（build-local/builder/v0.6-s2-trace/evidence/） |
|---|---|---|
| Gateway Release U完整 | 21/21，42.29s | gateway-ctest-u.log |
| Gateway Release O完整 | 22/22，41.17s | gateway-ctest-o.log |
| Gateway Debug trace ASan+UBSan O受影响 | 7/7，30.47s | gateway-sanitizer-o.log |
| L4 Release U TCP，CPP005 | 13/13，54.58s | l4-ctest-u-rework002.log |
| L4 Release O TCP，CPP005 | 13/13，54.60s | l4-ctest-o-rework002.log |
| 解析/生命周期无socket自测 | 12/12 | python-selftest-004.log |
| 固定矩阵/门槛/首停/入口/预算模拟 | 9/9 | matrix-selftest-002.log |
| 耗尽平台/当前受阻/时限纯谓词 | 3/3 | fixture-rework002-test-003.log |

Sanitizer使用GATEWAY_CONNECTION_TRACE=ON、GATEWAY_SANITIZERS=ON、Debug，ASAN_OPTIONS=detect_leaks=1、UBSAN_OPTIONS=halt_on_error=1；实际覆盖Runtime、Gateway/Reuse/Streaming/Admission/Routing E2E和ConnectionTrace专门单元。O产品回归不冒称T全负载验证；T功能分支与关联仍由冻结后三项负控验证。C++单元已覆盖启用记录、关闭零记录、幂等/满槽和结束早于发布。

保留首次失败：L4原metrics accept4 EAGAIN导致created前提未建立；RW001仅五处真实连接增加POLLIN≤1秒。随后metrics实际send=-1/EAGAIN、TCP_INFO SYN_SENT，RW002只首条需要真实可写的连接等POLLOUT+SO_ERROR0；原7/11字节断言保持。独立shutdown forced源耗尽形成伪双向平台，RW002固定块继续补充、正send重置blocked、两向差额正和两个相同periodic才进入停止；16秒/每向16MiB硬限，接受前再检查，all(pending)等原断言未变。全部早期日志/debug保留本机，debug不进入补丁；不将测试前提修复当产品优化。

## 冻结候选与预算

- 代码源快照：`build-local/builder/v0.6-s2-trace/evidence/source-freeze-cpp-005.json`，SHA256 `33073dc06c0177678b3594ff091b263aeea0d441c4257b31a737c7b789680807`。
- 诊断补丁：`tests/connection_diagnosis/L4ConnectionTrace.patch`，SHA256 `239af4f6d435229d810192bf7fb549ab9fd70b109f13373d567edac09c85c6c4`。外部dirty diff未发布。
- 候选：`build-local/builder/v0.6-s2-trace/evidence/manifest-001.json`，SHA256 `3228eb3a9d96934c45a1fcb6713386a70e1591c0dfcf78ad407daefda004bbed`。仍Draft，不能执行；全部新工具、旧capacity只读依赖、4二进制/CMakeCache、源和CPU均逐文件SHA在files字段。只读内存设Frozen验证通过，不更改磁盘Draft。

三负控按连接上限/预约失败/对端reset，仅2/2/1条客户端连接；保持各≤64、16MiB。低档9项1920 UOT/OTU/TUO；同repeat全门槛通过才运行高档6项3840 UT/TU/UT。参数固定A1024B、warm3+duration20、两发压/总slots128、双GW cap32/512MiB预约/stream4MiB、单backend、无queue/reuse，继承亲和性与100ms采样。低档全部有效且good≥99%，相邻对照good绝对差≤1pp、HTTP P95/P99和全链CPU成本增幅≤10%；高档T/U good差≤2pp和CPU≤10%，不满足即条件性观察并BLOCKED。不能把负控配置引入性能样本。

最坏每性能cell：88320×1664+3×33554432=247627776B，距256MiB尚20807680B固定余量，覆盖分片头、非请求日志、资源/config/汇总。整矩阵15×256+3×16+128=4016MiB，另加当前准备证据仍需≤4GiB，双角色磁盘预留8GiB。全入口1200秒/每cell60秒，单child AS128MiB，运行期合计RSS1GiB/FD2048。冻结校验检查隔离L4全部原275文件及补丁新文件集合、外部原始文件hash与Gateway实际源。所有压力仍等Leader明示冻结授权，最终入口/归因结论未产生。
