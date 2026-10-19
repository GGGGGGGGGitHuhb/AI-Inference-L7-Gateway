# V0.2/S2 Leader 规划报告001

2026-10-19；Leader (Zeus)；阶段待实现，编排Ready for Builder；累计返工0/2。

## 第一部分：PM 决策摘要

**结论与健康状态：On Track，可以进入实现。** 用户已启动S2，阶段内技术选择按既有委托采纳，设计与独立审查基线Approved。

**计划与实际：** 本阶段让慢客户端触发可恢复的上游停读，限制全进程受控缓冲，并明确取消、流空闲、写无进展与总期限。已交付设计、验证矩阵和当前状态更新；产品实现与独立验收尚未进行，V0.2整体未完成，S3真实后端未启动。

**已核验成果：** 起点为S1本地提交2f7cf831a302fc87717afcae510e777187c7d0ef，工作区初始干净；源码确认固定流输出容量及原事件注册语义。S1独立PASS和一次期限修复作为前置，不把旧测试当本阶段结果。

**重要取舍与风险：** 选择固定容量、默认高/低水位192/64KiB和4MiB进程SSE容量子预算，配合原会话总预约；缓存清空不立即返还数组额度。暂停时上游断连可能延后观察，由绝对期限兜底。流式写超时改为有效发送进展计时，新增流空闲保护；非流式保持。实际RSS、内核缓存、远端GPU停止不由此承诺。重大未解决偏差、风险接受或债务：None。

**PM决策：None。** 现有启动和技术决策授权足够推进，无需再次批准常规实现选择。批准包为本报告引用的S2设计/审查SHA；没有新依赖、外部费用、平台或发布范围变化。

**下一步：** Builder按固定基线实施并自测，Reviewer独立验证真实慢读暂停恢复、跨会话容量及竞争清理；全部AC通过后Leader收口，协调者按“以后每次工作完成都提交，不推送”本地提交。当前没有新实现提交或推送，也不假定S1已推送。

## 第二部分：详细工作记录

本部分供PM按需查阅，实施和独立审查以权威文档为准。

### 权威、身份与路线

[设计](../../designs/V0.2/S2-design.md) SHA256 `5dfc90adad8f0b9802a946b713434540a1954c69b3a2344a161f025b60e9bef6`；[审查计划](../../../reviewer/reviews/V0.2/S2-review.md) SHA256 `af34802f758c1598b0fa89008b8ea5d694f055f65c8b354c65f52897aa93b201`。均Approved/待实现，批准依据用户“开始s2工作吧”和“你来决策吧”，新阶段0/2。后续技术变更走新返工权威，不静默改批准基线。

前置为V0.2/S1 [Leader002](../V0.2/S1-report-002.md)及[Reviewer002 PASS](../../../reviewer/reports/V0.2/S1-report-002.md)，S1累计1/2；V0.1各阶段2/2、1/2、1/2保持。旧设计、报告、来源清单及失败证据不覆盖。未发现项目技术债台账；无接受债项，不因正常未来功能创建空台账。

适用用户AGENTS规则以及agent-execution-route、personal-cpp-standards完整规范/正反例、plan-project-docs、Olympus；项目没有独立Leader指南，回退 `plan-project-docs/references/role-guides/leader-guide-template.md`，遵循其中PM决策与两层报告规则，不复制第二套政策。

原生WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`，分支codex/v0.2-s2-backpressure，HEAD `2f7cf831a302fc87717afcae510e777187c7d0ef`。Leader目录build-local/leader/v0.2-s2/{tmp,cache,evidence}，脚本前显式设置TMPDIR/TMP/TEMP/XDG_CACHE_HOME。未执行产品测试/依赖下载/跨权限操作；Builder和Reviewer使用各自目录，已知Socket/LSan边界精确测试首次窄升级。未派生代理、未改产品/测试或兄弟仓库、未commit/push。

### 源码决策与兼容差异

已读StreamOutput、ProxySession、GatewayRuntime、GatewayConfig、EventLoop及ConnectionPool，结合S1 Approved协议/期限与最新接受链：

- StreamOutput是固定262144数组，consume只减少size；因此容量凭证按数组全额而不是pending计费。Runtime原16MiB/会话总预约保持，新的容量子预算动态约束活数组，分配前申请、销毁后释放；不重复算两份实际可用内存。旧std::string capacity仍须实测及保守上界证明，不能拿logical size冒充实际分配。
- EventLoop给已注册channel设置interest=0只是MOD，HUP/ERR仍可能反复到达。租约新增窄DEL暂停，恢复新token，保留唯一所有权和回调后清理；不重写整个事件层。暂停上游错误延后观察的可保证边界已明确。
- S1流式连续非空批次期限会使有真实写进展的慢流结束；S2按既定路线改为send>0刷新无进展期限，仍受response/total绝对上限。非流式与非SSE回退不变；新增stream_idle只看body进展，暂停保存剩余时长而非反复给完整窗口。
- S1唯一Major已通过完成转换前重查期限修复；S2要求所有读/解析/写进展更新在旧期限验证后，保留未send/仅首字节/已发前缀与CL/chunked/EOF边界矩阵，不借新增期限削弱原结果。
- 取消与正常读半关闭分离，首信号可排空、强制停止优先；预算/注册/timer/lease恰好一次结算。内部事件外requestShutdown限制仍是SDK边界，测试实际事件→cleanup路径，不暗中声明额外支持。

相对于S1，新增配置对象和idle默认均为本阶段显式兼容差异：旧配置继续可解析并自动获得默认保护，流式慢读不再正常触顶失败，有效send可延长写空闲窗口但不能延长绝对响应/总期限。高低水位与容量默认、边界错误规则及503预算耗尽无等待均写入设计。没有未解决技术冲突或需要用户二次选择的底层方案。

### 验收和交接

七组AC一一对应RV01—07：配置与真实容量、慢读恢复、暂停事件、跨会话预算/公平、分类期限、取消/停止幂等、三预设及旧关闭/完成反例。真实慢读必须先观察pause/recv停滞再放行客户端，至少两轮恢复，三种定界精确全文；单纯最终文本或backend阻塞不是通过证据。多会话证明空pending仍占额度、耗尽拒绝、释放后可用及快流在慢流仍暂停时完成。RSS仅另行诊断，无性能收益声明。

Builder依M1预算/配置、M2暂停恢复、M3期限取消、M4完整证据推进；独立Reviewer复核当前身份与具体原始结果，失败保留并最多两轮有限返工。提交权限只由协调者在本阶段验收收口后执行；本报告不提前宣告完成。

本轮只新增三个S2文档并更新README/ROADMAP/ARCHITECTURE当前阶段入口。没有在CHANGELOG新增未实现能力，旧历史时点状态保留。保护快照 `build-local/leader/v0.2-s2/evidence/planning-protected.json` 含112项已跟踪非根状态文件，SHA256 `8ee5b0819d652bada18a211407e7b52f42cf842a77cf3c66977bfb8e8b474e90`；文档链接/权威hash/保护/空白检查见planning-doc-check.log，六个输出文件hash见planning-identity.log。证据为规划一致性检查，不冒充本阶段产品验证。
