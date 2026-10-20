# V0.2/P1：独立性能基线专项

## 1. 批准、生命周期与边界

2026-10-19；`Approved`，专项待实现，Ready for Builder，累计返工0/2。Leader (Zeus)依据用户同意“V0.2完成后先测性能基线，再开发V0.3”并明确“可以，别忘了文档，做吧”，结合既有技术决策委托批准。批准包：[本设计](P1-design.md)、[审查计划](../../../reviewer/reviews/V0.2/P1-review.md)、[Leader001](../../reports/V0.2/P1-report-001.md)。无例行PM待批准项。

本专项为P1，不重开已完成S3。V0.2开发验收保持完成，S3历史2/2不变；P1有独立0/2至多两轮纠正。起点 `555b65d66a52d95791dba5445178e57a69b81d2c`（S3本地提交），分支 `codex/v0.2-performance-baseline`，初始干净，远端未核验。完成后协调者本地提交、不推送；不启动V0.3/V0.4、不优化产品、不改协议/调度/依赖、不把测量工作包装成发布。

目标是回答固定环境下：模拟直连/代理的端到端分布与连接成本如何；并发和受控慢读时资源如何变化；固定真实CPU模型的TTFT、E2E和闭环完成率如何。没有预设“代理必须更快/低于某数值”的性能门槛。预定义正确性、计量、完整记录和可解释性门槛，负面/异常/失败同样是结果。

## 2. 复用审计与实现责任（REQ-01）

已有tests/ProxyBaseline.py用于V0.1固定1KiB/并发1和4/200样本18cell，含连接计数/轮换/资源思路，可参考但**不直接将其结果称为P1**：其延迟到receive结束、失败与成功混入分位数；200样本P99尾部稀少；线程发压、后端逐请求同步日志和累计线程列表可能成为限制。保持旧工具及旧结果原字节，新工具放tests/performance/。

S3 Support.exchange的start包含序列化，end还含EOF等待及最终整理；WireResponse.finish在CL/chunked HTTP终态之后等待EOF。S3 SyntheticRun使用100ms Runtime快照退休门补位，适合资源正确性而非成本发压。P1不使用该门控制正式成本批次，不从旧soak计数/时长倒推新吞吐。可只读复用固定资产验证、专属PID清理、请求fixture和原始HTTP严格校验思路；不能改变S3工具来满足P1。

新增有限用途标准库Python客户端/独立进程模拟后端/结果汇总与快速负控。客户端I/O并发可用有限线程或selectors，由Builder按现有工具可维护性决定，但必须执行§7同环境负载工具控制；不构建通用压测框架、不安装压测库。后端与客户端至少分进程，正式计时热路径不逐请求同步写文件；本cell有限样本在内存有界保存、cell结束落盘，异常/中断finally也保存所有已开始attempt。线程/连接对象及时回收，不能跨cell无限积累。

正式成本测量必须使用Release正式ai-inference-gateway进程；测试host只用于单列慢读资源实验，输出的数字明确标记test host，不和正式产品延迟合并。可只读复用现有IntegrationRuntimeHost，其100ms快照不用于任何发压补位门；不新增产品管理接口。禁止改src或旧Approved/历史报告/input。新C++如确有必要只限测试设施并遵循personal-cpp-standards；本方案不要求新增C++。

## 3. 固定环境、配置与连接模式（REQ-02）

