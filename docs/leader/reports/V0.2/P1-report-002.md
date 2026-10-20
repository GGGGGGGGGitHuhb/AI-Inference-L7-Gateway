# V0.2/P1 Leader 收口报告002

2026-10-20；Leader (Zeus)。独立性能基线专项已完成，Completed，累计返工0/2。测量与独立审查日期为2026-10-19；本报告接续中断前Closing，不重复测量或改写历史。

## 第一部分：PM 决策摘要

**结论与健康状态：On Track，P1验收收口完成。** Reviewer001结论PASS，无未解决发现或债务。V0.2开发验收保持完成，S3不重开，V0.3/V0.4未启动。

**计划与实际：** 已交付模拟直连/代理成本、并发/慢读资源及固定CPU模型TTFT/E2E/闭环完成率基线，包含可复现工具、所有重复与原始样本、用户结果报告和独立测量附表。测量与文档范围无未完成项；本地提交由协调者随后执行，不推送。

**已验证成果：** Builder最终与Reviewer独立运行各72个单元、19,380条含预热样本，均0失败。Reviewer独立Release回归15/15，对两份最终数据各完成40,498项复算。真实流并发1的TTFT p50三重复中位：Builder直连/代理14.559/15.634ms，Reviewer16.603/17.387ms；它们是各运行的聚合观察，不是配对请求因果开销。

**重大偏差与风险：** 需新增接受的偏差、债务或阻塞：None。已批准的解释限制继续保留：模拟连接复用路径约44ms，比当前直连/关闭路径慢；高并发和发压控制存在工具/机器漂移迹象。这些结果不支持最大容量、GPU性能或优化收益，不能宣称“连接复用更快”。

**PM决策：None。** 建议保留本次基线用于以后回归；约44ms现象如需定位，应另行授权有限诊断，不在P1追加产品优化或推测根因。

**下一步：** 协调者核对文档/源身份和提交范围后，按既有授权创建本地提交并报告提交号，不推送。下一开发阶段等待用户启动；本专项完成不等于发布。

## 第二部分：详细工作记录

本部分供PM按需查阅。

### 权威与执行路线

依据用户“可以，别忘了文档，做吧”及已记录技术委托、[Approved设计](../../designs/V0.2/P1-design.md)、[审查计划](../../../reviewer/reviews/V0.2/P1-review.md)和[Leader001](P1-report-001.md)。固定权威保留规划时的待实现快照，当前状态由本报告及根文档表达，不修改其原字节。

| 文件 | SHA256 |
| --- | --- |
| P1-design | b65bf637c62463d5a7863c3e1fc988b9d27122e284c9d0cea4978e818fb45a2f |
| P1-review | ab535bb2e4ee4aaf39675478ef507a38cdecb17a4a998d3f0a8a6d23d465d397 |
| Leader001 | 3938f140b1dedd9ec43346ffeaf594095864c32191d72db8d70c06998f55879f |
| Builder001 | de8203f8d8ed135930855302b06d8ed9f5a34c2bce96acd2329dc74a709e51d7 |
| Reviewer001 | c2d810dd8abdacff5f6cf97cc2d1e256948b28c50b7285af698856edcf198011 |

分支codex/v0.2-performance-baseline，起点HEAD555b65d66a52d95791dba5445178e57a69b81d2c。沿用原生WSL /bin/bash login=false、仓库/home/power/projects/AI-Inference-L7-Gateway；Leader专属build-local/leader/v0.2-p1/{tmp,cache,evidence}，Python显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。没有项目专用Leader guide，沿用plan-project-docs全局Leader模板及用户跨项目规则；应用agent-execution-route和Olympus。此次仅文档/身份检查，无C++设计或修改、无构建/测试/性能重跑，无安装/下载/提交/推送。

### 实现、审查及接受追溯

[Builder001](../../../builder/reports/V0.2/P1-report-001.md)交付六个Python工具、运行说明、CMake快速检测入口及结果。产品src、第三方和旧S3工具保持。Builder交付前自查的中断样本修复及一次全组重跑均保留初始源码、失败负控和初次运行；没有择优或用旧run冒充最终身份，P1初审通过、返工0/2。

