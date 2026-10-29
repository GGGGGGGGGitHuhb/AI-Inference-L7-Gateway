# V0.6/S1 Builder 001：容量设施与校准

状态：实施/自测完成，正式矩阵执行中，独立验收待完成。2026-10-29。

依据 Approved `docs/leader/designs/V0.6/S1-design.md`、`version-plan.md`、`docs/reviewer/reviews/V0.6/S1-review.md`及Leader本次明确控制授权。项目无专用Builder GUIDE，使用全局plan-project-docs Builder参考模板；agent-execution-route采用原生WSL与角色独立目录。未改产品、旧测试工具、既有报告、L4源码或Leader权威文件。

## 预期与实际

建立B/G/M/L有界开环测量，保留全部计划ID/失败，先确认工具/后端/配置限制，再按校准冻结三档。实际完成asyncio独立后端/客户端、HTTP完整解帧与逐字节正文校验、512B/192B硬行cap流式分片、日志完整轮转、PID/线程资源采样、累计预算账本、严格冻结清单入口及离线审计。正式采集前已有27 E1、7 E2、10 diagnostic共44cell；包括首次失败，未重置额度。

E1初版完全空HTTP响应EOF被称为protocol_error。Leader批准只对rx=0且wire/body/http均空、error为missing delimiter的记录改称transport_failure；原始行/结果保持，`evidence/run/reaudit-v2/`保存逐ID归类理由和派生结果。A-G1920改88个、A-G3840改384个、S-G960改7个（含预热）；goodput分母/终点不变。新Client已一致分类。

正式E2E从scheduled到HTTP framing完成观测，close单列；正式前早期E0 smoke使用closed，不作选档。HTTP完成观测与V0.5最后recv观测边界不同，不直接做产品版本收益差值。

## 校准与控制

- A单发压G3840处generator约0.948core；双发压仍总slots128，P95 3.577→3.127ms、P99 8.976→4.763ms，超过预注册10%工具敏感门槛。不能把单发压失败归因Gateway。
- A双发压960/1920/3840候选无正文/协议损坏，生成器有效。3840两次good99.047%/99.979%、P99 4.763/3.962ms，表明波动；quota64控制good99.354%、P99 15.941ms，未证明扩大额度稳定改善。正式保持cap32。
- S主基线stream默认总4MiB，每流256KiB，实际最多16流。G240通过，480 good81.667%，960 good45.02%；B1920通过、3840漏发40.3%且generator约0.925core，为工具限制。
- S-G480仅stream4→8MiB使good81.667%→100%；双发压保持4MiB仍81.667%，支持流缓冲额度限制。8MiB控制不是产品优化，不进入主曲线；正式M/L把聚合4MiB均分。
- 上游复用off/on，A-G960双发压请求均6720、空探针0，backend accept6720→23；http P95 2.701→2.190ms，P99 7.144→2.571ms。已有连接池配置效应，只有一次对照，不称新产品性能提升。
- 采样100/500ms对照均good100%，http P95 2.664/2.625ms、P99 3.389/3.512ms；采样读取累计123.77/27.02ms。主曲线仍100ms。无网络微基准三重复：JSON序列化约2.20–2.22µs/行，序列化加页缓存写约2.66–2.67µs/行；它不包含网络/解帧/正文校验，也不是磁盘持久化吞吐。

A正式选960/1920/3840双发压，最高三有效候选，未观察有效失败上界；S选240/480/600单发压，围绕首次G失败F480。只能正式三重复后分类。当前仅已确认工具敏感/配置限制，尚无可行动产品热点，不自动进入S2。

## 文件与验证

`tests/capacity/`包含Common（硬分配/载荷）、Backend、Client、Analyze、Runtime（进程/轮转/账本/采样）、Run、Formal、Environment、ResourceSummary、Reaudit、SelfTest、Negative、InterruptTest、WriterBench、README与Draft示例清单。Builder拆解记录状态；产物均在`build-local/builder/v0.6-s1/`。

实际命令通过角色TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX执行；socket/loopback以窄权限运行，不安装依赖、不改全局/其他PID：

- `cmake -S . -B build-local/builder/v0.6-s1/gateway -G Ninja -DCMAKE_BUILD_TYPE=Release`及`cmake --build ... -j4`：通过。
- L4只读源用同角色`l4lb`构建，Release、BUILD_TESTING=OFF、L4LB_BUILD_XDP=OFF、L4LB_BUILD_XDP_LOADER=OFF：通过。
- `ctest --test-dir build-local/builder/v0.6-s1/gateway --output-on-failure`：21/21通过，41.99s，日志`evidence/ctest.log`。
- `python3 tests/capacity/SelfTest.py`：9组通过，覆盖非法framing、重复/缺ID、错误正文hash/clock/未发分类、drain goodput、硬行/文件/累计预算、L4跨片/截断、完整manifest校验、formal corruption首停并保留72计划。
- `Negative.py`：timeout保留1 deadline、bad_body保留60错误、overload保留20 HTTP拒绝+40漏发，均非达标样本；L4 smoke60/60完整成功、session/字节账相符。
- `InterruptTest.py`首次暴露fixture先wait_closed导致活跃连接清理等待、backend被KILL；首错与额度保留。修复后300=81已发interrupted+219not_started，backend81个ID、18863入站字节保留、正常exit0，全部PID回收。被中断的控制器cell明确失败。
- `Run.py --mode explore`及Leader授权显式cell：全部原始`spec/result/client/backend/resources/log`分片保留；工具与配置见每cell spec。正式前`Formal.validate`、`verify_sources`通过，工具hash在`evidence/tools-final.json`。

## 资源与边界

完整72cell含预热2,219,040请求、正式1,929,600请求，最坏证据1,930,715,136B；加约121.88MB已保留证据、15,753,216B剩余2诊断及16MiB收口池，总约2.085GB<2GiB。详见README预算表与`evidence/budget-proof.json`，启动时重新核算，不以删除历史失败挤空间。

每请求从scheduled绝对5s；测量窗口后在途最多5s，随后最多2s FD确认，均受全cell45s约束。清理TERM5s后必要时KILL/wait仅自有PID。后台日志捕获与采样线程所在控制器CPU/RSS/FD也计入；峰值为采样观测，不称连续真实峰值。tx是asyncio transport入队，不宣称失败时已送达；L4 sent来自完整日志，成功样本做字节守恒。未测包/NIC/GPU。

L4 dirty用户树未改，身份包含实际源码hash与diff；同机20逻辑CPU、未固定进程CPU quota，不称同资源扩容。perf命令不可用，未据此虚构剖析热点；小响应波动只给阶段计时/复跑/配置控制，原因未完全隔离。

## 未完成与Reviewer重点

Leader已冻结`docs/performance/V0.6/S1-manifest.json` SHA256 `81877a406c767b66fb90422a79b805f53c3c77a13869219b4f967ee5116358f4`，72正式cell正在串行执行；后续报告记录实际完成与失败。独立Reviewer必须用自有样本与构建，Builder自测不是验收。

重点核对：原始/派生归类修正范围；所有计划ID与失败分母；warmup损坏与formal首停；两worker聚合slots128；stream总额均分；实际最坏预算和独立角色账本；采样/日志开销边界；S1诊断交付与S2产品优化入口分开判断。正式之前没有阶段PASS或产品容量声明。
