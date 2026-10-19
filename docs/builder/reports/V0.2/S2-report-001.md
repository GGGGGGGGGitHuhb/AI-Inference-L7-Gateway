# V0.2/S2 Builder 初次实现报告001

2026-10-19；Builder Hephaestus；初次实现，累计返工**0/2**。实现及Builder自测完成，等待Reviewer独立验证；没有宣告阶段接受，没有提交、推送或启动S3。

## 权威、范围与路线

依据Approved [S2-design](../../../leader/designs/V0.2/S2-design.md)、[S2-review](../../../reviewer/reviews/V0.2/S2-review.md)及Leader001，完整读取根状态、S1最终接受/返工报告和当前实现。设计SHA `5dfc90adad8f0b9802a946b713434540a1954c69b3a2344a161f025b60e9bef6`，审查SHA `af34802f758c1598b0fa89008b8ea5d694f055f65c8b354c65f52897aa93b201`；最终核验保持不变。

使用agent-execution-route、personal-cpp-standards完整规则及正反例、plan-project-docs；项目无专用Builder指南，回退全局Builder与stage-design模板，已告知协调者。原生WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`；分支`codex/v0.2-s2-backpressure`、HEAD `2f7cf831a302fc87717afcae510e777187c7d0ef`。Builder独立`build-local/builder/v0.2-s2/{tmp,cache,evidence,debug,release,asan}`，所有脚本/构建前显式TMPDIR/TMP/TEMP到tmp、XDG_CACHE_HOME到cache。已知Socket/LSan边界首次精确窄升级；无联网、安装、派生代理或兄弟仓库修改。

证据根以下简写E=`build-local/builder/v0.2-s2/evidence`。旧阶段证据/Approved/历史manifest保持；Leader的ARCHITECTURE/ROADMAP修改保留，README只同步本阶段实际初版支持。变更文件逐项起点/当前hash见[变化记录](../../../references/V0.2-S2-changes.md)。

## 实现决策与所有权

新增gateway内部BufferBudget/CapacityLease：单Worker Runtime拥有唯一账本；move-only凭证构造前计费，析构/显式release幂等退还。原max_connections与16MiB/session总预约仍有效，新增固定256KiB/活StreamOutput数组的子预算；两者不是可相加的可用容量。Runtime在make_unique<ProxySession>前获取预约，构造/发布失败由局部凭证/对象回滚；session中的预约成员声明最先、其他成员销毁后才析构释放，Runtime预算成员寿命长于sessions，Runtime析构先清空所有会话。

streamCapacity凭证先于数组取得，make_unique数组失败由事件包装捕获、prepareError回滚。releaseStream先销毁数组再退凭证；pending空/暂停/HTTP完成未排空都不退容量。finish立即清流存储、暂停计数、租约、注册和timer，总预约仍等对象cleanup删除后释放。多次finish/timer/resume不重复统计。容量不足首字节未发送时503 buffer_capacity，无队列或淘汰；非SSE回退不占数组子预算。

RuntimeSnapshot保留旧字段并增加BudgetSnapshot：reserved/peakReserved、streamCapacity/peakStreamCapacity、pending/peakPending、paused、pauses/resumes、rejected及固定枚举终结原因数组。总预约和容量由凭证唯一维护，pending变更在append/consume/release时同步维护，paused按独立状态转换维护。累计计数饱和；没有保存正文/无界历史或外部管理API。

ConnectionLease新增suspendEvents，仅经过id/generation验证后Channel::removeChannel（DEL/旧token失效）；恢复setInterest重新注册新token，保留同一租约，不归池、不递归read。ProxySession每recv处理后达到high即停，每次正数send后到low才恢复；每方向原64KiB/64次事件限额保留。暂停不读上游，FIN/RST延后观察，由response/total/write持续兜底。

SSE新增stream_idle，只由实际body刷新；pause先查旧期限再保存剩余，resume检查有效期限后恢复原剩余，不充满。SSE downstream_write仅实际send>0刷新；EINTR/EAGAIN不刷新，pending空撤除，下一episode重新开始。所有相关recv/send/parse返回后先查仍有效旧期限，正send先记responseStarted以免跨期限后错误生成第二头，再进行旧期限检查；原response/total绝对计时和S1完成边界修复保持。同刻分类沿total、write、response、idle。非流式/回退的旧写/关闭行为保持。

## AC/RV对应实际证据

| AC/RV | 结果与输入/断言 |
| --- | --- |
| 01 配置/预算 | Runtime::testStreamBudgetAndConfig验证默认可省略、新高低/总额/idle边界，类型/未知/重复/溢出/low≥high拒绝；旧配置测试完整保留。StreamOutput分配bad_alloc后500且子预算/pending为0、预约仍16MiB直到对象删除；恢复注册token耗尽失败清理；Runtime原构造/接入/预约额度与析构回归通过 |
| 02 真实背压 | 新Backpressure CTest，真实CL/chunked/EOF各至少2次高水暂停、DEL token=0、8次poll观察read调用/字节不增、客户端放行到低水恢复新token；最终解chunk正文262153字节精确相同且恰好一个零块，无等待完整event。原StreamingE2E完整头/不完整event+chunk前缀双门控与>4MiB正文仍通过 |
| 03 暂停事件 | EOF模式在第一次暂停时后端已排完整余量并SHUT_WR，暂停不recv，恢复后完整尾部/正常EOF成功；三定界分别暂停时真实RST，恢复后中断无零块。手动派发旧IN/HUP/ERR token在暂停和恢复后均不增加read。无interest=0 MOD忙转、无归池/重入读；恢复注册异常清理有FakeIO精确注入 |
| 04 跨会话/公平 | Runtime共享预算1槽/2槽/524289尾余量；第一流pending=0仍占262144，第N+1个SSE503，前流释放后新流成功；峰容量≤配置，全部对象删除后预约归零。Backpressure同时慢流暂停、快速普通请求和未发请求头的计时会话：快请求200、计时会话408均在慢流放行前完成，慢流read计数不变；原混合非SSE回退/池资格回归保留 |
| 05 期限 | 新idle有效read和write正send在9/10/11ms跨10ms截止，等于也过期；write EAGAIN/EINTR跨边界不刷新。仅“H”已提交后超时不第二头。idle剩余6ms连续pause/resume两次仍6ms，纯chunk元数据不刷新；paused response/total到期恢复不能避开。原81组合与正常新batch尾片保留；S1原response/total18例探针各18/18 |
| 06 幂等/取消 | 原SHUT_WR完整流与RST模拟后端连接结束保持；新增暂停时RST取消、重复finish/迟到deadline/resume：capacity/pending/paused为0、取消原因只记一次。真实暂停流首SIGTERM后可恢复完成，第二信号或shutdown20ms强制归零；结束时session/reserved/capacity/pending/paused/pool/timer回基线，整个Backpressure进程FD数量回基线 |
| 07 完整回归/规范 | Debug/Release/ASan+UBSan各12/12；旧120/150ms关闭窗口20/20；Release主动失败exit1；原探针构造窄适配/身份保留；实际clang-format18-i/check和人工相邻函数/分组检查；历史权威未改 |

真实慢读使用测试端SO_RCVBUF=4096及网关已接受Socket的测试friend设置SO_SNDBUF=4096，Linux实际返回均8192；测试后端SO_SNDBUF设置524288，记录实际返回以容纳已知尾部后再发FIN。测试接缝不成为产品外部接口。控制条件依actual paused/pending/token/read计数，不以sleep或backend阻塞推断暂停；观察窗口为8次有界poll，再在未放行慢客户端期间完成其他请求/超时。所有等待有deadline。日志保留各定界、cycle、累计读取量、新token和pending，而不是只记检查总数。

旧Runtime两处S1语义按Approved§2/§6明确更新：停读达到high改断言暂停且容量内，不再期待正常背压触发硬溢出；持续正send使写截止从30ms延后到最后进展+30ms。硬StreamOutput N−1/N/N+1及append失败保护仍由StreamingParser原测试保留。StreamingE2E原无限慢读场景仍中断，但当前由写无进展/绝对期限收口；它不作为“可恢复慢读”证据，后者由新Backpressure控制门证明。

## 真实容量与同时存活上界

StreamOutput固定数组容量262144字节，实际sizeof=262168（额外24字节属元数据）；ProxySession sizeof=352，CapacityLease=16，BufferBudget=152（唯一全局，含固定原因计数）。这些新增字段远小于沿用的每会话1MiB元数据余量。数组容量全部先申请后分配；不会随着历史流量增长，不保存已消费数据。parser片段和recv各16384字节；body累计8MiB/wire16MiB是计数，不是常驻缓冲。

高水最大229376，下一recv正文≤16384，封装≤8及终止5，总<245774<262144；每recv立即检查，所以不会积累整个64KiB事件批次才暂停。首次完整头规范化保守≤64KiB，加一个16KiB片段和封装也<81KiB，低于硬容量；头实际受16KiB/100字段限制。append仍独立做硬上限检查。

阶段分别计，不把峰值跨阶段相加：请求SAX原≤8MiB逻辑推导，加固定16KiB片段；流切换瞬间未释放请求output capacity<2×(1MiB+64KiB)，加固定288KiB片段/输出和1MiB元数据余量<3.41MiB，随即释放请求输出。持续流<1.29MiB，16MiB预约保守覆盖。非SSE回退沿当前Linux/libstdc++旧增长路径：请求output capacity<2.125MiB、response body capacity<8MiB、规范化output≤4.0625MiB，加1MiB元数据与16KiB新片段仍<15.21MiB。实际容量探针再次测得body=7,864,320、normalized=4,209,892（与size相同），结合源码先头后一次大body append使用；更换标准库须重核，不声称跨实现增长保证。

Backpressure在pause点记录/proc/self/statm resident_pages及页大小4096，作为离散诊断样本，不当作最大RSS、精确预算、allocator泄漏或收益证明；测试正文/客户端响应本身也在该测试进程，非产品RSS隔离测量。Socket内核buffer、allocator元数据等不混为16MiB用户态逻辑预约。容量账本与FD/live对象回基线才是本项保证。

## 实际命令、退出码与原始记录

```bash
export TMPDIR="$PWD/build-local/builder/v0.2-s2/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.2-s2/cache"
cmake --preset debug -B build-local/builder/v0.2-s2/debug
cmake --build build-local/builder/v0.2-s2/debug -j 4
ctest --test-dir build-local/builder/v0.2-s2/debug --output-on-failure
```

release/asan分别替换目录与预设。首次debug配置/构建exit0；最后debug增量build为debug-build-deadlines.log，Release/ASan configure/build分别{mode}-configure.log/{mode}-build.log，全部exit0。最终完整结果：debug-test-final.log **12/12 29.43s**、release-test-final.log **12/12 23.53s**、asan-test-final.log **12/12 46.74s**，均exit0，无sanitizer诊断。逐测试原输出独立存{mode}-LastTest-final.log；12项包含新增Backpressure及原11入口，未跳过测试。

`python3 build-local/reviewer/s2/evidence/CloseWindow.py build-local/builder/v0.2-s2/release/ai-inference-gateway` exit0，close-window.log记录FAILURES 0 OF 20；脚本仍原120ms后端/150ms额外写，SHA158de752e714596bbdacf5e0e5c351d098d74239faf95d3b7f4d63ec8b58b425。Release/FoundationTests --intentional-failure真实exit1，release-negative.log。没有重跑旧18cell成本矩阵或新增性能实验。

S1 Reviewer DeadlineMatrix、TotalDeadlineMatrix、ParseOrderProbe原件逐字节复制为E/*-original.cpp；适配版本只给旧SessionFixture加BufferBudget成员及显式构造参数，差异E/*-constructor.patch，时序/断言原样。当前构造API必须提供明确寿命预算owner，不能通过旧无预算构造绕过。按以下模式分别编译，保存*-build-final.log：

```bash
c++ -std=c++20 -g -I src -I tests -I third_party/llhttp/include \
  build-local/builder/v0.2-s2/evidence/DeadlineMatrix.cpp \
  build-local/builder/v0.2-s2/debug/libgateway_runtime.a \
  build-local/builder/v0.2-s2/debug/libgateway_foundation.a \
  build-local/builder/v0.2-s2/debug/libllhttp.a -pthread \
  -o build-local/builder/v0.2-s2/evidence/DeadlineMatrix-final
