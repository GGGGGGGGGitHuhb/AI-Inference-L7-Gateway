# V0.4/S2 Leader 最终收口报告006

2026-10-21，Completed / On Track，累计返工 **3/3**。

## 第一部分：PM 决策摘要

**结论：On Track，V0.4/S2开发验收完成，V0.4/S1与S2均已完成开发验收。** Reviewer001独立PASS，无剩余发现或待接受债务；未发布，V0.5未启动。

**计划与实际：** 已交付三份可运行配置、固定对照实验、两角色独立完整21cell/2970ID及结果文档。Reviewer run002一次278.780588s完成，两rate有效三元组各3/3；原独立三套各21/21和控制按精确身份复用，本轮未重跑。剩余仅协调者本地提交、不推送。

**已验证观察与风险：** 在固定60req/s合成负载下，100ms候选相对500ms实验基线goodput三点+18/+21.5/+19.5req/s，5req/s未见误杀。但发压敏感与CPU限制仍触发，**不推荐替换基线**，不宣称因果、容量或真实推理收益；产品默认1000ms不变。原外层143中断的发送者与确切根因仍未知，新run通过不回填旧原因。

**PM决策：None。** 用户已批准新增一次有限继续，累计3/3；独立验收与全部文档齐备，无第四轮返工。Leader建议按PASS关闭本阶段；协调者核验后本地提交不推送即完成本轮交付，后续版本需另行启动。

## 第二部分：详细工作记录

供PM按需查阅。

### 权威与接受证据

依[原设计](../../designs/V0.4/S2-design.md)、[审查计划](../../../reviewer/reviews/V0.4/S2-review.md)、[返工001](../../reworks/V0.4/S2-rework-001.md)/[002](../../reworks/V0.4/S2-rework-002.md)/[003](../../reworks/V0.4/S2-rework-003.md)、Leader004条件B及Leader005用户新增授权收口。[Stop001](S2-stop-001.md)与所有旧报告、失败证据、原Approved均保留。

输入[Builder004](../../../builder/reports/V0.4/S2-report-004.md) SHA256 `e8fe3babee2682b278008cc660db18481036a68b1a89e20c2944c63fbb2e33c3`；[Reviewer001 PASS](../../../reviewer/reports/V0.4/S2-report-001.md) SHA256 `3a79d9f5863a90a5f706afb66d79927fd04f432cbe9d31ca4a06e78840d88767`。Reviewer所有AC/RV01–05通过，无发现或债务。产品源码不变，唯一旧测试例外为RunAdmission.py统一停止请求所有权，严格零退出、sanitizer及资源保障保持。

返工001关闭新控制后端大小写不兼容及失败取证；首次KeyError文本未捕获不回填。返工002诊断实测重复SIGTERM与−15，条件B修复测试幂等停止；原首次ASan退出码仍未知，mask恢复精确内核时点不称实测。返工003来自用户新增一次批准；只增强Reviewer执行生命周期记录并完整重跑矩阵，原run001外层143根因未知，不称超时/环境抖动/未await或产品错误。

### 验收与数据边界

独立Debug/Release/ASan各21/21（43.61/39.80/64.06s）及真实控制/独立反例在中断前通过；按249保护项、9源/配置说明及42binary完全一致复用。新run002完整21cell/2970ID，278.780588s；正式2760为2290成功/320 queue_full/150 queue_timeout，预热210为198/9/3，无未发、未开始、协议/传输/deadline错误。独立自写RawAudit首次通过，超时入队未派发、后台无请求，完整分母/长短类/等待分布及SLO保留。

两rate有效三元组各3/3，5req/s B/C全部成功。60req/s C−B三点+18/+21.5/+19.5req/s；配对相对变化+120/+165.385/+139.286%。独立T为1275.412/1990.847/1202.916req/s，drift=false、generator_sensitive与CPU限制=true；数值门槛通过不能取消工具限制。双角色不合池、不外推真实推理，500ms仅实验基线、100ms预注册候选而非最优，默认1000ms保持。

101实验PID全回收，drain账本全零、FD回基线；RSS最大4542464bytes，预热增量163840bytes≤32MiB；direct/managed/emergency为93847552/7847973/34903bytes。实际采样最大0.120142635/1.009750174s，不称硬实时。监督run002实际returncode0、无收到信号/剩余子进程，自CPU0.098449s；未触发强杀分支不冒称故障注入已验证。旧14cell未拼接。

### 文档、保护与交接

同步README/ROADMAP/ARCHITECTURE/CHANGELOG当前状态；原S2结果全文保留为前缀，仅追加独立接受及比较，见[结果](../../../performance/V0.4/S2-results.md)。V0.4为开发验收完成而非发布；V0.5仍未启动，无新参数搜索或产品优化。

沿用用户AGENTS及无项目指南时共享Leader模板回退、已读取PM关系/双层契约。原生WSL bash login=false，repo=/home/power/projects/AI-Inference-L7-Gateway；Leader独立v0.4-s2 tmp/cache/evidence及显式环境。分支codex/v0.4-s2-evidence-driven-improvement、提交前HEAD752987a；只读/文档校验，无构建、测试、负载或网络。TECH-DEBT-TRACKER不存在，无债务接受需要，不新增空表。

证据`build-local/leader/v0.4-s2/evidence/closeout006-before.json`与`closeout006-check.json`核对所有既有src/tests/docs、Reviewer源/42binary及保护身份，唯一既有docs差异是结果追加；Reviewer/Builder报告、旧权威/Stop/raw保持。六收口文档检查链接/围栏及git diff --check。阶段独立PASS齐备，Leader据此关闭；本报告为提交前快照，协调者精确暂存、本地提交并核验，不推送，不为写入新commit循环改历史报告。
