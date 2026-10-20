# V0.3/S3 独立网关MVP综合验收设计

状态：**Approved / 待实现**，2026-10-20，累计返工0/2。用户“开始s3工作”及既有技术决策委托授权路线图内方案；[Leader001](../../reports/V0.3/S3-report-001.md)记录决策。起点d89de57eb6be0106bccd24432b2559d342ed8b79，分支codex/v0.3-s3-mvp-acceptance；S2已本地提交，未核验推送。

## 1. 范围与实现边界

关闭ROADMAP V0.3/S3：独立启动说明、真实后端兼容、故障/过载矩阵、初步资源与延迟报告。验证已实现的流、路由、健康、准入与队列同时工作，不重写产品。S1/S2既有权威保持；本阶段不增加重试、主动探测、协议字段、管理API、GPU/L4LB联调或V0.4优化，不修P1约44ms现象。

新增自有`tests/mvp/`显式综合驱动、只读测试host/检测器及`docs/acceptance/V0.3/S3-results.md`。复用tests/integration的OwnedProcess、WireResponse和逐attempt finally留存模式，复用AdmissionRuntimeHost现有friend与Session trace，不修改旧工具行为/旧断言；必要新host链接同一gateway_runtime。观察状态须有界（本矩阵请求数、128MiB日志），不加公开产品接口。正式ai-inference-gateway另跑真实冒烟，不能仅host通过。若发现产品缺陷，保存失败并交协调者统一返工，不以工具补造成功。

## 2. 环境与资产

原生WSL `/bin/bash` login=false，cwd `/home/power/projects/AI-Inference-L7-Gateway`。每角色使用`build-local/<role>/v0.3-s3/{tmp,cache,evidence,debug,release,asan}`；脚本前显式TMPDIR/TMP/TEMP/XDG_CACHE_HOME。socket/loopback/LSan已知权限边界首次窄升级，不能禁检测器。

只读复用`build-local/integration/v0.2-s3/`：llama.cpp官方b7481及Qwen2.5-0.5B-Instruct Q4_K_M，来源/许可见[V0.2/S3设计](../V0.2/S3-design.md)。Leader已确认存在并计算SHA：`backend/llama-b7481/llama-server`为`45938e6847d403ff6486cd692de9441aeb330e971a5dd8ad6f695b60bae2d081`，与历史Reviewer asset-check一致；`models/qwen2.5-0.5b-instruct-q4_k_m.gguf`为`74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`，491400032字节，与资产清单一致。各角色仍独立校验模型、server、库/许可和启动参数，不下载/安装。缺失或身份变更为Blocked，不能替换模型。

本阶段明确允许两个同模型CPU进程同时运行，替代旧S3单进程实验布局，旧实验结论不变。每进程固定`--alias gateway-qwen --ctx-size 2048 --parallel 1 --threads 2 --threads-batch 2 --n-gpu-layers 0 --metrics`，host127.0.0.1，自有不同端口，模型路径绝对化；每实例启动120s、RSS护栏2GiB。两进程共享CPU/内存，不等同独占双实例或GPU收益。禁止接管别人的监听；只清理自有PID/process group，TERM5s后KILL/wait。Builder完全回收后Reviewer独立启动。

## 3. 固定配置与分母

真实Gateway一个模型gateway-qwen、两个实例，RR；LI额外由模拟验证。global2/perbackend1，queue每模型count4/bytes65536/timeout120000ms；max_connections16/reserved256MiB，stream总1MiB及原192/64KiB水位；池每实例max4/idle1/1000ms；health threshold1/cooldown1000ms。request10000/connect3000/upstream_write5000/response120000/stream_idle30000/downstream_write10000/total150000/shutdown3000ms。所有总期限从accepted开始，不因排队重置。

复用既有合成Inputs.json短/长prompt，temperature0/n1，短32token、长512token；保存输入hash。只支持现有字段。真实每角色一次正式run，总护栏1800s（含启动），单请求客户端155s；不满足固定条件直接失败，不能事后扩时/补样本替换失败。每个attempt预分配唯一ID、计划类别、开始结束、错误/取消、HTTP状态及部分响应，finally落盘。所有失败、拒绝、超时、取消都保留，预热独立分母。

| 组 | 固定请求分母与顺序 | 必须观察 |
| --- | --- | --- |
| R0 兼容/预热 | 每后端直连非流1+流1，共4；host预热流2；正式程序代理非流1+流1，共2 | 每条200、有效JSON或SSE非空content与唯一DONE/合法HTTP结束；预热不混正式延迟 |
| R1 正常路由 | host顺序8条，非流/流交替 | 两实例均收到请求，RR顺序可追溯，8/8完整成功 |
| R2 并发排队 | 2条长流启动且首content后，再发送4条短流，共6；其中1条长流首content后暂停读1s，再每20ms读1024字节 | 6/6完整、至少1条实际排队；若模型提前结束导致零排队，记录未满足，不能伪称覆盖；同时inflight≤2/per≤1/count≤4/bytes≤65536 |
| R3 取消/半关闭 | 长流RST2条（首content后），各接1短流恢复，共4；完整请求SHUT_WR2条 | 2预期取消、4完整成功；取消5s内本地额度归零，后端slot观察最多10s，不能以RST推断计算停止 |

