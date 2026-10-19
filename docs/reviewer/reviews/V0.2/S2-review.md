# V0.2/S2 独立审查与验证计划

状态 `Approved`，2026-10-19；批准人Leader (Zeus)，依据用户阶段启动和既有技术决策委托；[设计](../../../leader/designs/V0.2/S2-design.md)规定行为，本文件只规定验证。批准包[Leader001](../../../leader/reports/V0.2/S2-report-001.md)。阶段待实现/Ready for Builder，累计返工0/2，不是接受报告。范围为背压、预算、取消和期限，不验证GPU或调度收益。

## 1. 身份、独立性与路线

入口为HEAD `2f7cf831a302fc87717afcae510e777187c7d0ef`上的新阶段改动，分支codex/v0.2-s2-backpressure。读取Builder最新报告、breakdown、来源变化、Approved设计、V0.2/S1 Reviewer002与原反例；核验实际文件和二进制hash，不以报告数字代替结果。项目无角色指南则回退全局Reviewer模板，使用personal-cpp-standards完整正反例和agent-execution-route。

WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`。Reviewer独立 `build-local/reviewer/v0.2-s2/{tmp,cache,evidence,debug,release,asan}`；不得使用Builder可变构建/结果目录。mkdir后导出TMPDIR/TMP/TEMP到本角色tmp，XDG_CACHE_HOME到cache。无依赖下载；已知socket/loopback、LSan边界首次精确窄升级，不禁sanitizer、不跳过受限测试。每命令单独保留退出码和完整输出。重试使用新前缀不覆盖原失败。

## 2. 验证矩阵

| 编号/需求 | 方法与必须的断言 | 原始证据建议名 |
| --- | --- | --- |
| RV01 / AC01 | 配置默认/省略/严格类型/重复/未知/上下边界/low≥high及整数溢出；数组容量与会话预约双层账本源码审计；申请失败、分配失败、发布失败、注册失败和析构路径；旧buffered实际capacity及所有新增常驻对象同时存活表 | config-budget.log、capacity-proof.md、allocation-failure.log |
| RV02 / AC02 | 真实Socket慢读门控，CL/chunked/EOF各至少2次暂停恢复；期间计数证明读调用/累计上游read字节不增而后端仍有未读正文；达low才resume，最后精确全文/单零chunk，非完整SSE event前缀仍提前可见；高水边界/最大读片/初始大头/硬容量临界 | slow-reader.log及逐阶段快照 |
| RV03 / AC03 | 暂停时后端送余量后FIN/RST，HUP/ERR及IN|RDHUP组合；DEL注册真实存在且pause无事件busy loop；新token恢复，旧batch/回收FD/迟到resume无效；EOF尾部完整与截断分辨；恢复注册失败完整清理 | paused-events.log、token-lifecycle.log |
| RV04 / AC04 | 子预算1/2槽、非整倍数余量；流pending=0仍占1槽；第N+1个SSE获503无上游保留/等待；非SSE回退正常；前流释放后下一流成功。至少3会话含停读/快读/计时故障，快读在慢读放行前完成；max_reserved_bytes仍约束混合请求 | process-budget.log、fairness.log |
| RV05 / AC05 | fake clock分类期限前/等于/后：idle有效body/仅chunk元数据，pause冻结剩余和反复resume不重置，write正数/EINTR/EAGAIN及空→非空episode，response/total暂停仍有效。完成最后read跨期限，三种HTTP定界×未send/仅一字节/前缀提交；过期时不可新增成功尾块 | deadline-matrix.log、completion-regression.log |
| RV06 / AC06 | 客户端完整请求SHUT_WR返回全流；RST/硬写错取消；pause/resume和HTTP完成分别与timeout、首信号、第二信号、shutdown期限交错；重复finish/timer/旧事件无新注册/重复计费。EOF正常与硬错不混；最终资源基线检查 | cancellation-stop.log、resource-baseline.log |
| RV07 / AC07 | 独立Debug/Release/ASan+UBSan全部CTest；复跑旧独立closing 20窗口和S1 response/total各18反例（原探针身份保留，重链接新库）；81完成边界/正常新批次仍覆盖；clang-format实际执行与检查记录、人工命名/回调/函数空行；源身份/历史保护 | {debug,release,asan}-{configure,build,test}.log、format.log、source-sha256.json |

故障注入可使用现有SessionIo/测试friend窄接缝；不得用纯计数mock代替RV02真实transport证明。添加接缝不应让产品额外暴露不受控外部开关。Reviewer检查检查器本身有Release有效断言，不删除原AssertionFailure。

## 3. 慢读、预算和公平证据契约

采用可控合成正文（固定种子/序号，≤8MiB），后端分片发送，客户端先完成请求然后停读。记录实际SO_SNDBUF/SO_RCVBUF与Linux返回值，不把设置值当有效容量；只调测试端Socket以建立可重复压力，不依赖WSL默认大缓冲或固定sleep猜测高水。可用gateway实际快照的测试接缝/受控观察，须先看到pending≥high及paused、upstream注册已撤销才放行客户端。测试总窗口有界，若未达到pause必须失败而不是记录“慢读通过”。

pause后保留至少一个受控观察窗口，记录recv次数/bytes恒定、timer/其他会话仍运行；不能以后端send阻塞推断网关已停读。客户端恢复读取直到真实pending≤low，观察resume/newtoken，反复两次后放行读取全文。HTTP解码正文必须逐字节比对，捕捉重复/缺失；核查正常零块只有一个，SSE前缀门控仍成立。三种定界覆盖完整与截断，不要求实时性能指标或吞吐门槛。

容量预算默认4MiB以及较紧1/2槽分别验证；pending清空的长流仍持有256KiB容量，避免以逻辑字节假释放允许过量allocation。记录current/peak≤配置、预约≤总额以及全局计数等于live owner之和。预算不足被拒会话不重试/不排队；释放后新请求正常。快流在慢流仍暂停期间完成且timer按期触发，用控制门顺序证明不饥饿，不用脆弱的毫秒性能比例断言。

采样RSS和相关Socket设置作诊断，记录观察区间/样本及局限，不把RSS峰值等同容量账本或对外内存收益。若RSS持续增长，与容量/FD/session基线共同排查；常驻allocator不回落本身不冒充契约泄漏，也不能据此忽略live对象增长。

## 4. 期限和终结的攻击重点

每次IO返回可能推进时钟：在给idle/write刷新或标HTTP完成前，对旧有效期限执行边界检查。复用原response/total18反例保持探针字节身份，只重链接；必要适配构造预算依赖须保留原探针并另存差异和原因，不改变时序/预期断言。原81组合保留。新idle/write矩阵分别在deadline-1、deadline、deadline+1检查，覆盖暂停前已过期、恢复时total已过期、HTTP完成后输出仍pending、stream output空很久后新片等。

暂停idle剩余量不能被resume反复充满；active body字节才刷新，纯TCP就绪和chunk元数据不刷新。response暂停期间仍是绝对期限。强制stop/finished优先于恢复；同刻total/write/response/idle分类按设计。未send允许唯一错误，入队未send不算commit；首字节send后所有错误都不再追加第二状态行/正常零块。不得通过宽松正文查找误把源正文里的“0”当协议终止块，应按HTTP编码结构验证。

下游SHUT_WR不应被误判为取消；RST、EOF、上游HTTP完成分别验证。上游模拟器可以确认连接结束，但不确认真实推理停止。正常非流式池回收与stream永不归池都要回归；暂停lease仍占容量。清理基线：fixture无保留idle时active/reserved/stream容量/pending/paused/leased/timer/注册回到0（listener/signalfd和显式保留idle按fixture启动基线计算）；实际signalfd停止后全部活动归零。不得把内部事件外requestShutdown即时snapshot限制当新SDK承诺。

## 5. 构建和接受规则

每个mode=debug/release/asan分别执行并保存原始退出码：

```bash
cmake --preset "$mode" -B "build-local/reviewer/v0.2-s2/$mode"
cmake --build "build-local/reviewer/v0.2-s2/$mode" -j 4
ctest --test-dir "build-local/reviewer/v0.2-s2/$mode" --output-on-failure
```

日志报告实际CTest数量，不预填新增后数量。按项目当前格式工具clang-format-18，覆盖所有本阶段自有/迁入C++改动，检查Builder实际-i记录并独立dry-run；人工检查具名方法、短回调、命名语义、成员分组与相邻函数空行，不能只靠格式器。产品/测试/配置/相关来源清单输出hash，旧Approved/历史清单逐项保护，不修改原来源manifest。

全部AC有独立证据、无未关闭发现/未验证契约内分支，才能PASS；明确可接受的延期仅在用户授权后PASS WITH DEBT。已复现行为/资源/规范问题按严重度FAIL，哪怕只有未接受Minor；环境阻塞如实BLOCKED，不虚报通过。发现必须有输入、当前身份、预期/实际、精确位置和影响；保留每轮FAIL与原日志。返工最多2轮，新阶段计数从0/2开始。审查不能改产品或技术权威，不提交推送；最后交Leader收口，V0.2仍需S3真实后端接受。
