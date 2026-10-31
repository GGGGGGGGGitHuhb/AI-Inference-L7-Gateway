# V0.6/S2 前置诊断 Builder 实施拆解

依据Approved S2-preflight-design/review。沿用原生WSL与agent-execution-route；本仓无专用Builder指南，采用plan-project-docs Builder参考。只负责独立包装器与本角色证据，不改冻结capacity工具、产品或L4工作树；History.py/HistoryTest.py由Leader独占。

| 项目 | 实施与验证 | 状态 |
|---|---|---|
| 独立包装器 | 固定四条件×三重复；复用Run.cell生命周期/审计；更严预算与唯一输出 | 完成 |
| LP绑核 | sysfs互异物理core，controller及其线程同核；子进程taskset，实际PID与采样affinity核验 | 完成 |
| 无发压自测 | 顺序、预算、拒绝覆盖、源保护、亲和性、首错停止、子进程回收 | 11/11通过，无HTTP压力 |
| 冻结核对 | 原S1源码/dirty diff/Release二进制、旧工具hash、12顺序、CPU映射、环境、全矩阵预算 | manifest002经Leader/Reviewer核对，已执行 |
| 采集/交接 | Builder12项后停止压力，Reviewer反序串行；失败保留不重试 | Builder12/12完成，72子PID回收；Reviewer独立复验中 |

角色根build-local/builder/v0.6-s2-preflight/{tmp,cache,evidence}；TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX显式绑定本轮。每项45s、累计540s/12项、证据1.5GiB、分片1MiB、采样RSS1GiB/FD2048。L2七子进程地址空间896MiB按新设计批准，不改旧CLI六进程保护。无产品重建/CTest，无Git操作。

Builder结果与预算见S2-preflight-report-001.md；全过程无工具首停，无补跑。冻结工具不再修改，S2产品入口仍待可行动直接证据。
