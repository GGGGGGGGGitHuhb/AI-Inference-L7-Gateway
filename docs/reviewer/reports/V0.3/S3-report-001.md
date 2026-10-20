# V0.3/S3 独立验收报告001

2026-10-20，Reviewer（Athena）。**FAIL；当前累计返工1/2，保持既有Leader权威纠正计数。新增F-001（Major）阻断接受。** 固定矩阵与三套回归实际通过，但运行中日志总量没有执行Approved的128MiB边界；本报告不接受该契约缺口为债。统一交Leader/协调者返工，不启动V0.4、不提交推送。

## 权威、范围与独立性

读取[Approved设计](../../../leader/designs/V0.3/S3-design.md)、[Approved审查计划](../../reviews/V0.3/S3-review.md)、[返工001](../../../leader/reworks/V0.3/S3-rework-001.md)、[Leader002](../../../leader/reports/V0.3/S3-report-002.md)、[Builder001](../../../builder/reports/V0.3/S3-report-001.md)、实现拆解/来源、tests/mvp全量源码/README、验收结果及根文档差异。M2字节超限按queue_bytes_exceeded，M4严格八条按返工补充；没有修改原Approved或历史报告以消除差异。

无项目专用Reviewer指南，使用plan-project-docs Reviewer模板回退。读取agent-execution-route，复用personal-cpp-standards完整规则及正反例并再次人工复核。执行路径为原生WSL，`/bin/bash login=false`，cwd=`/home/power/projects/AI-Inference-L7-Gateway`，分支`codex/v0.3-s3-mvp-acceptance`，HEAD=`d89de57eb6be0106bccd24432b2559d342ed8b79`。

独立目录`build-local/reviewer/v0.3-s3/{tmp,cache,evidence,debug,release,asan}`，构建/执行显式设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME及Python缓存。socket/LSan按既有边界首次精确提升权限，没有关闭检测器。只读复用固定模型资产，自建产物、自有端口/PID，不使用Builder进程、二进制或可变测试输出。没有改产品、测试工具、Builder材料、根状态文件或提交推送。以下E指该目录下`evidence`。

## 独立执行结果

三套均执行`cmake --preset MODE -B build-local/reviewer/v0.3-s3/MODE`、`cmake --build build-local/reviewer/v0.3-s3/MODE -j4`及`ctest --test-dir build-local/reviewer/v0.3-s3/MODE --output-on-failure`。

| 检查 | 实际结果 | 原始证据 |
| --- | --- | --- |
| Debug全CTest | 20/20，34.54s，退出0 | E/configure-debug.log、build-debug.log、ctest-debug.log、last-test-debug.log |
| Release全CTest | 20/20，31.50s，退出0 | 对应release四日志 |
| ASan+UBSan全CTest | 20/20，49.23s，退出0，无sanitizer错误 | 对应asan四日志 |
| 固定真实一次real-001 | 28条，26成功（含2预热）+2取消，25.671941s | E/real-001目录、real-001.log |
| 固定模拟一次simulated-001 | 29条，19成功/2取消/2后端失败/1队列超时/5拒绝 | E/simulated-001目录、simulated-001.log |
| 工具负控留档 | 11类各非零、拒绝原因与超时attempt保留，host启动/排空/停止成功 | E/detector-proof-001、对应.log |
| Reviewer额外三负控 | 3个子进程均退出7；部分200流后非法截断没有冒充成功、漏样本和末态queue_bytes=1均拒绝 | E/IndependentNegative.py、independent-negatives.json、reviewer-partial.json、negative-*.json |
| 独立样本/序列复算 | 分母、成功延迟、排队等待、峰值/排空、FIFO、M4冷却及Trial、取消和回收通过 | E/Audit.py、audit.json、SequenceAudit.py、sequence-audit.json |
| 格式与保护 | clang-format-18 dry-run通过；人工职责/回调/函数空行通过；102源、48独立产物、191既有文件身份核验 | E/format.log、identity.log及三清单 |

