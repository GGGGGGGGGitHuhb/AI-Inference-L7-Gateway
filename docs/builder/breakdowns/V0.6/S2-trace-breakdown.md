# V0.6/S2-trace Builder实施拆解

依据Approved S2-trace-design、review及Leader002。读取personal-cpp-standards完整规范、plan-project-docs Builder/stage设计参考、agent-execution-route；本仓无专用GUIDE，继续采用全局Builder参考。用户已授权实施；三项负控与性能必须在冻结后经Leader核对，本文件不放宽条件。

| 子项 | 模块/依赖/验证 | 状态 |
|---|---|---|
| T1 | Gateway默认OFF CMake、固定观察区、accept分类/阶段/移除；关闭/幂等/饱和测试 | 实现与U/O/专门单元完成，待最终冻结 |
| T2 | 复制外部L4实际dirty源码、独立诊断补丁、TCP/健康同线程共享池；默认OFF U/O/T | CPP005补丁、RW001/002及U/O TCP13/13完成 |
| T3 | Client/Backend端点适配、固定binary解析、tuple+生命周期关联；歧义/健康/复用测试 | 实现及12项解析/生命周期自测完成 |
| T4 | 独立U/O Release全回归、受影响ASan+UBSan、L4现有TCP测试 | U21/O22、受影响Sanitizer7与L4双13通过 |
| T5 | 冻结18cell/1200s/4GiB、配置/源/工具/二进制；三负控和低档9项 | Frozen001执行3负控，2通过/第三工具退出错误首停；低档未开始 |
| T6 | 仅低档全门槛通过后6高档；报告开销/条件性关联/优化入口 | 未执行 |

实际路线：原生WSL /home/power/projects/AI-Inference-L7-Gateway，分支codex/v0.6-s2-trace起点7546020。自有build-local/builder/v0.6-s2-trace/{tmp,cache,evidence,gateway,l4-source,l4-build}，显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；后续构建-j2，回环功能回归走窄权限。首次静态磁盘可用约974GB，大于双角色8GiB证据和构建空间；冻结前重核。外部L4只读实际275文件复制，逐文件hash留本机，不发布其dirty diff。

固定布局：每连接一条256B聚合记录原位补齐，不逐I/O追加。每进程131071槽+256B头恰32MiB；高档88320业务连接（含预热）后有42751个健康/其他成功accept余量，单个Gateway按全88320计算，不依赖均分。满则drop++、从不覆盖，本cell不可完整归因。L4 TCP和health通过reactor维护/选后端回调同线程执行，不引入锁；健康连接用kind=3及实际出站tuple标识，匹配不唯一仍unknown。

每性能cell最坏：客户端512、后端192、L4日志256、客户端端点256、后端端点192、关联256 B/计划请求，加三个32MiB记录区及固定余量，可置于256MiB；负控≤64请求按实际事件远小于16MiB。全矩阵15×256+3×16+128=4016MiB≤4GiB，另需每项60s/全轮1200s、RSS1GiB/FD2048、子进程128MiB不变。仅停止排空后导出，进程内SIGALRM独立10秒硬限+控制器核验，分片≤1MiB。关闭U无编译观察代码，O没有热路径时钟/端点查询或写记录。

已知前期构建失败均保留日志：Gateway测试误用CHECK宏改为本仓GATEWAY_CHECK；L4直接include TcpReactor.cpp的测试需链接诊断库，修正仅隔离副本CMake。无18cell负控/性能已发生，未重置任何采集账本。

集中预检与所有真实失败/身份见[S2-trace-report-001](../../reports/V0.6/S2-trace-report-001.md)。冻结后3负控已尝试；第三工具失败首停，15性能未开始。现场/只读派生/回收及BLOCKED交接见[S2-trace-report-002](../../reports/V0.6/S2-trace-report-002.md)。