build-local/builder/v0.2-s2/evidence/DeadlineMatrix-final
```

三探针编译/运行exit0。DeadlineMatrix-final.log、TotalDeadlineMatrix-final.log各FAILURES 0 OF 18；ParseOrderProbe-final.log原16项通过及上述capacity数值。它们是精确接缝/容量检查，不替代真实网络门控。最终重链接保证使用当前库；早期探针输出也保留。

## 首次失败和过程记录

1. debug-backpressure-initial.log：新增真实Backpressure通过，但Runtime旧`!hasUpstream`硬溢出断言失败。当前高水暂停正是S2明确新契约，按上文改为paused/仍持租约/硬容量内，保留此前源历史和失败日志。debug-budget-tests.log随后2/2通过；没有放宽缓冲或时间。
2. debug-paused-events.log：增加“暂停时完整余量+FIN”后，EOF场景`sent == wire.size()`失败。后端非阻塞send受默认发送缓冲限制，尚未把全部测试尾部交给内核。仅给测试后端设置明确SO_SNDBUF并记录Linux返回值，保留网关/客户端小缓冲制造压力，未削弱“必须全发送后FIN”的断言。debug-paused-events2.log通过，随后三套完整回归覆盖FIN/RST/停止最终版本。

其他早期构建/定向测试日志均留在E，初版没有隐去失败或把重试覆盖原日志。此过程仍是首次实现自测，阶段返工0/2，独立Reviewer未开始接受。

## 格式、身份与交接

实际clang-format-18 -i及--dry-run --Werror覆盖12文件：gateway/BufferBudget.cpp/.h、GatewayRuntime.cpp/.h、ProxySession.cpp/.h；app/GatewayConfig.cpp/.h；upstream/ConnectionPool.cpp/.h；tests/RuntimeTests.cpp、BackpressureTests.cpp。工具版本format-version.log，格式输出format-initial.log/format-final.log；Runtime最后期限补充再-i，最终check exit0。git diff --check exit0。

人工逐文件确认新增相邻函数定义有一个空行（含凭证构造/析构/move、配置readStreamBuffer/readPool、lease suspend、测试friend）；头文件构造/业务/私有成员职责分组；注册lambda仍具名短转发，无新增嵌套/业务lambda。Runtime FakeIO辅助、配置/预算/时钟矩阵按测试职责分组；Backpressure单场景驱动较长，但Socket创建、收发、chunk解码、快速请求、诊断均已提取具名辅助，保留连贯门控/资源寿命以便核验时序。没有靠格式工具绿替代函数空行/回调人工检查。

source-final-sha256.json固定全产品/测试/配置身份；binaries-final-sha256.json包含三套二进制与静态库；权威/关闭脚本与保护检查见authority-final.sha256/handoff-audit.log。新来源表不会覆盖旧阶段目标hash。没有已知未解决产品失败或权威冲突；剩余为独立Reviewer验证、Leader收口及协调者按用户规则本地提交，不推送。

请重点独立审查：预算凭证与数组销毁顺序、空pending仍占容量、暂停DEL/恢复新token与迟到事件、IO跨旧期限时首字节commit、idle冻结剩余以及S1 completion矩阵。取消仅证明本地资源和模拟后端连接，不证明真实模型计算停止。