正式运行命令为`python3 tests/mvp/RunMvp.py --mode MODE --host build-local/reviewer/v0.3-s3/release/MvpRuntimeHost --gateway build-local/reviewer/v0.3-s3/release/ai-inference-gateway --output build-local/reviewer/v0.3-s3/evidence/MODE-001`；real额外指定`--assets build-local/integration/v0.2-s3`。正式真实/模拟各一次，没有择优重跑、补请求或改期限。短工具负控与三套回归不计入57条正式分母。

## AC01 / RV01：固定资产、正式入口与独立部署

实际real-001/ assets.json校验固定archive/server/model哈希、模型491400032bytes及归档内所有部署库/许可证逐字一致。llama.cpp版本7481(cc0a04343)，ldd无缺库（E/asset-runtime-check.log）。Qwen LICENSE SHA=`832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e`，Apache2.0；二进制归档内许可证已校验。无下载或写模型资产。

两自有CPU后端以alias gateway-qwen、ctx2048、parallel1、threads2、threads-batch2、GPU0运行。R0完成两个后端各非流/流直连、host两条预热以及真正ai-inference-gateway非流/流冒烟；后者有独立config、日志及PID，未用host代替正式程序。运行没有Server/L4LB服务依赖；两个进程共享宿主CPU，不表示双GPU独立算力。

## AC02 / RV02：真实R0–R3

R1八条目标实例序列实际为0,1,0,1,0,1,0,1；非流/流交替均合法完成。R2两条长流先通过首非空content和request_active事件门槛，再提交四短流；四条实际入队并派发，等待分别9.747024、9.746881、10.364835、10.361339秒（按ID顺序，不冒充FIFO时间排序）。排队等待由host enqueued/dispatched差求值；六条均成功，global峰2/per-backend峰1，queue峰4/5312bytes。慢读实际首content后暂停1.000102秒并执行后续限速读取。

R3两条长流在首content且活跃后RST；L1全账排空分别0.122345/0.105792秒，小于5秒。L2记录取消前upstream FD及socket inode、取消后确认该inode释放；随后两个恢复请求成功。另两条完整请求SHUT_WR均成功，不误判取消。L3本次两个CPU slot均观察idle，仅为后端现象，不宣称计算/GPU取消保证。

## AC03 / RV03：门闩M1–M5

按原始attempt、client-port关联host记录和后端request日志独立复核，而非仅采信summary：

- M1两活动、a两等待，下一a准确queue_full，b仍可等待；释放后五条成功。按各模型真实enqueued/dispatched检查FIFO，跨模型队列没有混为一个全局FIFO保证。
- M2单项逻辑charge超过4096返回503/queue_bytes_exceeded，小等待504/queue_timeout；上游日志精确仅M2-01/02/05，拒绝/超时没有隐式上游尝试。
- M3等待队首RST确实入队且未派发便取消；其后等待SHUT_WR记录downstream_eof且最终成功。活动RST释放后进展、两恢复成功。
- M4恰八条：01已提交内容后坏chunk截断，仍200且未HTTP完成/无DONE；03先等待，后实际派发a2。04关闭a2后502；05前两个实例均Ejected且未到冷却deadline，只一个503/no_available_backend。06在a1冷却后实际a1 Trial、inflight1，完整HTTP成功才恢复；07在06完成后启动，08模型b成功。没有追加HTTP状态探针；后端日志无重复ID或重试。
- M5两活动和两等待后SIGTERM，等待者精确gateway_stopping，活动完成；最终停止快照账本全零，进程正常回收。退出后未伪造live FD数据。

## AC04 / RV04：统计、资源及错误探测

E/Audit.py直接读取每条attempt文件，独立核对唯一ID和准确分母，从成功样本重新计算min/median/max；没有导入Builder summary或其重算脚本。TTFT直接由首content_times减sent复核；E2E以原始attempt的合法HTTP终态耗时统计，并检查其位于sent至ended之间；源码确认该耗时仅在HTTP合法终态赋值。非流不计TTFT，失败/取消不混入成功延迟，R0/direct、warmup、official独列。精确逐组样本数与延迟全见audit.json，不宣称p99或吞吐。

