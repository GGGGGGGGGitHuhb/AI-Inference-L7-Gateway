# V0.3/S1 独立审查报告001

2026-10-20，Reviewer (Athena)。**FAIL：功能验证通过，存在一项未接受的空行规范 Minor，阶段尚不能收口。** 当前累计交付返工0/2；本报告不自行接受债务或执行纠正。项目Approved审查计划要求PASS前无未接受Minor，因此使用未通过结论；不将排版问题虚升为Major，也不声称出现产品测试失败。

## 范围、依据与独立性

读取[Approved设计](../../../leader/designs/V0.3/S1-design.md)、[Approved审查计划](../../reviews/V0.3/S1-review.md)、[Leader001](../../../leader/reports/V0.3/S1-report-001.md)、[Builder001](../../../builder/reports/V0.3/S1-report-001.md)、实施拆解/来源说明、ROADMAP/ARCHITECTURE/README相关模块与V0.2/S3/P1接受边界。无当前正式rework或旧S1 Reviewer报告。未发现仓库AGENTS或Reviewer专用指南，以用户跨项目规则及plan-project-docs全局Reviewer模板回退；已读取agent-execution-route及personal-cpp-standards完整规则和正反例。

检查配置、ModelRouter/RequestLease、Runtime、ProxySession、ConnectionPool、HttpParser新类型分类、三份新测试和用户配置示例。旧测试断言、第三方和P1工具未改，未发现范围扩大或实质权威冲突。本轮未修改产品、测试、Approved、Builder报告或根状态文档，没有提交/推送。

路线为原生WSL，/bin/bash login=false，cwd=/home/power/projects/AI-Inference-L7-Gateway；分支codex/v0.3-s1-routing-health，HEAD e231fda25879060fcd730f562982f06448f2ba11。独立角色目录build-local/reviewer/v0.3-s1/{tmp,cache,evidence,debug,release,asan}，构建及Python前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME/PYTHONPYCACHEPREFIX；socket与LSan首次窄提升权限，不关闭任何sanitizer。Builder已停止负载后运行，未共享Builder构建、端口、进程或可变测试状态。无下载/真实模型/P1矩阵/历史长期soak。

## 实际验证与证据

下文E为`build-local/reviewer/v0.3-s1/evidence`。分别执行`cmake --preset MODE -B build-local/reviewer/v0.3-s1/MODE`、`cmake --build build-local/reviewer/v0.3-s1/MODE -j4`、`ctest --test-dir build-local/reviewer/v0.3-s1/MODE --output-on-failure`，MODE逐一为debug/release/asan；配置、构建、测试全成功退出0。

| 独立执行 | 结果 | 原始证据 |
| --- | --- | --- |
| Debug完整CTest | 17/17，35.34s，零失败 | E/configure-debug.log、build-debug.log、ctest-debug.log、lasttest-debug.log |
| Release完整CTest | 17/17，30.97s，零失败 | 对应release四份日志 |
| ASan+UBSan完整CTest | 17/17，50.05s，零失败，无sanitizer错误 | 对应asan四份日志 |
| 追加状态/Session/绑定组合 | 38断言，FD4→4，无剩余fixture账本/lease/timer | E/Independent.cpp、Independent、independent.log |
| 双模型同时请求 | 8请求、四实例各2条，model/messages/Host正确，无重发 | E/Concurrent.py、concurrent.log |
| clang-format-18 | 14文件dry-run通过，Ubuntu18.1.3 | E/format.log |
| 手工职责/函数边界检查 | 回调仅具名短转发、owner生命期及职责分组通过；7处函数间空行缺失 | F-001及E内两份初审源快照 |
| 差异/历史身份 | git diff --check通过；88源一致，161历史保护中仅11项批准代码/CMake变更 | E/identity.json、source-sha256.json |

