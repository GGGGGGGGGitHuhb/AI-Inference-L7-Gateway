# V0.5/S1：L4LB 组合拓扑与故障

状态：Approved。2026-10-29，依据用户“开始 V0.5/S1，先核对 L4LB 的 TCP 路径和健康机制，再推进联调”和既有技术决策委托，由协调者采纳既定路线范围内的基线。决策包见 [Leader001](../../reports/V0.5/S1-report-001.md)。

## 目标与源码核对

V0.4 已由独立 Reviewer PASS、Leader006 收口，实际本地提交为 31e7e78，启动时 Gateway 工作区干净。本阶段打通 `client → l4lb → gateway-0/1 → model-a/model-b`，交付可运行配置、故障矩阵和职责边界。

L4LB 工作树基于 f0d41f7a5c5378c63b42ee0f9cfe8b87afe6428c，存在用户暂存改动；不能仅以该提交标识实际构建。只读使用当前工作树，在 Gateway 的 build-local 内构建并保存构建输入逐文件 SHA256、工作树 diff 和二进制 SHA256。不得修改、清理或提交 L4LB 仓库。

- `src/control/TcpService.cpp` 将 HealthSelection 绑定到 TcpReactor；`src/net/TcpReactor.cpp::acceptClientSessions` 每个新连接选择一次 backend，连接一生绑定，不按 HTTP 请求分配，不重试、不迁移。
- `src/control/HealthSelection.cpp` 仅选择 Healthy；空集合立即关闭新连接，无 fallback。
- `src/health/HealthState.h` 初始 Unknown；连续 2 成功成为 Healthy，连续 3 失败成为 Unhealthy。`TcpHealthChecker.h` 默认探测间隔/超时各 1000ms，间隔从完成开始计算，不能宣称严格 3 秒摘除。
- TCP probe 只握手、不发 HTTP；健康变化不会关闭已有绑定。Gateway 负责模型路由、HTTP/SSE、上游被动健康、单进程准入。
- 用户态 TCP 路径不是 XDP；不保留客户端源地址，不调用 l4lb-xdp。

## 范围、职责与限制

REQ-01：只新增 tests/l4lb 下标准库 Python 故障工具与完整配置、阶段文档；可同步入口和当前状态。两仓产品源码、既有测试与构建定义、旧报告原字节保持。不合并仓库、不启动 Server、不改 TCP/XDP/健康策略、不做 S2 性能测量、无模型下载或新依赖。

REQ-02：使用真实产品 ai-inference-gateway 和 l4lb，两个 Gateway 都路由 model-a/model-b 到相同的两台可控 HTTP 后端。backend 响应回显唯一请求 ID 和模型，保留逐请求记录；L4 实际 accepted 日志标识所选 Gateway，禁止根据轮询序号猜测归属。静态例子采用 loopback，运行时分配空闲端口，保存实际配置；端口冲突必须失败而非杀其他进程。

REQ-03：冻结功能矩阵：启动 Unknown 拒绝；Healthy 后新连接覆盖两个 Gateway 和两种模型；同 TCP 连续请求保持 Gateway 绑定且可切换模型；完整请求半关闭仍收到完整响应；流式首段在后端放行前可见；客户端取消后后续请求正常；杀死承载流的 Gateway 产生截断且不重放，另一 Gateway 的已建立流继续完成；观察 Unhealthy 后新连接只走存活 Gateway；同端口重启并观察 Healthy 后恢复分配；全部 Gateway 故障时拒绝且 L4 进程存活，恢复后重新成功。

REQ-04：每 Gateway 配置 max_inflight=1、每 backend=1、queue_count=0。在两个 Gateway 各保持一个流时，共享模型后端实际收到两请求；同 Gateway 新请求被拒绝且不派发后端。由此说明配额是单进程的，不能将两实例视为一个全局配额。额外验证后端 HTTP 503 时 Gateway 端口仍可握手、L4 仍 Healthy、另一个模型仍成功，不能把 TCP 健康称作推理可用。

REQ-05：保留命令、源码/二进制身份、实际配置、逐 case 与请求 ID、后端收件、L4 健康转换、PID/退出码和最终结果。检测失败必须非零并保留证据。socket deadline 至多 5s，健康等待至多 12s，全矩阵 120s；自有子进程 TERM 一次、5s 后 KILL/wait，故障注入的 SIGKILL 单列预期。标准输出/错误每文件硬上限 1MiB，测试结果/后端记录按固定请求数有界，输出使用新目录，禁止覆盖历史。

## 执行路线与验收

原生 WSL2 Linux，cwd /home/power/projects/AI-Inference-L7-Gateway。角色路径 build-local/ROLE/v0.5-s1/{tmp,cache,evidence,gateway,l4lb}，TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX 显式指向自有目录。无需外网、安装、特权网络或 GPU；loopback 测试若执行限制阻止则用窄权限运行。L4LB 只读源路径 /home/power/projects/L4-LoadBalancer-withXDP；禁止写入其 build 或 .git。

M1 固定上述核对与设计；M2 Builder 实现并运行矩阵、检测器负控、Gateway Release 既有完整 CTest；M3 按项目独立审查规则交独立 Reviewer 代理，在自有构建和证据目录重新验证矩阵、负控与源码身份；M4 Leader 依据结果收口。产品未改，不重复历史性能实验，不强制重跑所有历史配置组合。

- AC-01 / REQ-01/02：保护文件不变；身份可核对；配置真实可加载；产品路径无替身。
- AC-02 / REQ-03：全部生命周期案例满足期望，正文及 HTTP framing 完整；故障流必须明确失败且无重复 backend ID。
- AC-03 / REQ-04：局部准入与 L4 健康边界均有实测反例，不声称集群全局容量或应用健康。
- AC-04 / REQ-05：全矩阵 PASS、进程回收、零意外退出、检测器能拒绝错误内容/重复或缺失 ID/不完整流；既有 Gateway Release CTest 全部通过。失败不得标完成；独立审查必须有自有运行证据。

新 CLI 由 Builder 交付：`python3 tests/l4lb/RunTopology.py --gateway <binary> --l4lb <binary> --output <new-directory>`；具体可复制构建与运行命令见待交付 tests/l4lb/README.md。联调只证明本机模拟故障下功能语义，不证明生产部署、GPU 收益、横向扩展或长期稳定性。
