# V0.2/S1 独立审查与验证计划

## 1. 权威与阶段

状态`Approved`；日期/批准日期2026-10-19；批准人Leader (Zeus)，按“已推送，开始v0.2/s1吧”及技术委托采纳，与[设计](../../../leader/designs/V0.2/S1-design.md)、[Leader001](../../../leader/reports/V0.2/S1-report-001.md)共同构成基线。阶段待实现，累计返工0/2。不得以审查方法改设计行为；当前无本阶段返工或预批准债项。

起点d653e9c400517783d5d33025a0b66a737c8256eb，分支codex/v0.2-s1-streaming，V0.1/S3 Reviewer002 PASS已闭环。读取实际Builder最新报告/变化记录和原V0.1权威。项目无专用Reviewer指南，回退全局模板；读取agent-execution-route、personal-cpp-standards完整相关规则和正反例。保持原历史报告和第三方字节。

## 2. 追溯矩阵

| RV | 要求 | 独立输入/方法与通过条件 |
| --- | --- | --- |
| RV-01 | AC01/设计§3 | JSON stream absent/false/true分别验证metadata、原始body；null/数字/字符串/重复字段拒绝。响应200 SSE与可选UTF-8参数进入流，非SSE 200/4xx/5xx/204/304走完整回退；重复Content-Type、非法SSE参数/charset、非200 SSE、101/HTTP版本/CL+TE/编码/非法Connection等在send前502。1xx后只一个最终头。默认nonstream拒SSE与原全部协议限制保持 |
| RV-02 | AC02/§4 | 单元枚举短样本全部单切分点、逐字节与固定seed多切分，跨header/chunk扩展/CRLF/UTF-8字节；下游解chunk后精确一致。真实后端头/未完成event且未完成HTTP chunk前缀发送后等客户端确认再发尾部，客户端必须提前收到；CL/chunked/EOF三模式，头独立先到。检查无整流body累积、无借用视图悬空/回调内删除/reentry；throw/bad_alloc安全、终态稳定、reset正确 |
| RV-03 | AC03/§5 | CL恰长/欠长、chunk正常零尾/缺零尾/错CRLF/非法trailer、EOF正常0与RST区分；[DONE]缺失/拆分/后续数据均不改变HTTP定界。混合nonstream→stream→nonstream真实后端accept/request计数验证stream一律关闭不归池，nonstream保持S3顺序复用。早期200SSE头时请求尚未发完：停止上传、继续收响应且不归池；下游SHUT_WR仍可完整接收；停止已有流有限排空 |
| RV-04 | AC04/§6 | FakeIO控制尚未发送（含已排队200头）错误仅一个502/504/500；仅部分状态行send后、整头后、压缩offset归零后错误仅截断，无第二状态行/零终止块/[DONE]。真实客户端先观察前缀再让后端坏帧/断连，确认chunked incomplete，不能用EOF当完成。短写/EAGAIN恢复精确字节，暂时pending空继续等流，不提前SHUT_WR |
| RV-05 | AC05/§7 | pending含封装的256KiB N−1/N/N+1、body8MiB/wire16MiB/chunks/headers边界与拒绝前置；接缝可缩小限额保证罕见分支但至少一次真实>4MiB正常流证明不受旧整流缓存约束。精确时钟检查response全程绝对/total、非空批次写期限不因部分进展刷新、排空重置批次、shutdown优先。真实慢客户端触发有限中断，混合正常请求可完成，session/reserved/pool/timer/FD终态回归；每回调操作公平及内存对象数有界 |
| RV-06 | AC06/§8 | 独立Debug/Release/ASan+UBSan完整CTest、Release主动失败、V0.1协议/池/Runtime/GatewayE2E/ReuseE2E保留、新增Streaming真实门控。S2原120/150ms关闭窗口20次及正常/错误握手保护不退化。clang-format18实际检查+人工相邻定义空行/成员分组/短lambda独立检查；来源变更单独登记，不改历史manifest |
| RV-07 | AC07/§8—9 | 核对实现/报告hash、原始命令exit与失败保留、README新流支持/硬限额/时间/no retry/不归池边界。无提前S2高低水位/完整动态预算、S3真后端、GPU或新性能承诺。接受后由Leader收口、协调者本地commit，禁止push；不让旧阶段发布限制覆盖新用户规则 |