| 接受项 | 已执行证据与结论 |
| --- | --- |
| AC01 身份/范围 | Reviewer独立54源文件、2运行binary及12Release产物身份核验；固定CPU资产与CLI保持；102服务启动/回收配对，无遗留负载 |
| AC02 固定矩阵 | 两角色各69cell+3控制，矩阵16,140、控制1,500、预热1,740；最终各19,380唯一样本、0失败/0未开始；PC/PR实际连接差量核验 |
| AC03 时钟/异常 | HTTP终态与EOF、首非空内容TTFT分离；独立边界/晚到异常探针通过；实际SIGTERM单/双发压均16 started=16 saved、112 not_started，外层预期exit1 |
| AC04 统计 | Reviewer标准库独立脚本从原始样本/资源复算两份最终run，各40,498项一致；失败/成功分开，零成功null、低样本尾分位与token来源边界保持 |
| AC05 回归/控制 | Builder最终Release15/15、26.65s；Reviewer15/15、27.53s；发压器控制和机器采样完整，波动如实披露；没有重跑旧三套或S3长期矩阵的声明 |
| AC06 文档/状态 | 用户结果并列两角色观察、完整附表与复现证据；根状态及本报告收口，无发现/债项，无产品范围扩张 |

Builder最终run-002耗时698.969s；此前run-001为744.680s、相同样本总量且0失败，但属于初始工具身份。Reviewer独立run-001为751.520s，没有重复择优。详见[Reviewer001 PASS](../../../reviewer/reports/V0.2/P1-report-001.md)及[独立附表](../../../reviewer/reports/V0.2/P1-measurements-001.md)。本Leader据此收口，不替代独立验收。

当前独立源清单build-local/reviewer/v0.2-p1/evidence/source-sha256.json共54项，文件SHA256 c6b5c9d1b3dc42399817a73e4d77a120a372c416b870e2e183334aaa0c61dc02；独立run manifest为b46e136388ec1ae7dd24b38273fc31665bb8746445abfb21f64fd51618354088。Builder最终manifest为2979fd7f039ba545b36679897db2138b80090cee3f71018801fa4420222a6db6。收口只调整文档，不变更测量身份。

### 观察、局限与后续参考

[用户结果报告](../../../performance/V0.2/P1-results.md)保留Builder原表和两次运行身份，新增Reviewer独立核心表及完整附表入口。A并发1 D/PC/PR E2E p50三重复中位：Builder0.734/1.359/43.908ms；Reviewer1.035/1.721/43.894ms。真实流并发1 D/P E2E对应362.725/364.851ms与443.916/423.359ms；方向波动不构成网关加速证据，也不作单请求配对因果解释。

两角色C慢读均实际触发pause/resume，内部容量峰1MiB、预约峰64MiB，自然排空回FD7及零活动账本，之后停止自有host。资源账本不同于RSS，采样峰不是真实峰值。CPU模型单slot、缓存、共享主机、Python客户端/后端、闭环coordinated omission及三重复样本限制全部保留。Builder最终双发压差异>15%和部分客户端近一核、Reviewer前后控制漂移>20%，禁止据高并发曲线宣称容量。约44ms根因未定位，不归因Nagle/GIL或某个具体机制。

仓库没有TECH-DEBT-TRACKER.md；独立验收无债务，故不新建空债务清单，也不将后续有限诊断建议冒充缺陷或已批准工作。无未接受Blocker/Major/Minor，无重大权限/发布变化。

### 文档收口与保护

本次接续前序Leader已编辑的README、ROADMAP、ARCHITECTURE、CHANGELOG及P1-results，新增本报告。核对并修正当前收口日期为2026-10-20，保留2026-10-19的测量/审查与规划历史；ROADMAP当前摘要同步已有固定CPU性能观察，避免旧“没有真实推理性能结论”与P1结果冲突。未覆盖历史角色报告、Approved、原始cell表或原始数据。

复用既有build-local/leader/v0.2-p1/evidence/closing-protected.json，不覆盖快照；最终逐项保护、54源身份、相对链接/围栏和git diff --check证据存于同目录closing-resume-check.log，交接文件SHA存closing-resume-identity.json。无负载测试重跑。P1测量/文档阶段Completed，V0.2开发验收完成；当前本地提交待协调者执行，远端未核验且禁止自动推送，没有发布或V0.3启动。
