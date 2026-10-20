# V0.2/P1 Builder 实现报告001

2026-10-19；Hephaestus。初次实现已完成自测与交付，**等待Reviewer独立验收，P1累计返工0/2**。S3已关闭，不重开其2/2。没有提交/推送、产品优化或V0.3实现。

## 目标、权威与路线

依据[Approved设计](../../../leader/designs/V0.2/P1-design.md)、[审查计划](../../../reviewer/reviews/V0.2/P1-review.md)及[Leader001](../../../leader/reports/V0.2/P1-report-001.md)，实现独立性能基线工具、固定69cell+3控制及面向用户的结果文档。三份SHA分别为b65bf637c62463d5a7863c3e1fc988b9d27122e284c9d0cea4978e818fb45a2f、ab535bb2e4ee4aaf39675478ef507a38cdecb17a4a998d3f0a8a6d23d465d397、3938f140b1dedd9ec43346ffeaf594095864c32191d72db8d70c06998f55879f，最终复核保持。

读取既有S3最终独立接受及当前协议/进程工具、根文档，使用agent-execution-route与plan-project-docs Builder/拆解模板；没有项目专用Builder guide，披露全局回退。本轮没有C++修改或新增C++测试组件，不重复C++格式化、Debug/ASan或S3长期实验。

原生WSL，/bin/bash login=false，仓库/home/power/projects/AI-Inference-L7-Gateway，分支codex/v0.2-performance-baseline，HEAD555b65d66a52d95791dba5445178e57a69b81d2c。角色目录build-local/builder/v0.2-p1/{tmp,cache,evidence,release}；每次Python/构建显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。socket本机回环测试按已知边界精确窄升级，无新下载安装或全局设置。以下E指build-local/builder/v0.2-p1/evidence。

## 实现与边界

新增tests/performance六个Python文件及README；CMake仅追加PerformanceDetectors。逐文件责任、只读复用和固定资产来源见[来源说明](../../../references/V0.2-P1-changes.md)。src、旧S3工具/输入、第三方、Approved与历史报告未修改；Leader根文档变更保留。

独立模拟后端进程，正式成本使用Release正式程序，只有C资源诊断用既有RuntimeHost。有限线程屏障放行，A/B/R连续闭环、C四请求波次；没有S3退休快照补位。双发压控制为两个进程各八线程，共16。固定69cell与3控制提前落盘schedule，每cell预热与正式分别保存，热路径不逐请求写文件。

预序列化请求，CL/chunked HTTP终态与EOF分离，首wire/body/非空assistant内容事件分别取时。最后成功worker t_closed为批次终点；已完成HTTP但后续EOF/内容校验错误仍归失败。所有已开始attempt统一返回完整/partial结果，cell finally一次落盘；协同取消停止新attempt，收口已开始worker，双子进程在executor全部结束后一次交接结果。测试专用started_audit字段仅用于中断负控，正式cell不启用。

固定CPU资产/许可再次核验，实际启动9个依次运行的模型block；每block先预热两路径，按既定顺序完成D/P。模型单slot/cache与服务端日志保留，缺可靠usage时token/s为null。CPU四线程、ctx2048、parallel1、ngl0、固定alias，未添加stream_options或改变网关协议。

## 实际运行与失败保留

| 执行 | 实际结果 |
| --- | --- |
| 初次--check | import路径优先导致误载S3同名DetectorTests，exit2；E/detectors-001.log保留。修为追加只读复用路径后通过 |
| Release构建 | configure.log/build.log，成功；未修改产品 |
| 初次完整CTest | 15/15，26.02秒，release-ctest-001.log |
| 初次完整run-001 | 72/72，744.680秒，19,380含预热唯一样本，0失败，exit0 |
| 最终实际SIGTERM负控 | 单/双发压均started16=saved16、not_started112，标识集合一致；外层exit1，双子进程均exit0且reaped |
| 最终其他检测 | 3时钟控制、10失败attempt（含4晚到）、空成功分布、负控子进程exit1、缺资产参数exit2通过；detectors-final-001.log及目录保留原始结果 |
| 最终完整CTest | **15/15，26.65秒**，release-ctest-final.log及release-final-LastTest.log |
| 最终完整run-002 | **72/72，698.969秒，19,380含预热唯一样本，0失败，exit0** |
| 逐样本/统计审计 | 两个run分别计数/唯一性/时序/确定正文hash/资源排空通过；各1,216项独立汇总计算一致，独立Summarize CLI再生成结果也完全一致 |

