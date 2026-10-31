# S2 前置归因诊断

本目录是Approved `docs/leader/designs/V0.6/S2-preflight-design.md` 的独立包装器，冻结S1工具和产品不变。History.py/HistoryTest.py由Leader维护，用于只读历史取证；Diagnosis.py复用Run.cell与既有HTTP/日志/资源审计，SelfTest.py不发HTTP、不启动产品压力。

四条件均A1024B、3840 req/s、warm3s/正式20s、双generator/总slots128、聚合cap32/预约512MiB/stream4MiB、无队列与上游复用、100ms采样。M1为客户端轮转双网关/单后端，L1增加L4，L2仅改两个后端，LP仅改各角色不同物理core的单逻辑CPU。L2是增资源控制，LP不能排除其他主机进程争用。Builder三轮依次左旋[M1,L1,L2,LP]，Reviewer每轮反序；压力必须角色串行。

`prepare`生成角色独立Frozen候选，包含工具/source/dirty diff/二进制hash、CPU拓扑/映射、taskset身份、具体12顺序、环境和可见cgroup；读取失败保留unknown/error。S1后测试/文档提交引起的HEAD变化单列，但实际source files/diff/binary必须相同。启动仍校验冻结文件SHA及所有身份，不接受负载参数覆写。Leader核对授权前不得执行run。

```sh
python3 tests/capacity_diagnosis/Diagnosis.py prepare \
  --manifest build-local/builder/v0.6-s2-preflight/evidence/manifest-002.json \
  --role builder \
  --gateway build-local/builder/v0.6-s1/gateway/ai-inference-gateway \
  --l4lb build-local/builder/v0.6-s1/l4lb/bin/l4lb \
  --s1-source build-local/builder/v0.6-s1/evidence/source-before.json
python3 tests/capacity_diagnosis/Diagnosis.py run \
  --manifest <已批准的角色清单> --sha256 <实际冻结SHA256> \
  --output <该角色本轮evidence/run>
```

以上命令必须设置本轮TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；stdout按1MiB限制，回环run使用窄权限路线。Reviewer使用自身S1二进制/源身份和新角色目录。run目录必须不存在，不提供resume/覆盖/重试入口。

## 亲和性与生命周期

仅对LP先把controller主线程绑核，在确认没有遗留线程后创建monitor/capture，线程继承该CPU。自有child由taskset启动，最多1s等待其真实PID亲和性生效；记录所有controller/monitor/capture TID实际affinity。资源流复核各角色在正式窗口实际出现且affinity吻合。LP物理core通过sysfs(package,core)去重，需要至少7个；L2继承亲和性，7子进程各128MiB地址空间=896MiB，仍由旧监控执行聚合1GiB RSS/2048FD门槛。

所有启动、捕获和TERM/KILL/wait由旧Owned/Run.cell管理；构造器核验失败时先关闭自身child再抛错，首错停止。包装器结束恢复controller原affinity。拒绝或传输失败保留为实验结果；正文/审计/资源/工具错误停止后续cell。

## 预算和证据

全12项最坏预留1,042,169,856B，加16MiB根级清单/检查点/收口池及采集前已有文件须≤1.5GiB。每项额度为`3840*23*(512+192*后端数+L路径256)+3MiB+320KiB`：原客户端/后端/L4 writer caps及3MiB固定开销不动，新增10×32KiB覆盖亲和性启动/核验/失败取证。各分片≤1MiB。每cell前继续核验预算，失败不返还实际证据空间、不重置账本。

旧ledger保留cell活动细分，每项45s、最多12项；包装器另从run入口计时，含verify、采集、亲和性复核及汇总，启动前要求elapsed+45≤540s，每项后检查总elapsed≤540s，收口记录总活动。正常清理遵循旧工具有限TERM/KILL grace，不把恢复后的成功当作首次无错。

`checkpoint-<ID>.json`恰一次保存每项审核通过结果，完整结束才写summary.json。发生错误保存attempted/verified/failed_verification/not_started，已发压但后置核验失败的当前项不会冒称未执行。原始result/spec/资源/逐ID/日志及全部失败分母保留。

## 解释边界

沿用全计划分母、HTTP framing观测100ms SLO/≥99%、not_sent≤1%、dispatch P95≤5ms；success还要求EOF和完整正文校验。成功样本分位不替代总体达标率。对L2或LP分别按同role/repeat配对L1，两角色六对均改善≥5个百分点才称稳定正向敏感；否则保持未隔离。不得将L4会话ID强行关联HTTP请求ID，容量拒绝的源码路径在没有直接计数前只是候选。诊断完成不自动授权S2产品修改。
