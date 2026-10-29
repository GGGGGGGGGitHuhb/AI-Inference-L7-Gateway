# V0.5/S2 Builder 实现报告001

2026-10-29，实现和自测完成，待独立Reviewer验收。依据[Approved设计](../../../leader/designs/V0.5/S2-design.md)、[审查计划](../../../reviewer/reviews/V0.5/S2-review.md)及Leader001。未改产品、CMake、旧测试、S1历史或L4LB用户工作树。

## 交付与实现

新增 tests/l4lb_cost：独立后端进程、开环客户端、原始字节/CPU/时钟记录、18cell运行器、完整性与配对分析、门闩长流偏斜案例、6组负控及运行说明。复用S1 Owned/Identity/Matrix和integration WireResponse，未复制产品代理逻辑。

D单Gateway32额度，M/L双Gateway各16，三者共享同一类型独立后端、无上下游连接复用；入口64、池/每backend配额同步，后端NODELAY固定on。每cell12预热+240正式、60req/s，JSON1024B/SSE16KiB各三重复，固定轮换顺序。成本仅描述同机低负载观测，不推断容量。

正式前审查建议已落实：first_wire与first_body分开；CPU真实window/tick量化；L4预热session排除；网络每逻辑边只算一次；session ID/port/正常关闭核对；全cell30s活动deadline；短写每次重算请求绝对剩余期限；批次中断后收齐已提交任务实际结果，只有未提交才记not_started；累计证据预算保留旧cell占用，逐文件caps证明16MiB cell/4MiB收口预留足够。

## 测试与结果

- 两仓独立Release构建完成，构建前/测试后输入manifest完全一致，记录实际L4 dirty diff和文件hash，不把f0d41f7当作干净源码。
- DetectorTests六组通过：计划4536唯一ID、请求失败/缺重/时钟/hash反例、原始读写字节、L4字节/预热/session/后端收件破坏、分位阈值、累计预算边界拒绝。
- 既有Gateway Release CTest **21/21 PASS，42.48s**；新工具单独执行，不计入21项。不重跑未受影响的历史性能、Debug/ASan或S1故障矩阵。
- run-001：18/18、4536成功、偏斜8请求通过，92.815s；quality_limited=[]。随后补发送短写绝对期限、细化结构化文件预算与失败未开始汇总；无负载参数变化。
- 最终run-002：**18/18、4536成功、not_started=0，92.793s**，另8个偏斜请求通过。全部质量标记未触发；最大dispatch lag p95=0.922ms，client/backend最大平均CPU约0.109core。57个自有产品/后端进程全部正常exit0、wait回收，无强制清理。summary写入前证据4,631,853bytes。
- 两轮完整分开保留，以最终工具run-002作为主证据，不择优样本、不拼接。独立Reviewer仍须自有矩阵/审计/负控。

最终Builder的L−M配对（repeat0/1/2）：

| 工作负载 | E2E p95差值ms | proxy CPU每成功请求差值ms | 多一跳payload字节/240请求 |
| --- | --- | --- | --- |
| A JSON | +1.794 / +1.517 / +1.074 | +0.375 / +0.417 / +0.292 | 348000 / 348000 / 348000 |
| B SSE | −1.240 / −0.176 / +0.492 | +0.417 / +0.417 / +0.542 | 4063920 / 4063920 / 4063920 |

CPU时钟粒度10ms，部分单Gateway窗口<5ticks，0.001ms排版不表示测量精度；流式正负差值不能包装为L4加速。D↔M的进程数也变了，不能把差异全部归因于L4；所有配对原值见comparisons.json。

## 命令与证据

原生WSL，cwd本仓库，分支codex/v0.5-s2-cost-boundaries，起点92fcf3d。角色根build-local/builder/v0.5-s2；TMPDIR/TMP/TEMP=tmp，XDG_CACHE_HOME=cache，PYTHONPYCACHEPREFIX=cache/pycache。回环测试走窄权限，无外网或其他用户进程操作。

```bash
cmake -S . -B build-local/builder/v0.5-s2/gateway -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-local/builder/v0.5-s2/gateway -j4
cmake -S /home/power/projects/L4-LoadBalancer-withXDP -B build-local/builder/v0.5-s2/l4lb -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DL4LB_BUILD_XDP=OFF -DL4LB_BUILD_XDP_LOADER=OFF
cmake --build build-local/builder/v0.5-s2/l4lb -j4
python3 tests/l4lb_cost/DetectorTests.py
ctest --test-dir build-local/builder/v0.5-s2/gateway --output-on-failure
python3 tests/l4lb_cost/RunCosts.py --gateway build-local/builder/v0.5-s2/gateway/ai-inference-gateway --l4lb build-local/builder/v0.5-s2/l4lb/bin/l4lb --output build-local/builder/v0.5-s2/evidence/run-002
```

evidence内保留configure/build/ctest/detector日志、gateway/l4lb before/after身份、两轮独立输出；每cell保存warm/requests/backend/samples/boundary/processes/原始日志/result，run级保存计划/身份/全部配对/未开始ID与summary。源与旧文件保护由Git核对，运行产物不入库。

## 限制和交接

网络是正返回TCP用户态载荷字节，未测TCP/IP头、握手/ACK/重传、健康probe的包成本；L增加一条逻辑传输边。CPU含发压/采样协调者和后端，低ticks有量化误差，采样峰值非瞬时上界。全部60req/s无质量标记也不证明饱和容量、长期公平、GPU收益或生产扩容。

偏斜实际8连接4:4、在途4:0，按L4日志与门闩状态确认，释放后全部成功；这是刻意到达顺序反例。Reviewer需独立复算时钟、CPU、字节、分位、每重复差值，执行早退/防覆盖/中途批次负控，并检查完整分母和资源回收。阶段尚待独立结论。
