# V0.5/S1 Builder 实现报告001

2026-10-29，Builder 实现与自测完成，待独立 Reviewer 验收。

## 范围与依据

依据 [Approved设计](../../../leader/designs/V0.5/S1-design.md)、[返工001](../../../leader/reworks/V0.5/S1-rework-001.md)、[审查计划](../../../reviewer/reviews/V0.5/S1-review.md)。新增 tests/l4lb 的运行器、可控 HTTP/SSE 后端、验收谓词、四组检测器负控、源码身份工具、三个完整配置与运行说明。两仓产品源码、既有测试和 CMake 不变；不改用户 L4LB 工作树，不运行 XDP、模型或性能实验。

## 实际结果

- Gateway 与 L4LB 独立 Release 构建成功。L4LB 当前树基于 f0d41f7a5c5378c63b42ee0f9cfe8b87afe6428c，包含用户暂存的启动/控制排版与注释修改；实际源码逐文件 hash 与 diff 已保存，不冒称干净提交。
- run-001：1组通过，routing 阶段 keepalive rebound 失败，7请求；触发返工001纠正下游复用假设，证据保留。
- run-002：6组全部通过，30个应用请求、29个后端收件，15.408s。随后将轮询请求的模型排列改为每个 Gateway 都覆盖两模型，完善构造中途失败和逐项清理异常路径。
- 最终 run-003：6组全部通过，30请求、29后端收件，15.542s；额外两次无健康后端的 TCP 拒绝探测不计应用请求数。所有 ID 唯一，无重放；准入拒绝 ID 不到后端。Unknown/单Gateway摘除恢复/全部故障恢复、SSE首段门闩/取消/截断/幸存流、单进程配额/TCP与应用健康边界均通过。
- DetectorTests 四组通过，覆盖错误状态/正文/模型、缺失或重复 ID、不完整流及把正常结束或超时冒充截断。
- 既有 Gateway Release CTest **21/21 PASS，43.10s**。新联调和检测器不在21项内，单独运行。无产品变化，不重复历史全量 Debug/ASan 或性能实验。
- 构建完成后记录输入并于测试后再次快照，两仓源身份逐字节相同；本轮不是构建前快照，独立 Reviewer 应保留构建前后身份。原源码/构建定义未修改，Git diff check通过。

## 命令、环境与证据

原生 WSL2，cwd /home/power/projects/AI-Inference-L7-Gateway，分支 codex/v0.5-s1-l4lb-integration，起点31e7e78。角色根 build-local/builder/v0.5-s1，TMPDIR/TMP/TEMP=tmp，XDG_CACHE_HOME=cache，PYTHONPYCACHEPREFIX=cache/pycache。已知回环测试走窄权限，未下载、改系统或其他仓库。

```bash
cmake -S . -B build-local/builder/v0.5-s1/gateway -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-local/builder/v0.5-s1/gateway -j4
cmake -S /home/power/projects/L4-LoadBalancer-withXDP -B build-local/builder/v0.5-s1/l4lb -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DL4LB_BUILD_XDP=OFF -DL4LB_BUILD_XDP_LOADER=OFF
cmake --build build-local/builder/v0.5-s1/l4lb -j4
python3 tests/l4lb/DetectorTests.py
ctest --test-dir build-local/builder/v0.5-s1/gateway --output-on-failure
python3 tests/l4lb/RunTopology.py --gateway build-local/builder/v0.5-s1/gateway/ai-inference-gateway --l4lb build-local/builder/v0.5-s1/l4lb/bin/l4lb --output build-local/builder/v0.5-s1/evidence/run-003
```

evidence 下 configure/build/ctest/detectors 日志，gateway-inputs/l4lb-inputs 及 after 文件，run-001/002/003 分开保留。每 run 内有二进制/工具身份、实际配置、原始产品日志、逐事件、应用尝试、后端收件、进程退出和汇总。

## 限制与交接

Gateway 下游每连接单请求关闭；上游连接池复用不等于客户端 Keep-Alive。L4 握手健康无法识别 HTTP503；两 Gateway 的额度独立，不提供全局后端容量。故障中已有流不能迁移；摘除前的连接仍可能失败，不承诺无损切换。FD 最终允许较启动值+2以容纳健康探测瞬态，不将采样解释为严格资源上界。本机模拟功能矩阵不证明真实推理兼容、长期稳定性或扩容收益。

Reviewer 应独立构建并运行完整矩阵，审计30/29收件集合和失败流，另做独立反例/早期失败取证检查。阶段尚待独立结论；无已知产品修改需求。