格式命令实际覆盖`src/app/GatewayConfig.{h,cpp}`、`src/routing/ModelRouter.{h,cpp}`、`src/gateway/{GatewayRuntime,ProxySession}.{h,cpp}`、`src/upstream/ConnectionPool.{h,cpp}`、`src/http/HttpParser.{h,cpp}`、`tests/Routing{Tests,Lifecycle}.cpp`，使用`clang-format-18 --dry-run --Werror`，没有格式化产品以掩盖发现。

追加Independent.cpp复用已审阅的RoutingFixture装配，但序列与断言由Reviewer新写：四idle→两个旧epoch请求并行→实际Session503摘除清idle→超过冷却仍因旧请求不能试探→迟到成功/失败均不恢复→唯一Trial成功恢复→旧Session下游排空仍不得回池；分别让活动Trial经客户端RST/显式stop终结，检查新epoch、零inflight、9ms拒绝/10ms新试探；检查所有FD恢复。另通过链接`--wrap=bind`仅在独立程序内把内核端口0选择确定为已取得的可用端口，配置第二实例指向该端口，实际Runtime在bind后抛`self upstream`，证明检查遍历所有实例。不是修改产品或仅静态检查端口0分支。

独立程序构建命令：`g++ -std=c++20 -g -I. -Isrc -Ithird_party/llhttp/include E/Independent.cpp build-local/reviewer/v0.3-s1/debug/libgateway_runtime.a build-local/reviewer/v0.3-s1/debug/libgateway_foundation.a build-local/reviewer/v0.3-s1/debug/libllhttp.a -Wl,--wrap=bind -o E/Independent`（E替换为上述目录），运行E/Independent退出0。双模型检查执行`python3 E/Concurrent.py "$PWD/build-local/reviewer/v0.3-s1/release/ai-inference-gateway"`，复用受控后端基础设施，自行设置8线程门闩及独立计数/正文断言；子进程communicate、监听线程join完成。

## 逐AC审查结果

- AC01：三套RoutingE2E逐一实际启动负配置并检查非零/无READY，覆盖类型、模式互斥、重复、缺字段、深度、数量/乘积/自指；合法32组64实例1024池边界成功。独立追加实际port0自指分支；旧JSON/直接构造及任意model透传由旧Runtime和E2E保留验证。源码整数/字符串/IPv4校验、≤64KiB、depth6和有界容器吻合。
- AC02：检查RR固定序列、LI最小请求数及同游标平局，Routing的leastInflightIdleChecks确实创建3idle与保留传输租约，inflight归零后即重新入选。真实socket长流门控短请求去另一实例，独立双模型8并发确认正文/Host不串。runtimeIsolationChecks实际使用相同物理地址但不同池、状态/计数分离。未知model与全不可用无上游新请求。
- AC03：Routing确定性时钟检查阈值、中立不增不清、成功清零、冷却/唯一Trial、中立/失败重冷却、epoch耗尽。独立追加混合晚到结果组合通过。E2E四实例各三轮503摘除、TCP可达404仍失败、200恢复；400/429中立。状态码只在完整HTTP判定，截断503正文仅记一次Failure。
- AC04：静态追踪completeRouting/closeUpstream/prepareError/finishSession/completeResponse/acceptStreamResult/shutdownWrite。非流/流完成先释放请求inflight，传输租约可能继续持有但归池再次核验epoch；成功后取消不覆写。试探取消/停止/容量满/流预算不足均中立且重新冷却，重复finish幂等，独立组合检查旧lease在新epoch恢复后仍不可回池。14种Session终态覆盖上游故障、明确deadline、本地保护和暂停response中立，类型化ParseFailure不依靠字符串推断；旧对外errorStatus/errorCode保持。
- AC05：真实网关E2E验证404/503精确代码、无重试、已提交SSE断流无第二HTTP状态/伪零块。旧GatewayE2E/Runtime覆盖未提交502/504等历史语义；活动Trial流与另一实例idle同存时SIGTERM有限退出。路由无健康timer，清池/retired延迟销毁顺序保留；独立资源末态及整组FD恢复。
- AC06：三套17入口全跑，源/binary/历史身份与用户配置说明齐全；唯一不满足为F-001规定的人工空行检查。无性能收益/MVP提前完成声明。根README/ROADMAP/ARCHITECTURE仍是当前阶段规划快照，待最终PASS后由Leader统一收口，当前不擅自改成完成。

