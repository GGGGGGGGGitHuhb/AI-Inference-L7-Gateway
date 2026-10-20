# V0.3/S3 显式MVP综合验收

此目录只提供测试host、固定28条真实/29条模拟驱动与短检测器。产品来自同一个gateway_runtime；没有Server/L4LB依赖，不下载模型，不启动旧长soak或P1性能矩阵。权威是S3 Approved设计叠加rework001：M2必须queue_bytes_exceeded，M4严格唯一8条。

## 构建与离线短检测器

仓库根目录，原生WSL/Bash。Reviewer把路径中的builder换为reviewer，禁止复用可变结果/端口/进程。

```bash
mkdir -p build-local/builder/v0.3-s3/{tmp,cache,evidence}
export TMPDIR="$PWD/build-local/builder/v0.3-s3/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.3-s3/cache"
export PYTHONPYCACHEPREFIX="$XDG_CACHE_HOME/pycache"
cmake --preset release -B build-local/builder/v0.3-s3/release
cmake --build build-local/builder/v0.3-s3/release -j4
ctest --test-dir build-local/builder/v0.3-s3/release --output-on-failure
```

debug/asan同理；MvpDetectors是普通CTest短项，不启动模型。测试socket/LSan需本机允许的宿主权限；不能关闭sanitizer冒充通过。保留11类负控子进程证据可执行：

```bash
python3 tests/mvp/DetectorTests.py build-local/builder/v0.3-s3/release/MvpRuntimeHost \
  --output build-local/builder/v0.3-s3/evidence/detector-proof-001
```

## 固定显式矩阵

每个输出目录必须不存在；失败目录不覆盖、不删除。除修正明确错误外不重复运行或补样本，不改变token数/期限/分母来通过。

```bash
python3 tests/mvp/RunMvp.py --mode simulated \
  --host build-local/builder/v0.3-s3/release/MvpRuntimeHost \
  --gateway build-local/builder/v0.3-s3/release/ai-inference-gateway \
  --output build-local/builder/v0.3-s3/evidence/simulated-001
python3 tests/mvp/RunMvp.py --mode real \
  --host build-local/builder/v0.3-s3/release/MvpRuntimeHost \
  --gateway build-local/builder/v0.3-s3/release/ai-inference-gateway \
  --assets build-local/integration/v0.2-s3 \
  --output build-local/builder/v0.3-s3/evidence/real-001
```

真实资产只能复用旧固定b7481与Qwen2.5-0.5B Q4_K_M；缺失/错误身份即失败，不下载替代。驱动核对archive/model/server与解压库/许可证，启动自有双CPU进程，各2线程/ctx2048/parallel1/GPU0；共享CPU/内存，不能当独占双实例或GPU调度收益。正式ai-inference-gateway由R0单独跑非流/流冒烟，不只测host。单请求155s、启动每实例120s、整体1800s；模拟整体120s、单组15s，门闩不超过5s。

`plan.json`给出预分配ID。各`R*-*.json`/`M*-*.json`是唯一attempt finally记录，保留状态、异常、部分正文、发送完成与首content/结束时刻；`joined-attempts.json`关联host稳定Session ID/实际端口；`queue-waits.json`分开成功派发等待与取消/超时；`summary.json`按组/预热等cohort分开分母。不能只看summary，独立审查应重算所有原始文件。

host在事件清理前后收集状态并至少每100ms写账本，1s采样RSS/FD，最大值不替代产品/确定性瞬时限额证据。资源基线与各排空点在drains.jsonl，正式attempt原始正文严格保留。M5为进程退出，资源以最终零账和自有PID回收为证；其余组要求live FD回启动基线、RSS不超过预热B+32MiB。L1取消要求本地账/资源≤5s归零；L2记录取消前上游socket fd inode及关闭后的消失；L3仅记录真实后端slot与恢复结果，不宣称GPU或所有计算已停止。

TTFT=客户端发送完成至首非空content；E2E=发送完成至合法HTTP结束。非流无TTFT；错误/取消不纳入成功延迟；未排队不补0。模拟正常SSE必须精确长度/hash一致，坏chunk必须保持截断。小模型慢读未触高水时如实报告；R2没有真实排队则失败，模拟覆盖不能替代。没有p99、吞吐、SLO、长期无饥饿或性能提升结论。

## Builder002：运行期间存储预算更正

Reviewer001 F-001 指出原128MiB只在末尾合计，原成功结果不能证明运行期有界。现在 RunBudget 在创建plan/manifest之前启用：96MiB直接路径预留池＋28MiB Python累计写入池＋4MiB错误保留池，严格总和128MiB；不是三个可各用128MiB的独立限制。

每个子进程stdout/stderr合并为一个4MiB文件；host还写state、state.partial、history三个4MiB路径，分别预留并计入原子替换同时存在的峰值。真实最多1host+3其他进程=7路径/28MiB；模拟5host=20路径/80MiB，均在96MiB池内。启动前必须完成全部路径预留，prlimit设置RLIMIT_FSIZE=4MiB硬限且禁止core；达到硬限10ms目标监视即失败、停止自有进程，不等矩阵完成。最终成功前必须全部子进程退出且再次核验硬限。

Python所有save/append/attempt写入均在同一锁内先按UTF-8序列化字节计费；覆盖不退账，保守累计覆盖多线程/原子替换和失败写入。常规池耗尽停止run；已发生attempt转入错误保留池，记录ID、时刻、状态、字节数/hash、错误及有界正文前缀，明确failure/evidence_truncated，不伪装完整响应。最多29条attempt，单回退记录正文/错误各4096字符，其余固定字段；4MiB还容纳process start/reaped、cleanup错误和最终FAIL。错误池本身也锁内硬计费。默认阈值不提供CLI覆盖。

小预算独立负控（输出目录必须不存在）：

```bash
python3 tests/mvp/BudgetTests.py \
  --host build-local/builder/v0.3-s3/release/MvpRuntimeHost \
  --output build-local/builder/v0.3-s3/evidence/budget-003
```

七个子进程退出2：多个单项未超但累计耗尽、并发写入、原子覆盖、真实子进程写穿硬限、多子进程多文件预留耗尽、有界attempt回退、真实HTTP attempt finally超限；另正常host短控退出0。测试审计置于各受限run目录外，不把审计输出漏算为run内文件。
