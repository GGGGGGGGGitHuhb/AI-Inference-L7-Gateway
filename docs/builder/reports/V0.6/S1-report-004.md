# V0.6/S1 Builder 004：返工002与18项派生复审

2026-10-29。依据Approved `docs/leader/reworks/V0.6/S1-rework-002.md`及原S1设计。产品/采样间隔/矩阵/SLO/预算不变。状态：有限修复与18项派生完成，等待独立核对及v3续采授权。

v2正式第18项`F-S-M-480-r0`收口监控PermissionError首停。实际只采了r0的18项：A三档×四路径12项、S六项，**未完成任何三重复容量验收**。先前一次进度消息误把三档称三重复，已即时向Leader纠正，报告以manifest.repeat与ledger为准。

原第18项9600正式计划=7634成功+1966 HTTP拒绝，无正文/协议损坏，4子进程exit0，drain存在。资源244行中197行为正式窗口样本，5进程真实CPU窗口19.884787034s、采样峰RSS113541120B/FD110可独立复算。最后row.end在formal_end前16.285432ms；冻结实现完成该行后执行100ms等待，下一轮可能发生权限I/O的下界在end后83.714568ms、最后client.close后46.517916ms。此证明不识别具体PID或系统调用，也不把收口监控说成首次完整。

Runtime有限修正：读取自有子进程出错后再poll，仅确认退出才跳过；存活进程和控制器权限错误保持fatal。新增有界采样时间/PID/name/phase/exception/traceback证据，64KiB计入既有3MiB固定分配。Common.proc仅对确认TID目录消失的ENOENT跳过该线程，进程总ticks仍保留；PermissionError不忽略。没有改全局/proc权限。

现有Resume只增加第二个固定18前缀与两精确原错，保持第一固定7前缀路径及v1/v2链完整；不是通用恢复。初次派生预检暴露原最低3进程假设不适用于S/B单发压两进程，日志保留且无发压。按Leader指示改为冻结backends/workers/path推导精确名称集合、数量/PID唯一性、exit0和capture_error核验，负控覆盖A/S×B/G/M/L缺失/重复集合。

验证：`SelfTest.py`15组通过，日志`evidence/selftest-rework002-fixed.log`；原14组日志及首次derive预检错误日志保留。`Resume.py --parent docs/performance/V0.6/S1-manifest-v2.json`生成18项`formal-reaudit-r3`，没有新请求。summary SHA256 `836ee2779ac05db9ba9f22314ed71bbfae6281ded8f347c31dd1443129d60102`，绑定全部原始逐文件SHA、原结果/ledger快照/plan/两份provenance、binary及新tools。所有请求指标与旧已知结果一致；第7沿用r2解析修复，第18带明确sampling_coverage证据。

两个原failed ledger/result未改。累计62cell（44校准/诊断+18正式），派生工具处理活动另记，不重置预算。v2工具源先按其hash逐个归档到`evidence/tool-v2-sources/`，便于独立核对旧时序。

Leader已冻结v3 SHA256 `66b57cde541599fcc8e2666b618d7f5910913a7b9c025a6319cac5db4d026198`；v2为`292cbafde4460b1af038e909cf82b2d4c6d804022494dc3c9d5286705b698f0e`。在Reviewer readiness及Leader授权前不执行余54项；py封口。若再次未知关键采集错，按rework002受限交付，不追加恢复框架或重发旧ID。