真实四条与模拟五条成功派发队列等待独立从时间戳复算；取消/超时不混入该分母。按所有host历史快照复核global/per-backend、队列、预约及stream额度；峰值仍是观察到的峰，100ms账本/1s RSS采样不等于瞬时全覆盖。

真实预热排空基线B=4378624bytes，后续排空最高4706304bytes，低于B+32MiB；各排空FD=7与基线一致。模拟各组B=4096000bytes，排空最高4521984bytes，FD=7。所有排空/最终快照的sessions/reserved/capacity/pending/paused/timers/upstreams/leased/idle/pool_total/retired/inflight/queue_count/queue_bytes均零。真实采样gateway峰RSS4706304bytes/FD15；两个后端RSS621289472/621408256bytes，均低于2GiB。

额外IndependentNegative.py自建socket服务发送200和有效首content后不完整chunk并关闭，真实Attempt保留正文和异常并以failure退出；两个独立构造分别漏一个计划样本、末态queue_bytes=1，均非零拒绝。负控不是只检查预置通过文本。11类工具自身负控另独立留档，完整回归也执行。

## AC05 / RV05：工具实现、保护及规范

检查Attempt线程异常进入finally唯一`open('x')`落盘，join传递持久化/验证错误；增量SSE/HTTP合法终态、单调时钟、超时和部分正文保持。RunMvp独占新目录、固定计划和源/产物manifest、整体alarm及非零失败记录；cleanup_all逐资源执行，即使一项失败仍继续其余清理并传递异常。已有OwnedProcess正常TERM、必要时KILL并wait，自有日志边界及host历史上限可追溯。

RuntimeHost只读借用现有friend身份采样，cleanup先收集再执行原onCleanup，未改变产品调度/健康判断；registerCleanupCallback短lambda转发具名方法，observer/runtime在轮询回调期间均存活。构建不新增下载。新增唯一C++文件`tests/mvp/RuntimeHost.cpp`实际执行`clang-format-18 --dry-run --Werror`（18.1.3）；人工核查.cpp相邻函数/类内定义空行、接口/成员分组和回调捕获。没有用格式工具代替语义审查。

102项源清单逐项与Builder最终源身份一致；独立48产物为每预设13可执行+3静态库。191个HEAD既有文件（排除当前允许更新的CMake与三根文档）逐字比对不变，包含原产品、旧测试/断言、工具、配置、第三方及历史文档。根文档当前仍描述待实现属于Leader待同步状态，本报告不自行改其权威状态。新results正确标Builder自测/Reviewer未验收快照；收口可追加独立结果。

身份锚点如下，完整权威与哈希原文见E/identity.log：

- Approved设计SHA：b0d9fd9a518436631ecfd189d3bb50488b4edb3c7d6fb7cde24c81520901e49d。
- Approved审查SHA：2b3e3ce3d1a030c25b1b08800a942d41107ee0ebf04173b4f3d281ac30ae62f4。
- rework001 SHA：993c9ae4ea64991803a9fbe49a1bf353c3d04f6df2a4854c131c161852dc99de。
- Leader002 SHA：545dde7eeb641cb749b4be742da8d295ac6d72adef5bf20a409ff6fd8ad32e4a。
- Builder001 SHA：f291b821785ade44f698d5704337da017bf0bbedd819de864e0c3efcac64fd4e。
- E/source-sha256.json（102项）SHA：5612c4e5d8ad7d9da2fc6b8f1b5f70948662a337d62d08a7b5d80ce062da6f52。
- E/binaries-sha256.json（48项）SHA：3012f101380232e74b3adee79a80f2e1e97b39309fa0df1f5931b0d37f2612c6。
- E/protected-sha256.json（191项）SHA：0080e3ee55826e6c7f3a85b9ee5df7c94c75129dd30c78130429bf9129927866。

