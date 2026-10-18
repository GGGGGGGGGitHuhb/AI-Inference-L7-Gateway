# V0.1 / S1 独立审查计划

状态：`Approved`。创建/采纳日期：2026-10-18。

依据：[S1 设计](../../../leader/designs/V0.1/S1-design.md)。Leader 根据用户“你来决策吧”的授权采纳。本文件仅细化验证方法，不能改变需求或扩大 S1 为完整网关。本轮尚未执行独立审查。

## 1. 输入与独立性

读取设计、架构、路线、实际实现、第三方清单与复用来源记录、Builder 报告及后续返工文件。当前没有 Builder/Reviewer 实现报告；收到交接时重新核对，不把本规划报告当作实现证据。

使用原生 WSL 路径和独立 `build-local/reviewer/` 构建、缓存、临时目录。第三方只读固定快照可共享；测试进程、输出、构建状态和故障注入配置必须独立。实际网络测试按当前沙箱权限路由执行。

## 2. 必需审查矩阵

| 编号 | 来源 | 方法与证据 | 通过条件 / 失败级别 |
| --- | --- | --- | --- |
| RV-01 构建独立性 | REQ-01 / AC-01 | 独立目录构建 Debug/Release；检查 CMake 与编译命令，核对所有依赖来源、hash 和许可；构建不得依赖兄弟仓库或联网 | 两种构建均通过、结果可复现；缺失为 Major，环境无法执行为 BLOCKED |
| RV-02 复用与所有权 | REQ-02 / AC-02 | 将固定提交原始源码和散列与迁入清单比对；独立验证 Buffer 溢出/移动/视图、FD 移动后仅关闭一次、Timer 取消/重排/回调内变更 | 语义和适配差异有证据；资源泄漏/重复关闭为 Blocker，其余契约缺陷 Major |
| RV-03 HTTP 定界 | REQ-03 / AC-03 | 覆盖每一支持矩阵行；有效夹具测试整块、逐字节、每个单切分点和固定种子分片；组合两条消息核对消费偏移 | 输出正文/状态一致且边界准确；定界歧义或串扰 Blocker |
| RV-04 JSON 与 API | REQ-04 / AC-04 | 每个字段的合法/非法类型、缺省、边界；重复键、UTF-8、messages/深度/成员限制；比较输出与原始 JSON 字节 | 合法元数据正确，拒绝分类符合契约；Major |
| RV-05 预算与生命周期 | REQ-05 / AC-05 | 对设计所有上限作边界测试；构造多次 reset/error/EOF、回调失败与分配失败可控路径；ASan/UBSan 动态执行 | 无越界/泄漏/异常跨 C；Blocker，未执行必需动态检查不能 PASS |
| RV-06 模拟器联动 | REQ-06 / AC-06 | 独立启动模拟器；直接访问后将原始响应交给 C++ 测试；覆盖固定/分块/延迟/截断/畸形场景和退出 | 行为确定、临时端口、仅清理自有进程；Major |
| RV-07 文档与范围 | REQ-07 / AC-07 | 执行 README 的实际入口，核对 manifest、复用记录、格式化记录和阶段状态；检查变更未涉及原仓库、完整代理或后续功能 | 命令和证据匹配；虚假完成或必需证据缺失 Major；纯措辞 Minor |

## 3. 关键攻击性与异常用例

- 请求 TE+CL、重复/逗号 CL、空 TE、多层 TE、重复 Host、非法起始行、非法 CR/LF/头名、超头部预算：拒绝且不能继续解释尾部为第二请求。
- chunk size 行在每个字节处分片；终块缺 CRLF、正文截断、非空 trailers、超长扩展、超 chunk 数：不能成功完成。
- HTTP 无正文状态、1xx 后的最终响应、1xx 次数/累计字节超限、101、EOF 定界、长度声明未满足的 EOF：分别遵守设计。
- Connection 提名关键语义头必须拒绝；普通逐跳头和其列举字段移除；重新生成长度不产生 TE+CL；普通重复端到端头不被无条件合并。
- JSON 深度 31/32/33、成员总数边界、每个对象的重复键、超长 model、错误 messages 结构、stream=true、n>1、未知字段与 NaN 类非法 JSON：按设计分类拒绝。
- 输出 Buffer 源视图在变更后使用、Timer 回调取消另一任务、同一时刻新增已到期任务、Socket move 后析构：结合固定来源契约验证，不凭名称推测行为。

## 4. 构建与测试顺序

本节列出 S1 必须实现的验收入口。当前没有 CMake 文件，因此本轮未执行这些命令；收到实现后按原样执行，不能把缺少预设静默替换成更弱验证。

Shell：Bash。工作目录：仓库根目录。先创建并设置 Reviewer 的 TMPDIR、TMP、TEMP 和缓存根，必要时通过 CMake `-B` 覆盖到独立目录；预设不得把角色目录硬编码成唯一位置。

```bash
cmake --preset debug -B build-local/reviewer/debug
cmake --build build-local/reviewer/debug
ctest --test-dir build-local/reviewer/debug --output-on-failure

cmake --preset release -B build-local/reviewer/release
cmake --build build-local/reviewer/release
ctest --test-dir build-local/reviewer/release --output-on-failure

cmake --preset asan -B build-local/reviewer/asan
cmake --build build-local/reviewer/asan
ctest --test-dir build-local/reviewer/asan --output-on-failure
```

独立复核 Release 下错误断言确实导致非零退出；测试名称或程序存在不代表断言有效。检查 CTest 注册数大于零，记录程序与测试数量，不预设一个臆造的通过总数。

第三方快照存在时 configure/build 不得执行 FetchContent 下载或访问兄弟工作区。检查本次格式化使用 clang-format 18 且覆盖所有自有/适配 C++ 文件；第三方文件不纳入格式化。

模拟器测试必须设置进程与场景超时；超时失败后回收本测试自有进程。不能因为网络权限不足而把必需联动测试标记为跳过后通过；记录具体原因并报告 BLOCKED。

## 5. 证据与结论

报告记录代码提交或工作区文件散列、工具版本、执行命令、退出码、测试数量、失败摘要、所用资源预算、临时目录和模拟器退出证据。第三方版本与来源散列必须能够重新计算。

输出到 `docs/reviewer/reports/V0.1/S1-report-xxx.md`，按已有报告编号递增；当前尚无该报告。每项发现列关联 RV/REQ/AC、复现输入、实际/期望、严重程度和是否阻塞关闭。

- PASS：所有 AC 有独立证据，无未解决关键问题。
- PASS WITH DEBT：仅有明确接受的非关键延期；不能豁免定界、资源预算、所有权、依赖可复现性或必需动态测试。
- FAIL：实现不满足设计，给出最小复现和返工项。
- BLOCKED：环境或必要材料阻止完成验证，明确未覆盖项，不推断通过。

下一步只能由 Leader 根据真实 Reviewer 结论决定阶段关闭。S1 完成也只代表协议与组件基础通过，不代表 Gateway 代理链路完成。

## 变更记录

- 2026-10-18：依据 S1 设计建立 REQ/AC/RV 追溯及独立验证步骤；当前仅有计划，未运行审查。