测试数量仅描述执行规模，以上具体断言和代码路径才是覆盖依据。38条追加断言不替代完整17入口，端口包装不是部署环境容量证据。

## F-001：相邻函数定义未保留空行（Minor）

依据Approved设计§7/AC06、审查RV06及personal-cpp-standards“`.cpp`中相邻函数定义之间保留一个空行，包括测试辅助函数及类内定义”。

当前位置：`src/app/GatewayConfig.cpp:114`（readPool→requireKeys）；`tests/RoutingLifecycle.cpp:13、16、20、21、30、364`（ProxySessionTestAccess各方法、RuntimeTestAccess pool→router、idleAndTrialChecks→trialAndCapacityChecks）。这些函数定义之间直接相邻，合计7处。`nl -ba`及初审源文件即可复查；clang-format通过不等于职责空行符合人工规则。

预期：上述每个边界一个空行。实际：缺失。影响：违背明确交付规范，阅读分组边界不清；没有已观察的运行时功能影响。要求Builder仅补齐空行、复核本次受影响文件同类边界，实际重跑格式dry-run，追加后续报告并纠正“人工全部通过”的交付描述。不得修改行为、断言、Approved或原Builder001。

## 复验边界与身份

当前独立88项源清单SHA256 `a2a8ec791c58a9ae97d770031801203bcf217ae0b29b1d3550cc66ba210186e7`，逐项重算与Builder最终完全一致。独立39项产物清单SHA256 `bd22a2423190db5e6039cc868268fe0589e8087b9b00615e9cb30bde3ef5baa9`，每套10可执行+3静态库；不把39当测试数。源初审两份原样副本位于E/GatewayConfig.cpp、E/RoutingLifecycle.cpp，可用于逐字节比较纠正差异。

设计SHA `8f3aeeee2d137bf484a008630021218da418824f5dfefa2edc05bc61e1a64740`，审查计划SHA `79e390d108d1686056956462e01bd3b6ad3f49f2876998dae0364281f6dceafc`，Builder001 SHA `e4673d6394daa24704f4d2ff0d14eb3ec5ac555baff81b755010f80abe5160ee`；均保持。161保护项中150原样，11为批准CMake/原有C++改动，具体列表在identity.json，历史文档/旧测试/第三方/P1未改。

若后续严格只插入空白行且新报告记录准确：Reviewer须独立比较两份快照，证明剔除空白行后字节完全相同、其余86源不变；核验本轮39产物身份未变，重跑14文件格式与人工边界审查、git diff --check和文档保护，然后以新Reviewer报告复用本轮三套CTest/追加组合。无需因纯空行重复全套或长期测试。若存在任何token、注释、字符串、断言、构建配置或行为改动，不适用该最小复验许可，需按实际差异重新验证。

## 未验证项、风险与结论

无契约内功能验收阻塞项；真实多实例模型/GPU/业务SSE语义、S2准入队列、性能收益与P1约44ms诊断未执行，均为明确范围外，不算本轮缺陷。完整2xx只证明当前HTTP协议成功，初始Available仅配置许可，无流量不会主动恢复；池限额不等于推理准入。

全部自有测试/补充程序已退出，CTest子进程及受控后端均回收，未留后台负载。无已接受债务，无建议转债条目。**最终结论FAIL，仅F-001 Minor待有限纠正；功能测试全部通过。** Leader不能在该发现未关闭或明确接受前将S1写为已完成；Reviewer不替代Leader收口、协调者提交职责。
