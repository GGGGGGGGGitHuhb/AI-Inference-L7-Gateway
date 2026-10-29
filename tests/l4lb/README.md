# V0.5/S1：L4LB 与两个 Gateway 联调

本目录验证 `client → 用户态 l4lb TCP → gateway-0/1 → model-a/model-b`。使用真实产品程序和 Python 标准库可控 HTTP/SSE 后端，无 GPU、模型下载、root 网络配置或外网依赖。需要 Linux、CMake、Ninja、C++20、Python3 和 util-linux 的 `prlimit`。

## 一次运行

在 Gateway 仓库根目录执行，`L4_SOURCE` 指向本机 L4LB 源码目录。不会修改该源码目录，不依赖其现成二进制；XDP 保持关闭。

```bash
L4_SOURCE=/home/power/projects/L4-LoadBalancer-withXDP
STAGE_ROOT="$PWD/build-local/manual/v0.5-s1"
mkdir -p "$STAGE_ROOT/tmp" "$STAGE_ROOT/cache" "$STAGE_ROOT/evidence"
export TMPDIR="$STAGE_ROOT/tmp" TMP="$STAGE_ROOT/tmp" TEMP="$STAGE_ROOT/tmp"
export XDG_CACHE_HOME="$STAGE_ROOT/cache" PYTHONPYCACHEPREFIX="$STAGE_ROOT/cache/pycache"
python3 tests/l4lb/Identity.py --source . --output "$STAGE_ROOT/evidence/gateway-inputs.json"
python3 tests/l4lb/Identity.py --source "$L4_SOURCE" --output "$STAGE_ROOT/evidence/l4lb-inputs.json"
cmake -S . -B "$STAGE_ROOT/gateway" -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build "$STAGE_ROOT/gateway" -j4
cmake -S "$L4_SOURCE" -B "$STAGE_ROOT/l4lb" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=OFF -DL4LB_BUILD_XDP=OFF -DL4LB_BUILD_XDP_LOADER=OFF
cmake --build "$STAGE_ROOT/l4lb" -j4
python3 tests/l4lb/DetectorTests.py
python3 tests/l4lb/RunTopology.py \
  --gateway "$STAGE_ROOT/gateway/ai-inference-gateway" \
  --l4lb "$STAGE_ROOT/l4lb/bin/l4lb" \
  --output "$STAGE_ROOT/evidence/run-001"
ctest --test-dir "$STAGE_ROOT/gateway" --output-on-failure
```

输出目录必须不存在；重复执行时选择新目录，身份文件也不覆盖。脚本会分配回环端口，生成实际配置，启动自有进程；杀死/重启的仅是自己创建的 Gateway。正常约十几秒，全矩阵上限120秒，健康等待12秒、socket5秒；进程退出等待5秒，超时强杀并记失败。每个产品 stdout/stderr 由 prlimit 限制1MiB。不得把本工具指向其他人的运行进程。

结果在 result.json；events.jsonl 保存案例、实际 L4 session→Gateway、请求及健康转换；attempts.json 与 backend-records.json 核对30次应用请求，其中29次到达后端，1次准入拒绝。另有 Unknown 和全部不可选两次纯 TCP 拒绝探测。processes.json 列出全部自有 PID、预期故障 SIGKILL 与实际退出码；identity.json 保存实际产品和工具 SHA256。失败非零退出并保留证据，禁止删除失败记录后只报告成功。

## 可手动部署的配置

configs/l4lb.conf 监听127.0.0.1:8080，TCP backends 是18080/18081两个 Gateway；gateway-0.json 与 gateway-1.json 仅监听端口不同，均把 model-a/model-b 映射到19080/19081。

先启动匹配 `/v1/chat/completions` 的两个推理后端，再分别启动两个 `ai-inference-gateway --config tests/l4lb/configs/gateway-N.json`，最后 `l4lb --run tests/l4lb/configs/l4lb.conf`。实际模型名、后端地址和端口应一起修改；这些是故障实验配置，max_inflight=1、禁排队，不是生产推荐容量。自动 runner 的模拟后端会自行启动和清理，静态示例本身不会启动后端。

## 已核对的语义与矩阵

- 初始 Unknown 不可选，连续2次成功开放、连续3次失败摘除。每次完成后间隔1秒，探测超时1秒；就绪日志不代表已 Healthy，不能承诺严格3秒故障切换。
- L4 每新 TCP 连接选择一次 Gateway，已建立长流固定绑定。Gateway **下游每连接单请求并关闭**；连接池复用在上游。第一版测试误假定下游 Keep-Alive，已按返工001纠正并保留失败记录。
- 6个新连接验证轮询及两种模型在两个 Gateway 的交叉覆盖；另验证明确关闭语义、完整请求半关闭后仍可收完整响应。
- 两个 Gateway 各持有一条 SSE，首段在后端门闩放行前到达客户端；第三请求局部拒绝、不派发后端。客户端取消后两个 Gateway 均能处理后续请求。
- 杀死持有 SSE 的一个 Gateway：该流不完整且不重放，另一个流完整完成。观察摘除后，新连接只到幸存者；重启同端口、观察恢复后再次分配到两个 Gateway。
- 两个 Gateway 全失效时，L4 拒绝新连接但继续运行；重启恢复。TCP probe 只握手；模型返回 HTTP503、另一模型正常时，Gateway 端口仍 Healthy。

每个 Gateway 的额度独立。两个实例各允许1个请求时，共享模型后端可同时收到2个；没有集群全局配额，也不会把超额请求自动转移到另一 Gateway。L4 不解析 HTTP、不保留客户端源地址、不自动重试、不迁移故障流。本阶段不证明 XDP TCP、真实模型质量、吞吐提升、GPU 利用率、横向扩展或长期稳定性；额外成本与长连接分布偏斜属于 V0.5/S2。