## F-001：完整run的128MiB日志预算仅事后检查（Major，未关闭）

Approved设计第1节明确“观察状态须有界（本矩阵请求数、128MiB日志）”。`tests/mvp/RunMvp.py:41–44`先完整执行matrix.run与join_observations，再遍历输出目录并检查128MiB。直到这时，运行期间无任何完整run总量预算检查或写入限制。

`tests/mvp/RuntimeHost.cpp:171–172`只在追加后检查单个host历史文件96MiB；既有Support.append只检查单文件64MiB；OwnedProcess将子进程stdout/stderr直接定向普通文件。真实两个backend、host、official及attempt/资源/event输出，模拟五组各自host历史均共享一个run目录；每文件分别未触限仍可合计超过128MiB。进程日志没有该总量检查，不能由其他文件的限额推导出完整run上限。以上源路径可直接复核，无需制造数百MiB垃圾才能证明控制流缺口。

影响：在超时/高频日志/大量状态变化路径，驱动可以先越过Approved存储预算，继续运行直到矩阵完成或更晚才返回FAIL。当前成功run仅2700415/448709bytes不是运行中预算执行证据。把总量检查解释成“仅成功结果大小验收”会放宽原有明确有界要求，Reviewer不自行作此改写。

修复要求：在新S3工具范围内给完整run所有日志/快照/attempt/子进程输出建立真实的运行期总量边界；达到边界即失败并有限清理自有进程，同时保留已发生attempt与错误证据。不能只增加最后一次合计、各文件独立限额、截断后伪成功或修改Approved大小来关闭。允许设计有界的错误记录保留预算；实现方式由Builder提出，不能改旧工具行为或扩大产品。

最小复验：保留当前真实28/模拟29、三套20/20为修复前证据；提供小预算/可控写入的专用负控，验证多个各自未超限的输出累计触限、运行及时失败/进程回收、已有attempt和错误保留且无成功结果。Reviewer独立检查修复路径及测试，不必为了存储护栏重复模型负载。若只改新工具预算/说明且产品、host/CMake、三套产物、固定矩阵/协议校验/时序不变，可按精确源差异和产物SHA复用既有功能实跑，仅执行相关短检测器及独立追加负控；若改动波及上述行为，则根据实际diff补相应回归，不能预先承诺全部复用。返工计数由协调者统一推进，本报告记录交接时1/2。

其他边界复核：未开始的计划ID仅存在plan.json，不伪造已执行attempt；已构造Attempt的run在finally落盘，提前失败使整个run失败，完整成功必须通过精确ID/数量检查。零额度来自实际快照，缺失样本/缺键会失败，不用默认0掩盖缺失。采样100ms/1s是调度目标；独立实测账本最大间隔真实0.120105s/模拟0.101598s，资源最大间隔1.000976s/1.000390s（E/sampling-audit.json），含轮询/调度开销，不能宣称严格硬实时“至少每100ms”。这符合设计要求保留实际采样间隔与不作瞬时上界推断的边界；收口说明应使用目标周期措辞。

## 结论与交接边界

AC01–AC03通过；AC04/AC05的运行中日志边界未满足，F-001未关闭，因此整体FAIL，无自行接受的债。真实4个与模拟5个自有进程start/reaped一一对应，退出0且/proc均不存在；短检测器所属进程亦回收。构建和负载已结束，保留原始证据，无后台模型服务遗留。

真实慢读pauses=0，不能声称真实高水背压已触发；现有确定性背压全回归通过。小样本、共享CPU、host写盘观察开销、采样周期及协议级健康限制保留，不据此宣布容量、SLO、长期公平或性能优化，也未重跑P1/旧长soak。交Leader形成统一返工；F-001关闭后才可重新裁决阶段与版本收口，协调者按用户授权完成后本地提交、不推送。
