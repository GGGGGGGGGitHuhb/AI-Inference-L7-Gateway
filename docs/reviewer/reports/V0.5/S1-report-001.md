# V0.5/S1 独立审查报告001

2026-10-29，**PASS**。全部阶段验收要求满足；无待返工发现或需接受的债务。交 Leader 收口，不启动 V0.5/S2。

## 范围、依据与独立性

已读取 [Approved设计](../../../leader/designs/V0.5/S1-design.md)、[审查计划](../../reviews/V0.5/S1-review.md)、[返工001](../../../leader/reworks/V0.5/S1-rework-001.md)、[Builder001](../../../builder/reports/V0.5/S1-report-001.md)、ROADMAP 的 V0.5 范围和 ARCHITECTURE 的组合拓扑/协议/配额边界。项目无专用 Reviewer GUIDE，回退全局 plan-project-docs Reviewer 模板；执行遵循 agent-execution-route，既有 C++ 语义核对遵循 personal-cpp-standards，不做无关代码调整。

Reviewer 自有 Release 构建、进程和证据位于 `build-local/reviewer/v0.5-s1/`，未复用 Builder 二进制或运行样本。Builder 完成最终矩阵后才运行独立矩阵。原生 WSL2 Linux，cwd 为本仓库；TMPDIR/TMP/TEMP 指向自有 tmp，XDG_CACHE_HOME 与 PYTHONPYCACHEPREFIX 指向自有 cache。回环测试走窄权限，无外网、依赖安装、GPU、XDP 或用户进程操作。

## 源码与范围核对

检查 L4LB 的 TcpReactor 接纳路径、TcpService 回调装配、HealthSelection、HealthState 和 TcpHealthChecker：每 TCP 连接选择并保存一次 backend；仅 Healthy 可选；Unknown 起步，2 成功开放/3 失败摘除；probe 完成后间隔 1 秒、超时 1 秒；无重试或已有连接迁移。握手无 HTTP 载荷，因此不能判断模型业务可用。

核对 Gateway README:118 和 HttpNormalization：下游每连接单请求，响应关闭；复用属于上游池。返工001纠正原设计错误假设，未通过扩展产品功能掩盖失败。Builder run-001 的 keepalive rebound 失败和原始结果保留；run-002、最终 run-003 分开保留，未拼接案例。

两仓实际构建输入在构建前保存 `gateway-inputs-before.json` / `l4lb-inputs-before.json`，构建后与 `*-after.json` 精确相同。L4LB HEAD 为 f0d41f7a5c5378c63b42ee0f9cfe8b87afe6428c，源码工作树存在用户暂存改动，输入身份包含实际文件 hash 与 diff，未冒称该 HEAD 的干净构建。检查 Gateway diff：产品源码、既有测试、CMake 与旧报告不变。新增内容仅阶段工具/配置/文档及入口状态同步。

## 实际命令与结果

以下命令均在上述显式角色环境运行，完整日志保存在自有 evidence 目录：

```bash
python3 tests/l4lb/Identity.py --source . --output build-local/reviewer/v0.5-s1/evidence/gateway-inputs-before.json
python3 tests/l4lb/Identity.py --source /home/power/projects/L4-LoadBalancer-withXDP --output build-local/reviewer/v0.5-s1/evidence/l4lb-inputs-before.json
cmake -S . -B build-local/reviewer/v0.5-s1/gateway -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-local/reviewer/v0.5-s1/gateway -j4
cmake -S /home/power/projects/L4-LoadBalancer-withXDP -B build-local/reviewer/v0.5-s1/l4lb -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DL4LB_BUILD_XDP=OFF -DL4LB_BUILD_XDP_LOADER=OFF
cmake --build build-local/reviewer/v0.5-s1/l4lb -j4
python3 tests/l4lb/DetectorTests.py
python3 tests/l4lb/RunTopology.py --gateway build-local/reviewer/v0.5-s1/gateway/ai-inference-gateway --l4lb build-local/reviewer/v0.5-s1/l4lb/bin/l4lb --output build-local/reviewer/v0.5-s1/evidence/run-001
python3 build-local/reviewer/v0.5-s1/evidence/IndependentAudit.py build-local/reviewer/v0.5-s1/evidence/run-001
python3 build-local/reviewer/v0.5-s1/evidence/IndependentNegative.py
ctest --test-dir build-local/reviewer/v0.5-s1/gateway --output-on-failure
```

