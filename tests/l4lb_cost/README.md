# V0.5/S2：拓扑成本与长流边界

比较D（直连单Gateway）、M（客户端轮询直连两个Gateway）、L（L4LB TCP接两个Gateway）。三条路径共用相同独立合成后端、请求与总准入额度32；D为32，M/L各16。下游每请求新TCP，上游max_idle=0、后端Connection close，无连接复用。产品、S1工具与CMake均不修改。

## 复现

在Gateway仓库根目录运行。要求Linux、Python3标准库、util-linux/prlimit、CMake/Ninja/C++20，无外网或模型下载。L4源码只读，构建产物写本仓库角色目录；实际源可能有用户未提交改动，用身份快照描述，不能只引用HEAD。

```bash
L4_SOURCE=/home/power/projects/L4-LoadBalancer-withXDP
STAGE_ROOT="$PWD/build-local/manual/v0.5-s2"
mkdir -p "$STAGE_ROOT/tmp" "$STAGE_ROOT/cache" "$STAGE_ROOT/evidence"
export TMPDIR="$STAGE_ROOT/tmp" TMP="$STAGE_ROOT/tmp" TEMP="$STAGE_ROOT/tmp"
export XDG_CACHE_HOME="$STAGE_ROOT/cache" PYTHONPYCACHEPREFIX="$STAGE_ROOT/cache/pycache"
python3 tests/l4lb/Identity.py --source . --output "$STAGE_ROOT/evidence/gateway-before.json"
python3 tests/l4lb/Identity.py --source "$L4_SOURCE" --output "$STAGE_ROOT/evidence/l4lb-before.json"
cmake -S . -B "$STAGE_ROOT/gateway" -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build "$STAGE_ROOT/gateway" -j4
cmake -S "$L4_SOURCE" -B "$STAGE_ROOT/l4lb" -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TESTING=OFF -DL4LB_BUILD_XDP=OFF -DL4LB_BUILD_XDP_LOADER=OFF
cmake --build "$STAGE_ROOT/l4lb" -j4
python3 tests/l4lb_cost/DetectorTests.py
python3 tests/l4lb_cost/RunCosts.py \
  --gateway "$STAGE_ROOT/gateway/ai-inference-gateway" \
  --l4lb "$STAGE_ROOT/l4lb/bin/l4lb" \
  --output "$STAGE_ROOT/evidence/run-001"
ctest --test-dir "$STAGE_ROOT/gateway" --output-on-failure
python3 tests/l4lb/Identity.py --source . --output "$STAGE_ROOT/evidence/gateway-after.json"
python3 tests/l4lb/Identity.py --source "$L4_SOURCE" --output "$STAGE_ROOT/evidence/l4lb-after.json"
cmp "$STAGE_ROOT/evidence/gateway-before.json" "$STAGE_ROOT/evidence/gateway-after.json"
cmp "$STAGE_ROOT/evidence/l4lb-before.json" "$STAGE_ROOT/evidence/l4lb-after.json"
```

所有输出采用不存在的新路径，不覆盖历史。通常约90秒完成固定矩阵与偏斜；600秒全run、每cell30秒活动期限，请求绝对5秒，失败清理另有有限grace。只停止自有PID；后台服务没有安装/常驻。正式测量时不要同时运行其他基准或构建。

## 固定矩阵与产物

- 18cell：1024byte JSON（A）、16KiB SSE（B：16段、每段间sleep目标2ms）各三重复×三路径。每重复顺序轮换DML/MLD/LDM；每cell12预热+240正式，60req/s开环、4秒计划窗口、32槽。4536个计划请求完整保留；晚于50ms或无槽不补发。
- 合成后端独立进程、所有路径同样TCP_NODELAY=on，产品默认保持；SSE时间包含Python sleep和同机调度开销。这个设置不代表真实推理后端。
- plan.json固定cell和所有ID；identity.json固定二进制和新工具SHA256、CPU affinity/CLK_TCK。每cell保存实际配置、stdout/stderr、warm.json、requests.json、backend.json、samples.json、boundary.json、processes.json和result.json。
- summary.json记录整体结果/未开始数/质量标记，comparisons.json保留每重复M−D、L−M配对差值。每cell前检查已保留文件总量+16MiB预留+4MiB收口不超过64MiB，不释放旧cell占用。每产品日志1MiB硬限；structured文件分别封顶，最大单文件2MiB。每cell最坏直接日志8MiB+backend1MiB+其他结构化文件不足4MiB，低于16MiB预留。
- 不发生故障时每cell252次后端accepts，与全部ID一一对应，证明本实验没有上游复用。非200、正文/收件/字节不一致均失败；失败记录不从统计分母删除。not-started-ids.json保存尚未建立cell记录的未来ID；当前cell内未提交请求保留在requests/warm中。已经提交的任务等待其有限期限并保留实际结果，不能伪记未开始。

## 指标解释

TTFB=首次非空recv（可能仅HTTP头）−scheduled；first_body单列，不称模型token TTFT。E2E以完整Content-Length/终止chunk的观测时刻减scheduled；关闭/EOF校验耗时另列。p50至少20样本、p95至少100、p99至少1000；本矩阵不报p99。完成吞吐用最后关闭−计划起点，不把4秒计划窗口内未完成者删掉。

CPU是/proc实际ticks差与实测window。窗口涵盖计划正式请求前快照至正式终态和连接排空，排除预热与进程启动/停止；含全部Gateway、L4、后端和协调/发压进程。报告每角色CPU秒、core fraction、每成功请求CPU与tick精度；小于5ticks标低分辨率，0tick不能解释为免费。RSS/FD峰值是100ms目标采样观察，不是严格瞬时上界。

网络量是**用户态TCP正返回载荷字节**，包括HTTP头与chunk framing；每条逻辑边只计一次：D/M是client tx+rx及backend counted read/write，L另加L4→Gateway关闭session的sent_c2b+sent_b2c。正式与预热session分开；L4正式总字节须与client正式总字节相等。不是物理NIC字节，不含TCP/IP头、握手/ACK/重传；TCP健康probe无应用载荷，其CPU仍计入。每路径正式240条客户端连接与240条上游连接；L另有240条L4→Gateway连接，健康探测连接另计且本阶段不报告其包级成本。

dispatch lag p95>5ms或client/backend CPU>.85core触发quality_limited。所有有效和受限重复都保留；M↔L用于观察增加L4层的差异，D↔M还改变Gateway进程数。低负载无质量标记也不能证明无所有瓶颈、生产容量或因果提升；同机共享资源、3重复和固定rate只支持有限描述性比较。

## 长流偏斜

单独skew目录复用S1真实产品及门闩fixture，两个Gateway额度各8。依L4实际accepted日志确认8连接，4长流保持、4短请求完成，连接计数4:4而在途4:0；放行后所有流完整完成。它是刻意构造的到达顺序反例，证明连接数轮询不等于工作量均衡，不是随机生产流量预测，也不是扩容收益实验。