初次正常矩阵完成后，静态自查发现外部中断时直接终止发压子进程可能丢未交接样本。协调者同意交付前自测修复，不计交付返工。先保存初始源码和完整run，再补协同取消/收集、实际SIGTERM负控，以及发送绝对期限、DONE后数据拒绝、批次终点精确化。之后只进行一次完整重跑；两次都报告，不因性能结果择优。初次与最终四个Python源变化、增加README进入清单；E/initial-source、diff-*.patch、两份manifest保存身份映射。没有把旧run当最终源码重跑证据。

每run矩阵正式A/B/C/R分别13,500/1,800/120/720，共16,140；控制1,500；预热1,740；合计19,380。固定cell数量与全部样本、失败/not_started分别核对，不以计数替代覆盖。两个正式run驱动时间合计1,443.649秒，均未触2400秒护栏。没有额外性能实验或容量搜索。

## 测量观察与局限

[用户结果报告](../../../performance/V0.2/P1-results.md)先给对照表与限制，[完整cell附表](../../../performance/V0.2/P1-cells.md)保留两次所有重复/控制。最终A并发1的E2E p50三cell中位：D0.734ms、PC1.359ms、PR43.908ms；PR实际复用预热池但当前后端条件下更慢，不能宣称复用收益。

最终真实流并发1：D/P的TTFT p50三cell中位14.559/15.634ms，E2E p50为362.725/364.851ms；并发2 TTFT约374.448/376.868ms，包含后端单slot等待。不是一一配对请求或单请求因果开销。真实非流、完成率、token来源及观察范围均见报告，不声称生产容量/GPU或优化收益。

C三个P cell实际pause/resume分别159/159、160/160、150/150（含预热），容量峰1MiB、预约峰64MiB，最终≤5秒自然排空FD/活动账本，停止回收另记。仅验证此固定慢读条件，不声称容量极限或严格公平。RSS/CPU/FD采样与内部预算分列，主线程context-switch和子进程最后有效CPU采样窗口边界明示。

初次控制触发前后median漂移>20%；最终双进程完成率相对单进程变化>15%，并发16部分cell客户端接近一核且完成率不稳定增长。保留为潜在发压/后端/机器限制，不精确归因GIL。闭环有coordinated omission，三重复不是置信区间；A探索性p99、B p50/p95、R p50/p90、C快慢median/max不混用。

## 命令与可复现证据

[工具README](../../../../tests/performance/README.md)列完整命令。实际使用：cmake --preset release -B build-local/builder/v0.2-p1/release；cmake --build同目录-j4；ctest --test-dir同目录 --output-on-failure；RunBaseline.py --check（最终另带--output E/detectors-final-001）；RunBaseline.py --gateway绝对Release程序 --host绝对IntegrationRuntimeHost --assets固定S3资产 --output E/run-001或run-002；Summarize.py --input E/run-002 --output E/summary-002。构建/负控/回归日志保留，py_compile与git diff --check通过。

关键证据：

- E/run-002/manifest.json：**54项测量源/只读复用文件与2个运行二进制**；SHA256 **2979fd7f039ba545b36679897db2138b80090cee3f71018801fa4420222a6db6**。
- E/release-binaries-sha256.json：**12项Release构建产物**（9可执行程序+3静态库），不是上项2个测量进程的计数；SHA256 **f712d8d26ae50daee7b02447a96965f2e7cb181ffe2e1d14257a08f69575abd1**。
- 初次E/run-001/manifest.json：53项（当时未加入README）；SHA256 **761d70bc199fe01150c4c3c4ef794b45822e981fcfb5521c6aa76faf589a10db**。
- E/run-002/{schedule.json,cells.json,summary.json,run-status.json}及每cell/{formal,warmup}/{attempts.jsonl,resources.jsonl,cell.json}；真实block模型日志/资产/CLI，C快照/drains，模拟backend-counts及预热快照。
- E/run-001-audit.json、run-002-audit.json、两份summary-audit.log、Audit.py/AuditSummary.py以及final-audit.json。

最终manifest逐项与当前文件匹配。Leader保护清单143项中142项原字节保持，唯一授权差异CMakeLists.txt为新增快速测试；三份P1权威SHA保持。每run102个服务进程的204条start/reaped事件配对，全部PID已不存在；最终双发压两个子进程均exit0、不存活。原始证据约66.4MB，保留首次失败/初始源码/两次完整数据。

## 交接

实现、自测、结果文档和保护审计均完成；没有未完成的Builder范围或需要擅自放宽的权威冲突。Reviewer重点独立核查HTTP终态/EOF与TTFT、双进程取消样本完整性、固定69+3顺序/连接差量、统计与工具限制，并按设计完整独立重跑。自测不是独立验收；等待Reviewer后由Leader/协调者收口及本地提交。