- 两个 Release 产品构建成功；独立正式矩阵 **6/6 PASS，15.543s**，30 个应用请求、29 个后端收件，另有 2 次无可选 Gateway 的 TCP 拒绝探测。
- 自有 Gateway Release 既有 CTest **21/21 PASS，41.30s**；新联调和 DetectorTests 不属于这 21 项。产品未修改，不将未重跑的 Debug/ASan 或历史性能实验写成新证据。
- DetectorTests **4/4 PASS**，拒绝错误状态/正文/模型、缺失/重复/错误 ID、不完整流和将正常结束冒充截断。
- 自写 IndependentAudit 不导入 Builder 的 Checks，独立核对请求/后端集合、模型归属、实际 L4 accepted 日志与 connection 事件对应、健康转换、幸存者选择、流截断/完整终结、二进制身份和全部 PID 回收，PASS。
- 自写 IndependentNegative 使用 `/usr/bin/false` 作为明确会提前失败的 Gateway 控制：runner 非零，保存 FAIL 和实际退出 1，PID 回收；随后对同一输出目录重试被拒绝、非零退出，已有文件 hash 完全不变。该负控不冒称产品 Gateway 运行成功。

## 按审查项结论

- **RV-01 / AC-01 PASS**：实际两个产品路径运行，静态配置与运行时配置仅端口替换；两仓源身份前后相同。L4 配置启用 tcp_connect，XDP 关闭，无产品依赖耦合。
- **RV-02 / AC-02 PASS**：Unknown 拒绝、Healthy 后两 Gateway/两模型交叉覆盖、单请求关闭、半关闭完整响应、SSE 首段在门闩放行前可见；杀死承载流的 Gateway 后该流 HTTP framing 不完整且无重放，另一已建立流完整结束；摘除后新连接全走幸存者，恢复后重返两实例；全失效时 L4 仍存活并拒绝新连接，重启后成功。
- **RV-03 / AC-03 PASS**：两 Gateway 各占一个 in-flight 时，共享模型后端收到两个不同 ID；第三请求局部 503 queue_full，后端无该 ID。取消后两个 Gateway 的后续请求成功。模型 HTTP503 时两个 Gateway 仍可被 L4 选中，另一模型成功；TCP 健康与应用健康边界有实测反例。
- **RV-04 / AC-04 PASS**：6 个产品子进程全部回收，3 个预期故障 SIGKILL、3 个正常退出 0，无意外退出或强制清理。最终 L4/Gateway-0/Gateway-1 FD 均为 7，启动基线各 7；工具允许 +2 探测瞬态，采样不证明瞬时严格资源上界。每产品输出文件小于 1MiB 硬限制；120s 矩阵上限、12s 健康等待、5s socket/进程等待及逐项清理异常取证已审查。早期失败和防覆盖负控通过。
- **RV-05 PASS**：tests/l4lb/README 给出完整构建/运行命令、prlimit 前置、配置端口、产物、单进程配额及失败解释。根入口当前准确标记待独立审查，Leader 可依据本报告更新为验收完成并补 CHANGELOG/结果记录。

## 限制与收口建议

无未关闭 Major/Minor、无新增债务。验证范围仅本机可控 HTTP/SSE 组合功能；没有验证真实推理质量、生产环境、长期稳定性、严格故障切换时间或横向扩展收益。探测摘除之前的新连接仍可能失败；已有流不迁移；多个 Gateway 没有集群全局额度。S2 性能与长连接分布偏斜仍未开始。

Leader 收口时同步 README/ROADMAP/ARCHITECTURE 当前状态、CHANGELOG 与验收结果；历史报告和失败 run 保留。本报告仅写 Reviewer 文件，未修改 Builder 实现或提交 Git。