内存安全、失控资源、串扰为Blocker；核心增量/定界/错误行为、关键验证缺失为Major；排版Minor须实际纠正或明确批准，不自行默认接受。若仅未接受Minor使模板结论枚举不明确，报告协调者裁定，保留真实严重度与历史结论。

## 3. 必需攻击性时序

1. 后端先发完整头再停，客户端已读头；接着发送单个大HTTP chunk的前缀 `data: hel`，不发送该chunk剩余，更无SSE空行。只有客户端经独立控制通道确认收到该前缀，才发尾文。门控超时失败，不允许测试通过“先发完再收”绕过。
2. 头验证失败与头/正文同read、正常头后本read坏帧：确认parse callback没有直接send，发前候选可撤回；已有历史输出不可撤回则准确中断。callback异常不跨C ABI，不destroy parser/session。
3. 压缩/消费输出后offset为0但responseStarted保持；此时timeout/容量失败不能产生第二头。合法完成只一个零chunk，done后再收到额外数据不再解析，不追加正文。
4. early SSE header与上游OUT同时到达，待发请求体必须停止，不能下轮继续发送或因清空buffer标写完；流结束关闭租约，后续正常请求重新获得容量。
5. downstream-write连续积压期间持续小量写成功仍不能刷新旧期限；队列排空→新片到达才开新批次，response/total始终约束。每个deadline先于事件推进时结果确定，不让热流饿死停止。
6. 下游FIN半关闭与RST分别验证；首次信号含idle/活动流/等待首片，第二信号及shutdown期限无假零chunk且全回收。正常stream完毕后closing继承1秒/total界限，旧下游事件不触及后续pool租约。
7. 资源快照与真实Socket/Python子进程端口清理一起验证；RSS仅采样观察，不当作16MiB逻辑额度证明。慢读被中断为S1设计行为，不把未实现pause/resume列为本阶段失败，也不声称S2已完成。

## 4. 可执行命令与证据

WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`。独立目录及环境：

```bash
mkdir -p build-local/reviewer/v0.2-s1/{tmp,cache,evidence}
export TMPDIR="$PWD/build-local/reviewer/v0.2-s1/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/reviewer/v0.2-s1/cache"
for mode in debug release asan; do
  cmake --preset "$mode" -B "build-local/reviewer/v0.2-s1/$mode"
  cmake --build "build-local/reviewer/v0.2-s1/$mode" -j 4
  ctest --test-dir "build-local/reviewer/v0.2-s1/$mode" --output-on-failure
done
ctest --test-dir build-local/reviewer/v0.2-s1/debug -N
build-local/reviewer/v0.2-s1/release/FoundationTests --intentional-failure
```

分别保存每条命令exit和日志，不能因循环尾成功覆盖中间失败。主动失败应exit1，其余exit0；新增CTest目标名由Builder报告列清且与ctest -N对照，必须包含真实流门控入口。格式检查对实际修改自有C++逐项运行clang-format-18 --dry-run --Werror，并检查Builder的实际-i记录；不修改第三方或以工具绿替代人工检查。报告须列具体文件而非“全部符合”。

独立关闭窗口探针沿V0.1保存的原脚本/hash/120ms后端+150ms额外写/20次；若历史本地脚本缺失则按原明确输入重建并披露，不跳过。控制时钟/IO只证明接缝状态，真实网络门控另证增量；不能用curl最后文本或日志时间猜首片到达。

所有测试合成loopback，无GPU、真实用户数据和外部服务。已知Socket/LSan边界精确窄升级，首次即正确路线；不能禁sanitizer/跳过关键项以通过。Reviewer自有构建/端口/进程，日志置evidence，失败与重试新命名，不用Builder可变二进制当独立结果。无需重新执行V0.1的18cell成本矩阵，当前不作流性能验收。

## 5. 接受和交接

新建 `docs/reviewer/reports/V0.2/S1-report-001.md`，之后同阶段递增；保留所有旧报告。逐项RV记录输入、期望/实际、命令exit、源码/二进制/权威hash、原始证据、发现严重度/AC与复现。PASS需所有AC独立满足且无未接受发现；契约内增量/生命周期/容量缺口不可默认债务化。环境阻止关键验证为BLOCKED，实现不满足为FAIL。PASS WITH DEBT必须先有明确批准及owner/退出条件，目前无预批准债项。

当前0/2，后续最多两轮纠正，第三轮开始前硬停。Reviewer不代Leader关闭阶段，不提交推送。V0.2/S1完成也不等于整个V0.2完成；后续S2/S3另行批准和验证。
