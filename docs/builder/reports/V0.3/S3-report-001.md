# V0.3/S3 Builder 实现报告001

2026-10-20，Hephaestus。初次实现和自检完成，Ready for independent review。累计返工 **1/2**（Leader权威包纠正已占1轮），不重置；没有Builder交付后返工。未提交、未推送；独立验收与Leader收口尚未完成。

## 依据、范围与文件

分支codex/v0.3-s3-mvp-acceptance，起点d89de57eb6be0106bccd24432b2559d342ed8b79。依据[Approved设计](../../../leader/designs/V0.3/S3-design.md)、[审查计划](../../../reviewer/reviews/V0.3/S3-review.md)、Leader001，叠加[rework001](../../../leader/reworks/V0.3/S3-rework-001.md)与Leader002。五份精确SHA见E/authority-sha256.json，均与协调者授权值一致：M2精确queue_bytes_exceeded，M4严格8条。旧阶段报告/权威保持字节不变。

沿agent-execution-route原生WSL路线、personal-cpp-standards规则及正反例；无项目Builder指南，回退plan-project-docs Builder模板。初始Leader根文档改动保留，不替代Leader状态收口。E=`build-local/builder/v0.3-s3/evidence`。

只修改CMakeLists.txt，新增tests/mvp的RuntimeHost.cpp、Common.py、Attempts.py、Simulated.py、Real.py、RunMvp.py、DetectorTests.py、README.md，以及本报告、[拆解](../../breakdowns/V0.3/S3-breakdown.md)、[来源说明](../../../references/V0.3-S3-changes.md)、[实测结果](../../../acceptance/V0.3/S3-results.md)。每个工具职责见来源说明。没有产品源码、旧测试断言/工具、第三方、旧配置变化；没有下载或新增依赖，没有性能优化、旧长soak/P1矩阵或未来阶段实现。

测试host链接同一gateway_runtime，通过既有friend只读观察Session/Router/Admission及资源；cleanup回调调用原runtime清理后记录，不修改产品状态。最多128条Session历史、96MiB host日志、128MiB完整run。客户端唯一attempt finally落盘、固定单调时钟与截止时间；错误保留部分正文，正常模拟SSE严格长度/hash，真实流检查content/finish/DONE与合法HTTP终态。cleanup_all逐项回收，即使某项失败仍执行其余，并使最终失败非零。

## 路线、实际命令与结果

cwd=/home/power/projects/AI-Inference-L7-Gateway，/bin/bash login=false；独立tmp/cache及三套构建目录。实际构建、Python、测试均显式：

```bash
export TMPDIR="$PWD/build-local/builder/v0.3-s3/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/build-local/builder/v0.3-s3/cache"
export PYTHONPYCACHEPREFIX="$XDG_CACHE_HOME/pycache"
cmake --preset debug -B build-local/builder/v0.3-s3/debug
cmake --build build-local/builder/v0.3-s3/debug -j4
ctest --test-dir build-local/builder/v0.3-s3/debug --output-on-failure
```

release/asan逐套替换实际执行。socket/LSan首次走精准宿主权限，不关闭任何检测。显式矩阵及持久短负控命令逐字见[操作说明](../../../../tests/mvp/README.md)，正式run目录为real-001/simulated-001，各一次；早期短检测器一次，后为持久保存11类证明又执行detector-proof-001，未重复正式矩阵凑结果。

| 实跑 | 结果/exit | 原始证据 |
| --- | --- | --- |
| 三套最终configure/build | 各0 | E/configure-{debug,release,asan}-final.log、build-*-final.log |
| Debug完整CTest | 20/20，34.57s，0 | E/ctest-debug-final.log、LastTest-debug-final.log |
| Release完整CTest | 20/20，32.42s，0 | E/ctest-release-final.log、LastTest-release-final.log |
| ASan/UBSan/LSan完整CTest | 20/20，47.84s，0 | E/ctest-asan-final.log、LastTest-asan-final.log |
| 持久短负控 | 11类子进程均按预期非零，驱动0；host idle/stop通过 | E/detectors-002.log、detector-proof-001 |
| 模拟正式一次 | 29条，2.620857s，0 | E/simulated-001/result.json及全部原始文件 |
| 真实正式一次 | 28条，25.607183s，0 | E/real-001/result.json及全部原始文件 |
| 资产动态库/版本 | ldd无not found；7481(cc0a04343)，0 | E/asset-runtime-check.log |
| 格式/差异 | clang-format-18实际-i及最终dry-run、git diff --check，0 | E/format-final.log、diff-check-final.log |

三套均执行现有19项原断言加MvpDetectors，普通CTest不启动模型；显式真实/模拟矩阵在Release上运行。正式run所记所有工具/产品源码SHA以及Release host/正式程序SHA与最终版本逐一一致；最终重建未改变其身份。本次没有正式运行失败或被替换的样本；负控的非零是预期测试结果，不是正常成功请求。

## 逐AC证据核对