原生WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`；各角色build-local/<role>/v0.2-p1/{tmp,cache,evidence,release}，脚本前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。现有CMake/Ninja/Python标准库，无新下载。模型资产只读复用build-local/integration/v0.2-s3：llama b7481/cc0a04343，GGUF Qwen2.5-0.5B-Instruct Q4_K_M固定revision2ed9be962c95f7625f4963ff51ed472e4538187a；SHA、许可沿S3再次核验。4线程/threads-batch4、ctx2048、parallel1、ngl0、alias gateway-qwen，CPU执行；不使用GPU。

每角色独立PID/process group/端口/日志，同一时刻只运行一个测量cell，真实模型只有一个。Builder和Reviewer顺序运行、不能并行争抢机器；不杀用户服务、不改变系统频率/全局内核参数、不要求管理员清空缓存。各cell前静置2秒并记录/proc/loadavg、CPU/内存、相关进程CPU/RSS/FD、系统可用内存/CPU计数、时钟分辨率、编译器/内核/标准库/CPU型号。开始/结束及每秒记录loadavg、系统CPU差量、相关进程CPU/RSS/FD；机器其他负载只报告，不读取无关进程命令行/个人数据。

固定实验Gateway配置：max_connections64、max_reserved_bytes1073741824（64×16MiB预约），pool max_connections64/max_idle按模式0或64/idle_timeout_ms300000；stream高/低192/64KiB、max_total_bytes16777216。timeouts_ms request10000/connect3000/upstream_write5000/response120000/downstream_write10000/total150000/shutdown3000/stream_idle30000。这是实验配置，不修改产品默认；较高会话额度给已HTTP完成但尚closing的会话留余量，不把它称容量测试。不得根据失败事后调高。

所有客户端每请求新建TCP、HTTP/1.1、Connection: close，固定CL JSON请求，完成后关闭；直连同样新连接。模拟backend尊重Connection: close，允许其他请求持久连接：

- D：direct-close，绕过Gateway。
- PC：proxy-close，max_idle=0，非流式每请求新上游。
- PR：proxy-reuse，max_idle=64，非流式可复用预热池。
- 流式只比D与P；P取PR配置，但stream=true上游必关，不能称流式池复用。

每个cell新启自己的模拟backend/Gateway，预热后不清空池；只对非流式PR要求有实际复用并记录accept/request差量。真实每个“重复×并发×响应模式”配对block新启固定模型，预热两路径后连续完成交错的D/P cell；prompt缓存不可强行视为相同，记录服务cache/token信息和实际顺序。模型slot内部等待属于后端，不能把真实并发2的队列时间全归因网关。

## 4. 固定有限矩阵（REQ-03）

所有模式每个组合3次完整重复，重复编号0/1/2；同一repeat内并发顺序轮换1→4→16、4→16→1、16→1→4；非流路径顺序D/PC/PR循环移位。双路径顺序按repeat和场景编号奇偶交替，完整预先生成schedule.json，不看测量结果选顺序。预热不计正式分母但全部记录并须正确。

| 组 | 负载/模式 | 每cell预热/正式 | cell数 |
| --- | --- | --- | --- |
| A 模拟非流成本 | 固定合法请求content256个ASCII；固定JSON响应1024字节，无人工延迟；D/PC/PR × C=1,4,16 × 3重复 | 50 / 500 | 27 |
| B 模拟流成本 | 固定64个1024字节有效SSE data记录，总解码65536字节；首片立即，后续发送间隔目标1ms，chunked；D/P × C=1,4,16 × 3 | 10 / 100 | 18 |
| C 混合慢读资源 | 4MiB确定SSE正文，分16KiB发送，无人工后端间隔；4并发，每4请求中1慢3快；D/P(test host) × 3 | 4 / 20 | 6 |
| R1 真实常规 | S3固定短prompt、temperature0、max_tokens32；stream=false/true × D/P × C=1 × 3 | 每路径2 / 40 | 12 |
| R2 真实并发观察 | 同一短prompt、stream=true，D/P × C=2 × 3，后端仍单slot | 每路径2 / 40 | 6 |

共69cell；正式A13500、B1800、C120、R720尝试。数量不是完成保证：失败仍在固定attempt分母。A/B常规闭环worker每次完成请求及本地校验/关闭后再发下一条，无think time/快照门；启动顺序统一屏障，数量按worker分配，不把线程创建时间混入批次。C客户端首读前暂停0.5s，之后每次读取最多16384字节并sleep5ms，SO_RCVBUF设65536并记录内核实际值；快客户端不停顿。C每4条作为一波全部结束才发下一波，明确这是波次闭环诊断，不是饱和吞吐实验。

B的1ms是目标用户态sleep，不保证真实间隔；记录后端首/末发送与间隔分布，不能把调度抖动称网关抖动。C不强制声称触发高水；必须报告pause/resume和pending峰实际是否发生，未发生则本cell只能说明该慢读条件资源，原S2/S3高水正确性证据仍独立存在。不得临时改Socket参数或正文直到看到期望结果再隐去之前run。

每cell护栏A60s、B90s、C120s、R180s；单请求socket超时A/B5s、C10s、R150s（并用单调绝对客户端总期限避免每次recv重置造成无限等待）。真实启动每block120s。每角色完整正式矩阵总护栏2400s，不含构建；通常目标10–20分钟但不保证。超时停止新attempt，已开始的尽力收口并保存，尚未开始明确not_started，不伪造零延迟样本；报告PARTIAL/不完整，不能降低样本量补写PASS。固定矩阵之外仅§7有上限的校准，不扩成容量搜索。

## 5. 计时、正确性与原始样本（REQ-04）

预序列化固定请求；所有时刻取客户端同一monotonic_ns。每attempt记录独立ID、cell/repeat/worker/sequence、开始/终止状态、请求hash、响应状态/头/定界、decode字节/hash、错误/partial及以下时间：

- t0：开始connect前；t_connect：连接建立；t_send：完整请求send返回；t_head：完整最终头可用。
- t_first_wire：第一次recv返回任何响应字节；t_body：第一段解码body可用。
- t_content：流式客户端解析到首个非空assistant delta.content，使用包含该事件末尾的recv时刻；role-only/usage/[DONE]/空content不算。该定义是首个可识别内容事件，不声称单个模型token；非流不输出TTFT。
- t_http：CL最后字节或chunked零块/空trailer完整的时刻；EOF定界则真实EOF。另存t_eof、t_validated、t_closed。

主E2E=t_http−t0，connect=t_connect−t0，post_send=t_http−t_send；流TTFT=t_content−t0，TTFB=t_first_wire−t0、首解码body=t_body−t0另列，不能用头到达代替TTFT。t_http必须在等待EOF/最终JSON整理之前记录，基于解析器可判定的字节到达；同一recv多事件只能得到同一时刻，不伪造纳秒级token间隔。客户端解析/调度仍在可观察路径中，声明测量分辨率不等于精度。

严格校验完整HTTP/无额外响应或尾块、1024/65536/4MiB确定模拟解码正文逐字节hash匹配；真实需200、合法非空assistant文本，流终态finish_reason/[DONE]正确。真实不同次推理的ID/created/timing/文字不强求相同。可继续复用S3 WireResponse验证逻辑，但P1新增计时适配须在HTTP终态处独立取时；原文件不改。后续EOF/正文校验失败时即使已有t_http也算失败，不纳入成功分位数，保留partial时间。

每个已开始attempt无论连接/解析/回调/校验/超时/中断/晚到worker异常都恰好记录一次，失败退出不吞错误。记录错误类型及阶段；计划中但未启动另记not_started，不进入完成耗时分布。批次总时长从屏障放行到最后worker关闭/校验完成，故完成率包含客户端处理和关闭成本，与单请求HTTP E2E口径不同；预热/进程启动/结束采样落盘不混入批次。失败不能从吞吐分母时间删去。

## 6. 汇总口径与可信边界（REQ-05）

每cell分别输出attempted、valid_success、HTTP拒绝、连接/超时/协议/校验/中断失败、not_started及有效字节；success completion/s=成功数/实际批次墙钟，attempt/s及失败率并列。不称最大QPS、开放到达率容量或生产服务能力；闭环响应变慢会自动降低到达率，存在coordinated omission，P1不尝试修正成开放负载分布。

成功样本E2E、TTFB、流TTFT分别nearest-rank；A的n=500报告p50/p95/p99且p99仅约5个尾部样本、标探索性；B n=100仅p50/p95，p99不出正式结论；R n=40仅p50与p90，p95可在原始附表标低置信、p99不报告；C每角色仅20混合样本按快/慢拆分报median/max与资源，不假装稳定尾分位。失败耗时单独分布，零成功输出null不是0。

每个重复单列分布和数量，再给3次cell统计的median和min–max；不把不同cell混池后得到“更稳定P99”，不丢异常重复/不选最佳。3重复仅描述运行间散布，不能声称95%CI、统计显著或总体尾延迟保证；请求相关性和同机干扰阻止把每个请求当独立重复。直接/代理cell差值或比值仅“分布统计差/比值”，两组P99相减绝不是单请求额外延迟P99，也不将不同随机推理请求做伪一一配对。

真实报告响应完成/s和解码正文有效MiB/s；token吞吐仅当同一固定后端每请求usage.completion_tokens或可靠终态计数可核对时输出总tokens/同一批次墙钟，注明来源/分母及是否含后端单slot等待。SSE event数量/content字符/字节不能代替token数；缺计数则token/s=null并解释，TTFT仍可按内容事件测。不得为获取usage额外添加网关拒绝的stream_options。

资源：相关gateway/backend/client分别每秒CPU、RSS、FD、context-switch计数，A/B短cell至少开始/结束并尽可能50ms采样；CPU seconds差量/墙钟给“核数等价”，100%代表一个逻辑核，不混作整机100%。采样负担单列，采样峰不等于真峰。C的host additionally给预约/容量/pending/paused/pause-resume/lease峰和排空基线，硬容量不得越界，结束≤5s回到启动基线（关闭idle或等适当期限，不等300秒才cleanup；测试收尾可主动停自己的host，需区分自然排空与停止回收）。正式PR保留idle，结束前记录其占用，关闭过程另列，不能误认idle FD是泄漏。

## 7. 工具瓶颈控制与失败处理（REQ-06）

正式前快速correctness负控验证时刻顺序、已HTTP终态但延后EOF（主E2E不含延迟）、role-only先到而content后到、坏正文/缺尾块/重复尾块、连接拒绝/读取超时/校验异常、并发晚到失败、空成功分布。原S3异常attempt完整性不能倒退。离线自测无模型依赖，显式模型测量不会加入默认CTest。

工具控制固定3个附加A场景C=16、D直连，正式前与后：前两次各500请求，分别单发压进程和2发压进程×8并发（总16）同时作用于同一单后端进程；末尾单进程再500。后端/客户端都独立进程、同步屏障，数据与正式矩阵格式一致。这里只诊断Python/GIL/调度/漂移，不用最优控制替换主结果。测量客户端无同步每请求磁盘日志，记录自身CPU和实际并发/worker周转间隙（t0下一条−t_closed上一条）。

若双进程相对单进程完成率改变>15%，或CPU持续接近一核且增长并发无明显完成率增长，或前后控制median/QPS变化>20%，标记潜在发压/后台瓶颈或机器漂移并保留所有结果。仅有这些阈值不能精确归因；不据平台化曲线宣布网关饱和。只做一次有明确原因的全组重跑，原run保留，且必须报告两次而非选优；不自行换负载框架/调系统/无限扩大控制。工具受限并不强制优化，只收窄结论为“当前工具+后端+网关链路观察”。若连正确性/时间/样本完整都不可证明则BLOCKED/FAIL，不能以局限声明豁免。

正常正式样本任意失败不隐藏：保留cell失败率与延迟，先区分模型/机器/负载工具/产品问题。性能低或出现准入拒绝本身不是预设门槛失败；若根因是明确产品契约bug或检测器错误，交协调者按阶段治理，不擅自产品优化。P1可在结果不理想时完成，只要固定矩阵、错误取证、正确性分类和限制全部可审计；不能将确实错误正文标成功或把不完整矩阵称完成。

## 8. 交付、命令与接受（AC）

建议可复现入口固定为tests/performance/RunBaseline.py、Summarize.py及README；Builder可内部拆文件，但下列CLI须实现，离线`--check`验证资产缺失/参数/负控且不触发完整矩阵。schema含manifest、schedule、attempts.jsonl、resources.jsonl、cells.json、summary.json，记录源/二进制/fixture/资产SHA、平台、参数、实际开始结束、退出码和进程回收；任一失败也保存run-status。输出目录必须新建，禁止覆盖。

```bash
mkdir -p build-local/builder/v0.2-p1/{tmp,cache,evidence}
export TMPDIR="$PWD/build-local/builder/v0.2-p1/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.2-p1/cache"
cmake --preset release -B build-local/builder/v0.2-p1/release
cmake --build build-local/builder/v0.2-p1/release -j4
python3 tests/performance/RunBaseline.py --check
python3 tests/performance/RunBaseline.py --gateway "$PWD/build-local/builder/v0.2-p1/release/ai-inference-gateway" --host "$PWD/build-local/builder/v0.2-p1/release/IntegrationRuntimeHost" --assets "$PWD/build-local/integration/v0.2-s3" --output build-local/builder/v0.2-p1/evidence/run-001
python3 tests/performance/Summarize.py --input build-local/builder/v0.2-p1/evidence/run-001 --output build-local/builder/v0.2-p1/evidence/summary-001
```

Reviewer用自己的路径完整重跑同矩阵与控制，不能只重算Builder数据冒充独立测量；实测差异不要求一致，报告环境/顺序差异与波动。预算每角色正式矩阵≤2400s，执行期间驱动持续进展输出；命令可异步轮询，代理每分钟沟通。

| AC | 必须接受的结果 | 审查 |
| --- | --- | --- |
| AC01 | 产品/旧工具不变，固定资产/CLI/版本/输入/配置/调度清单可复现，进程独立并清理 | RV01 |
| AC02 | 69cell与3控制完整，预热/正式/失败/not_started严格分离，连接模式与真实CPU工作负载真实执行 | RV02 |
| AC03 | 七类时间口径及HTTP终态/EOF/TTFT负控正确，正文/终态校验与每attempt取证完备 | RV03 |
| AC04 | 分位数/重复/失败率/吞吐/token来源及资源独立复算一致，无伪开销P99/容量/显著性结论 | RV04 |
| AC05 | 工具瓶颈/负载/波动控制记录，限制/负面结果保留，独立Reviewer同矩阵和必要回归通过 | RV05 |
| AC06 | docs/performance/V0.2/P1-results.md面向用户结果报告与角色报告齐备，包含场景表/结果/局限/下一步，根状态一致且历史保护 | RV06 |

结果报告先回答“观察到什么/当前不能判断什么/对V0.3开发有何参考”，再附完整表和原始证据链接；最多两张有单位/样本量/模式/重复说明的静态图可选，优先清晰表格，不能造样例结果。没有产品修改时Release完整CTest加新测量负控足够，旧Debug/ASan与长期测试仅准确引用不冒充重跑；如新增C++测试host则新代码三预设验证，不需要重跑S3长期矩阵。
