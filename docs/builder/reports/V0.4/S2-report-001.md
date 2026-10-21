# V0.4/S2 Builder 实现报告001

2026-10-21，M1首次负控失败，**停止纠正、待Leader返工评估**。未进行正式性能矩阵、三预设完整CTest或独立验收。S2当前0/2已执行返工，原S1历史不变。

## 目标、输入与实际实现

按[Approved设计](../../../leader/designs/V0.4/S2-design.md) SHA256 `e26173c6cc5862d37f95cff96162be814a23018829eaa4cfe2cce50ae9bd0410`、[审查计划](../../../reviewer/reviews/V0.4/S2-review.md) SHA256 `20d0e143bdf7b2e6f8d34bcefa203d8a7880d269873b4c2cd2d45aa7d7207692`、[Leader001](../../../leader/reports/V0.4/S2-report-001.md) SHA256 `13af91ff0ac67ea82728e90230b4671addd0810627c429579e40599e1f13a4e4`实现配置级500ms/100ms比较。读取执行路线、文档Builder/阶段设计模板；无项目Builder指南。只读定位产品头规范化时读取C++规范及正反例，无C++修改。

新增`tests/queue_budget/QueuePlan.py`冻结21cell/2970ID；`RunQueueBudget.py`局部继承Cell，仅覆盖gateway配置构造，复用原Budget/Worker/Client/Host等；`QueueAudit.py`验证scheduled来源、全部长短类分母、超时未派发、终态唯一和配对门槛；`DetectorTests.py`提供统计反例、三配置实际加载、真实占位超时及两项失败闭合控制。三份configs与README、实施拆解已写。尚未验证后续全部路径，不称工具已验收。

预期M1所有控制通过，M2三套回归及一次矩阵；实际完成Release自有构建、Python语法检查、离线反例和三份配置Host实际加载，但真实超时控制未建立稳定占位，首次命令退出1。没有正式性能结果，未产生候选收益结论。

## 首次失败与只读定位

证据根`build-local/builder/v0.4-s2/evidence/controls-001`及旁边`.log`、`.exit`，原始全部保留。失败点：`gate deadline: actual two occupied slots`。两个host session均确实dispatch至backend0/1，但约1ms内结束为`upstream_error`，`peak_inflight=2`而后续状态inflight=0，因此等待两条后端接收且inflight=2未满足，第三条排队请求未启动。

静态原因清楚：新控制后端以普通bytes dict解析HTTP头，然后用`headers[b'X-Experiment-Id']`取ID。产品`HttpParser::handleHeaderValueComplete`将字段名转为小写，`HttpNormalization`转发该字段名，故线上为`x-experiment-id`。`Content-Length`是序列化时重建的规范大小写，不能据此推定自定义字段大小写。控制后端发生KeyError会关闭上游连接，符合host的upstream_error。**首次线程异常只存在控制进程内存的errors列表，未落盘；因此具体异常字符串没有首次运行日志，不能冒称已捕获该KeyError。** 此处为源码确定的不兼容与观测一致的定位。

最小建议：只在新增DetectorTests中按HTTP语义大小写无关解析头名；在finally持久化后端接收/异常、客户端结果和占位gate状态，避免将来只看到外层超时；补一个小写/混合大小写控制，保持真实占位→入队→504→释放→drain条件不放宽。旧产品和S1工具不需改变。待Leader新返工权威再修改和使用新controls目录验证，保留controls-001。

## 命令、身份与清理

原生WSL bash login=false；cwd `/home/power/projects/AI-Inference-L7-Gateway`；分支`codex/v0.4-s2-evidence-driven-improvement`，HEAD `752987a0564e8a99c0833c7f2af7e65ad561e491`。TMPDIR/TMP/TEMP显式指向`build-local/builder/v0.4-s2/tmp`，XDG_CACHE_HOME和PYTHONPYCACHEPREFIX指向独立cache。loopback首次使用窄权限，无下载、安装、调系统。

```bash
cmake --preset release -B build-local/builder/v0.4-s2/release
cmake --build build-local/builder/v0.4-s2/release -j4
python3 -m py_compile tests/queue_budget/*.py
python3 tests/queue_budget/DetectorTests.py --host build-local/builder/v0.4-s2/release/ExperimentRuntimeHost --output build-local/builder/v0.4-s2/evidence/controls-001
```

构建退出0；语法检查退出0；首次控制退出1。`configure-release.log`/`build-release.log`保存构建记录。`failure001-audit.json`记录新增源、host身份、保护与清理审计：Leader冻结236项全部原字节不变，四个Host子进程均有start/reaped配对，失败控制Host exit0。监听器关闭，所有创建线程在finally join；没有仍运行负载。`git diff --check`通过。

## 未完成及Reviewer重点

先修控制后端与证据留存，再完成真实超时/退出/预算控制、Debug/Release/ASan全量21项和唯一21cell正式run；目前三套CTest与矩阵均未执行。新工具其余路径尚未实际检验，可能存在后续发现，不能以语法检查代验收。README、ROADMAP、ARCHITECTURE现有Leader修改保留，未改其权威。Reviewer特别关注完整分母、已过期不派发、长短类和工具限制、首次失败未覆盖。Builder不提交或推送。
