# V0.1/S2 独立审查计划

状态：`Approved`；日期：2026-10-18；Leader (Zeus) 按用户“推送好了，开始s2吧”及技术决策委托采纳。当前 S2 累计返工 0/2。

唯一阶段行为依据为 [S2 设计](../../../leader/designs/V0.1/S2-design.md)，本文件细化方法，不增加功能或削弱验收。前置 S1 已独立 PASS；其历史 2/2 不计入新阶段。读 ARCHITECTURE/ROADMAP、S2 Leader 最新报告、Builder 最新报告及所有后续适用返工；项目无 Reviewer 指南时使用全局模板。发现已批准设计冲突先报告，不能自行改验收。

## 1. 独立执行路径

原生 WSL2、`/bin/bash`、login=false，仓库根目录。先建立目录并设置：

```bash
mkdir -p build-local/reviewer/s2/tmp build-local/reviewer/s2/cache build-local/reviewer/s2/evidence
export TMPDIR="$PWD/build-local/reviewer/s2/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/reviewer/s2/cache"
cmake --preset debug -B build-local/reviewer/s2/debug
cmake --build build-local/reviewer/s2/debug -j 2
ctest --test-dir build-local/reviewer/s2/debug --output-on-failure
cmake --preset release -B build-local/reviewer/s2/release
cmake --build build-local/reviewer/s2/release -j 2
ctest --test-dir build-local/reviewer/s2/release --output-on-failure
cmake --preset asan -B build-local/reviewer/s2/asan
cmake --build build-local/reviewer/s2/asan -j 2
ctest --test-dir build-local/reviewer/s2/asan --output-on-failure
```

以上预设已存在；新产品和新增测试目标由本阶段 Builder 实现，不能声称此刻已运行。测试 socket 权限为已知边界，按精确命令升级，不先重复旧沙箱失败。使用 Reviewer 自有临时配置、日志、进程和端口，不能用 Builder 可变实例。测试监听 127.0.0.1:0，通过 READY 获取端口；启动/测试/退出均有限超时，finally 仅终止并等待本测试子进程。

## 2. 必需矩阵

| 条目 | 来源 | 方法、证据与通过条件 |
| --- | --- | --- |
| RV-01 来源/事件安全 | REQ/AC-01，§3/6 | 逐项从固定Server提交取六文件并重算源/目标hash，查适配差异及依赖闭包；运行注销后旧token、同批事件销毁另一Channel、fd数字复用、回调后清理、取消/过期计时器用例。检查无裸fd事件身份和回调自析构。生命周期错误为Blocker，来源缺证Major |
| RV-02 配置与启动 | REQ/AC-02，§4 | 独立生成缺字段、重复键、未知键、类型/bool/浮点、地址/端口、64KiB和数值边界配置；检查错误码2且无READY/监听/上游联系；有效端口0可连接，bind失败退出1，help退出0。可见行为错为Major |
| RV-03 完整代理 | REQ/AC-03，§5 | 独立客户端→独立Gateway→Mock真实Socket；固定/分块/EOF/1xx/204/304/4xx/5xx/合法未注册状态、早期最终响应；比对原始JSON和响应字节，Host/CL/Via/Connection close及认证移除。请求/响应任意分片，第二请求绝不派发，坏请求/Expect在上游记录中为零。串扰/定界错误Blocker，缺功能Major |
| RV-04 IO与生命周期 | REQ/AC-04，§6 | 故意短写/EAGAIN和EINTR，读取尾字节与RDHUP同现、完整请求SHUT_WR后继续收到响应、请求截断EOF、客户端RST/上游RST、timeout与就绪/终结竞争。重复连接与fd复用，观察活动会话/上游/定时器/预约归零；健康并行请求继续。UAF/泄漏/重复释放Blocker |
| RV-05 资源/公平 | REQ/AC-05，§7 | 设置max_connections=2和预约只容1/2会话，测试N−1/N/N+1占用、拒绝与释放后再接入；max_reserved不足一个槽的配置拒绝。独立审查逻辑存储副本上限计算及前置容量检查；大合法头/请求/响应+慢读下无无界缓存。热连接连续额外输入不能阻止其他请求/计时器。RSS另作观测不替代协议预算；越限或泄漏Blocker |
| RV-06 deadline/停止 | REQ/AC-06，§8 | 各阶段单独制造延迟，验证408/502/504及code、总deadline不被分片刷新、错误排空上限；已发响应后只能关闭。connect超时用确定性接缝+真实成功/拒绝，不能只用路由黑洞。SIGTERM排空活动正常请求、拖住请求后强制截止、第二信号立即终结；端口关闭/进程退出，恢复资源。缺关键路径Major，生命周期损害Blocker |
| RV-07 全回归与文档 | REQ/AC-07，§9—11 | 独立三套完整CTest、manifest、S1全部回归、Release主动失败、ASan/UBSan。实际执行README启动和格式检查；无SSE/池/路由/队列/后续阶段提前实现。核实最新报告与代码身份。必需证据缺失Major，环境不能执行为BLOCKED |

每项记录实际输入、命令、退出码、观察及源码/配置身份；不能只写“已覆盖”。单元接缝用于保证罕见 syscall/时钟分支触发，不能替代真实代理集成。产品日志不得包含prompt/正文/凭据，观察用合成唯一标记检查stdout/stderr。

## 3. 攻击性与时序重点

- 第一请求与第二请求同批/跨批到达，确保上游只见第一条，第一条可正确返回；额外数据不无限缓冲或延长deadline。
- 上游在收到请求头后即返回最终错误，网关尚有待发正文：不能死锁，也不能重试。上游1xx后最终响应仍仅生成一个最终下游状态行。
- 下游SHUT_WR不是取消；RST或send失败才按可观察取消收口。不能以FIN本身要求立即结束已完整请求。
- 接收过程中预算超限、解析错误、上游超限/截断、生成错误响应时bad_alloc：受影响请求终止，其他请求仍可完成；无法分配错误响应可以关闭。
- timer/Channel回调执行中终结自身或另一会话，确保延迟析构与token查表；操作真实复用fd或可验证的事件注入，不只检查代码字符串。
- 先有待发数据再遇EAGAIN，后续恢复发送完整；没有待写数据不维持OUT兴趣；stop/timeout在持续就绪事件下依然推进。
- 等待/timeout测试以明确握手或可控事件为主，短deadline配合理调度容差；记录实际起止时刻，不把粗sleep或机器忙造成偶发结果当唯一依据。
- 构建测试有限时限、每个自有子进程可回收。异常退出也检查监听关闭，不使用全局进程名kill。

## 4. 证据与结论

Reviewer 记录分支/HEAD及工作区源hash；查看所有修改文件，不覆盖Builder日志。原始证据放 `build-local/reviewer/s2/evidence/`，日志保持初次失败和后续重试，编号不覆盖历史。独立复核clang-format18范围、版本和结果，实际执行Release `FoundationTests --intentional-failure`返回1，以及所有新增测试不会被NDEBUG关闭。

每项发现关联REQ/AC/RV，给最小复现、期望/实际、严重程度和阻塞性。报告路径 `docs/reviewer/reports/V0.1/S2-report-001.md`，之后按S2独立递增。

PASS要求全部AC具有独立证据；PASS WITH DEBT只允许明确批准且不影响核心目标的债务。定界歧义、内存/生命周期错误、失控容量、缺必需真实链路或sanitizer证据不得债务化。实现不满足为FAIL；环境限制阻止关键验收为BLOCKED，不能跳过后PASS。不代Leader关闭阶段、发布或开始S3。
