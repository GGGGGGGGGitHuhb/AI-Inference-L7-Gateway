# V0.6/S1 Builder 003：Approved返工001实现与派生复审

2026-10-29。依据`docs/leader/reworks/V0.6/S1-rework-001.md`（Approved）及原S1设计/审查计划。产品、负载、SLO、预算不变；本报告不表示已完成余65正式cell。

仅修改测量器：Analyze完整session行fullmatch，reason以明确sent_c2b字段结束，支持`shutdown SHUT_WR`；校验SID、端点与唯一性，未知session行拒绝。SelfTest新增多词reason、重复SID、缺结束、端点不符和受控prefix/指纹负控。Resume.py/Run/Formal新增仅本次rework受控入口，拒绝关键CLI覆盖；v2从头formal同样核对parent与相同矩阵/数字语义。

11组SelfTest全部通过（`evidence/selftest-rework001.log`）。只读注入负控进一步确认实际spec.capacity与冻结值不符会拒绝、非指定原错误会拒绝，输入文件未变（`evidence/rework001-guard-probes.log`）。

`Resume.py --output build-local/builder/v0.6-s1/evidence/run --gateway .../gateway/ai-inference-gateway --l4lb .../l4lb/bin/l4lb --parent docs/performance/V0.6/S1-manifest-v1.json`派生审计7项成功，没有发任何新请求。`formal-reaudit-r2/summary.json` SHA256 `88d6e6af863080ee6ec775a4356f6a06316ce79640d1bc76b17f233fd1770e6a`，包含每个输入文件hash、原result、原ledger bytes快照、原plan/provenance和binary身份、派生结果及工具hash。前6数值强制等于原已成功结果；第7恢复完整日志解析，保留正式26 transport_failure及预热38 transport_failure。

原6 complete+1 failed ledger/result状态不改，所有原始分片、v1清单与首错保留。累计cell仍51（44校准/诊断+7正式）；派生处理开销作为auxiliary累计活动，不虚增或重置cell。余65只在新冻结工具/清单、Reviewer核对与Leader授权后执行。

Leader冻结v2 SHA256 `292cbafde4460b1af038e909cf82b2d4c6d804022494dc3c9d5286705b698f0e`，原v1 SHA256 `81877a406c767b66fb90422a79b805f53c3c77a13869219b4f967ee5116358f4`。当前尚等待最终独立静态核对/续采授权。py已再次封口，未扩展通用恢复或更改产品。

Reviewer重点：原七项指纹不可变；第七项仅特定日志语法错误可派生接受；实际spec及原binary/source一致；auxiliary running也必须拒绝；任何其他原infra错误不可恢复；余65是全新ID并按剩余最坏预留+已有证据+诊断/收口池预检。独立Reviewer从头使用v2，不把Builder派生作为独立容量样本。