真实共28attempt：4直连、2预热、2正式程序、8正常、6并发、6取消/恢复/半关闭；其中2预期取消、26正常成功。真实排队观测非确定性由R2明确门槛控制；拒绝和精确取消竞态使用下述门闩模拟，不依赖模型速度。R2记录慢读实际开始/结束及完整正文，不要求小模型触发高水；并发启动以首content和host活跃状态为门槛，已结束则本次条件未满足，不无界增加token/请求。真实L1网关资源/L2上游连接释放必须证实；L3仅报告slot与恢复证据，不声明GPU计算取消。

## 4. 确定性综合矩阵

每角色每组一次，独立gateway/host可重置，模型a有a1/a2，模型b有b1，a使用RR/b使用LI（另外用S1/S2单测覆盖多候选LI）。health1/cooldown1000ms；global2/per1；每模型queue2/byte4096/timeout500ms，total2000ms。正常模拟帧由固定字节组成；gate最长5s，单组15s、全模拟120s护栏。测试通过观察后端收到/host进入Waiting再推进，不用sleep猜测。每组准确记录下列正式HTTP请求；启动健康探测不得计入分母。

| 组 | 分母 | 事件与预期 |
| --- | --- | --- |
| M1 count过载/FIFO | 6 | 2个a长流占满；2个a短流入队；第5个a请求queue_full拒绝；第6个b请求入队；依次放行，5成功/1拒绝，模型内FIFO、跨模型最终进展 |
| M2 byte/timeout | 5 | 2个a占满；一个合法大于4096逻辑charge请求queue_full；一个小请求等待至queue_timeout；释放后新a成功：3成功/1拒绝/1排队超时；无额外上游请求 |
| M3 取消/半关闭 | 6 | 2个a占满，1个a队头RST，下一a完整请求SHUT_WR保持等待；释放一个活动流前RST取消另一个活动流；再发2个恢复请求：2预期取消/4成功，FIFO空洞移除、额度恰一次释放 |
| M4 故障/隔离/恢复 | 8 | a1首内容后发送坏chunk截断（1失败）；并行b1流及一个排队a请求最终成功；停a2后请求a触发连接失败（1失败），下一a全不可用503（1拒绝）；两个摘除期限前确认503后，重启a1等待冷却，新a试探成功，再发a/b各1成功：5成功/2失败/1拒绝；b正文不变，恢复须完整HTTP成功 |
| M5 停止 | 4 | 2个活动a流、2个等待a请求；SIGTERM，等待者gateway_stopping，放行活动流正常完成：2成功/2停止拒绝，有限退出，无迟到回调 |

共29正式attempt：19成功、2取消、2后端失败、1排队超时、5拒绝（含停止）。M4必须用可观察的Router状态/请求目标安排a2故障，避免把某个RR序号当未验证前提；脚本不得跳过未触发场景。已提交失败流不得补零块/第二状态行/DONE。所有正常模拟响应严格长度/hash相等。恢复新请求不是重试；单个失败不能污染其他模型/流或账本。

## 5. 资源、延迟与工具验收

每组预热/启动后记FD/RSS基线，各组结束等idle池过期后≤5s排空：queue/bytes/request inflight/sessions/reserved/stream capacity/pending/paused/leased/request timers归0，FD回相同启动基线；监听/signalfd常驻明确记录。采样100ms账本与每秒Gateway/后端RSS/FD，保留峰值与采样间隔，瞬时限额靠产品累计峰值/确定性断言证明，不能只靠轮询。Gateway预热排空RSS=B，各排空点≤B+32MiB；不满足先诊断不得自动豁免；后端RSS分开，非Gateway预算。内核buffer及allocator缓存边界如实说明。

记录客户端monotonic发送完成→首非空content的TTFT、发送完成→合法HTTP结束的E2E；非流只有E2E，错误/取消不塞进成功延迟。queue_wait=dispatched−enqueued，仅真正排队且派发样本；超时/取消等待另列，不混入。每组列总尝试、成功、预期取消、拒绝、超时、失败分母及min/median/max；不报小样本p99或性能提升，无直连同负载公平对照、吞吐/SLO/生产容量声明。

工具必须负控：缺/错资产、坏HTTP或缺终止、客户端超时、子进程失败、样本遗漏/重复、队列/额度越界、资源未归零、错误分类伪装成功。失败应非零且保留attempt；运行目录不得覆盖。三预设完整CTest，新增短检测器不启动模型/长负载；规范检查修改C++及人工相关规则。Reviewer独立构建、进程、原始结果，独立按attempt重算分母/延迟/峰值，不复用Builder汇总。

## 6. AC与交接

AC01：独立启动/配置/资产来源可复现，R0成功且无Server/L4LB依赖。AC02：R1/R2/R3固定28attempt分类准确，路由/流/排队/取消同时工作。AC03：M1–M5固定29attempt、故障恢复隔离及终结符合契约。AC04：账本、FD、RSS及分母/延迟报告可独立复算，工具负控通过。AC05：三预设完整回归、代码规范、历史保护、来源/SHA/命令/退出码、操作说明齐全，独立PASS后才能关闭V0.3/MVP。

Builder先完成短工具负控与配置，再各一次真实/模拟run，最后回归和报告；Reviewer同规模独立验证，可补少量关键负控，不重跑V0.2长soak/P1矩阵。所有环境/实验失败保留，新尝试另编号；失败分类与固定门槛不得事后改。无重大新增依赖或债务；发现权威冲突交Leader，最多两轮统一返工。最终Leader收口后协调者本地提交、不推送，不自动启动V0.4。