| AC | 实际实现与已执行证据 |
| --- | --- |
| AC01 | Real.verify_assets核对固定archive/server/model与归档内实际库/许可证字节，assets.json保留；两个自有CPU进程各2线程、ctx2048/parallel1/GPU0；R0共8条含直连4、独列预热2、正式ai-inference-gateway非流/流2，均成功；所有参数/端口/PID在manifest/processes/config |
| AC02 | Real.Matrix的normal/concurrent/cancellation连同R0完整28条；R1实际目标索引RR双实例；R2首content+双active门槛后四短流全部实际排队，等待9.635677–10.295857s；R3两次首content且active后RST、随后恢复，两条SHUT_WR完成。cancellations.jsonl两次L1约0.107/0.105s归零，L2上游inode消失，L3观察slot idle而不宣称计算停止 |
| AC03 | Simulated.m1–m5完整29条，19成功/2取消/2后端失败/1队列超时/5拒绝；M1真实FIFO与b隔离、M2精确bytes拒绝/超时未触上游、M3队首RST与后继SHUT_WR/活动取消、M4坏chunk截断/重选/全部不可用/冷却后真实Trial恢复且唯一8条、M5等待503与活动完成。events/backend接收记录/Session最终关联完整 |
| AC04 | 原始57条finally独立文件与预分配plan一一对应；E/independent-recalculation.json另从原始文件重算分母/min/median/max；R0 cohorts独立、queue-waits分开成功派发与取消超时。drains逐点全部零账、FD同基线7、RSS≤B+32MiB，1s RSS/FD与事件/100ms账本保留。M5为退出状态明确单列，不伪造live FD。11类负控包括实际timeout残留attempt、部分坏chunk、缺DONE/错误成功、漏/重复样本、额度溢出/末态残留、子进程退出与错误/缺资产 |
| AC05 | 三预设各20/20；新C++规范/格式人工检查、189个历史文件字节保护、102源/48产物完整SHA；源码操作说明和实测结果齐全；全部所属进程回收。独立Reviewer应自有目录重建/各一次矩阵后裁决 |

负控并非只调用summary：bad_http用实际增量WireResponse保留首段x后拒绝坏chunk；timeout建立真实TCP不响应，Attempt finally记录failure/complete=false且join传播失败；child_exit实际执行/bin/false并回收；另外missing_done/false_success验证HTTP200或部分content不等于成功。11个negative-proof.json包含具体异常，驱动检查非零及证明存在。原始attempt目录、摘要和负控分母完全分离。

## 格式、身份与保护

仅新增C++文件tests/mvp/RuntimeHost.cpp：实际clang-format-18 -i，最终`clang-format-18 --dry-run --Werror tests/mvp/RuntimeHost.cpp`，版本Ubuntu18.1.3。人工逐个核对所有相邻函数定义空行（含类内）、构造/接口/成员职责分组；非简单record/collect/snapshot等类外定义，回调短lambda只转发具名cleanup。没有全仓格式化，不修改.clang-format。

| 清单 | 数量/意义 | SHA256 |
| --- | --- | --- |
| E/source-final-sha256.json | 102，沿S2的94源加8个mvp文件，每路径完整SHA | 208d643d550d0fd4a9ec2fb01d3c8e828335f6e70eab9b3149a26eb083306569 |
| E/binaries-final-sha256.json | 48，三套全部ELF/静态库 | 35398630951d9f43a272f8d1708ba16eb00ae0493135becd30e891b63c5817dd |
| E/protected-identity.json | 189个HEAD既有src/docs/tests/config/third_party/格式/预设逐字一致 | e0b2adfecc2beb5a59f835047124336933a2c81a3263bf5e57c5378c731e20fc |
| E/authority-sha256.json | 当前5份权威与授权一致 | a4d257eb3cf1c23315803d7563b7504ff0c3322379ec26bccd1af19969a1fcfc |
| E/real-raw-sha256.json | 正式真实目录每个原始文件身份 | fa30ce18be514718087d7af7751d24cb5f139e37379c5c97d6e241f52e8db362 |
| E/simulated-raw-sha256.json | 正式模拟目录每个原始文件身份 | 289a415f54396eccfbbbbfae07de6018e854893a29c7899f211f58d3e12b370a |
| E/independent-recalculation.json | 原始57条重算及run源码/二进制与当前一致 | 7b6a190a96728d7edb3283c361d2e7f01b3a177909b31f1d1c0c2c933ee9cb73 |

## 交接与限制

没有已知未解决功能问题或新增债务。慢读确实执行但本次pauses=0，未触高水；保留这一限制，不能把小模型慢读当真实背压覆盖。RSS/FD采样最大值不证明瞬时上界，短模拟可能错过峰；既有确定性限额断言与事件账本仍通过。健康为协议级，不校验生成语义。共享CPU两实例、小样本、host写盘会影响时序，不作吞吐/p99/SLO/性能提升/长期公平结论。

Reviewer重点复核finally与异常传播、M4唯一8条及真实Trial状态、R2真实队列、L1/L2、基线与原始分母；没有以观察host代替正式程序冒烟。文档与产品范围一致，Leader权威纠正已明确叠加，没有额外设计偏移。

E/process-audit-final.json记录真实4、模拟5、持久检测器2个子进程start/reaped一一对应，最终无MvpRuntimeHost/llama-server/ctest存量；构建/驱动也全部已结束。现在停止Builder执行，交独立Reviewer；不自行宣布V0.3/MVP验收完成。
