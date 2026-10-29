# V0.5/S2 启动报告001

## 第一部分：PM 决策摘要

2026-10-29，On Track，用户已授权启动S2。采纳[设计](../../designs/V0.5/S2-design.md)与[审查计划](../../../reviewer/reviews/V0.5/S2-review.md)。固定比较直连单Gateway、客户端均分双Gateway、L4LB接入双Gateway的延迟、CPU及各段TCP载荷字节；另以长流构造案例验证连接数均衡不代表在途工作量均衡。

保持产品、依赖与用户L4工作树不变；采用同一合成后端和总额度，控制连接复用。预计交付可复现18cell、三重复配对差异和边界报告，不能证明真实GPU或横向扩展容量。PM必需决策：None。下一步实现与自测后独立审查；完成后本地提交，不自动推送。

## 第二部分：详细工作记录

S1已独立验收并推送92fcf3d，无遗留债务；三角色最终报告已读取。当前分支codex/v0.5-s2-cost-boundaries，原生WSL，角色隔离tmp/cache/build/evidence，L4源只读。复用S1 Owned/Identity/Fixture和HTTP WireResponse，而非新增产品统计接口。

已与独立Reviewer核对设计风险：TTFB必须首次wire recv；HTTP framing完成和EOF分开；CPU真实窗口包含客户端与后端并保留tick分辨率；L路径仅多算L4→Gateway这一段，不重复计算接收边；正式与预热会话分开；D↔M改变进程数，M↔L才隔离L4层；长流偏斜按实际连接日志而非RR猜测。固定参数与门槛见设计，不根据结果择优调整。
