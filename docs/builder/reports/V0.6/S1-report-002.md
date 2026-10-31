# V0.6/S1 Builder 002：正式采集首停与只读定位

2026-10-29。依据Approved S1设计及Leader冻结清单/停止规则。正式清单SHA256 `81877a406c767b66fb90422a79b805f53c3c77a13869219b4f967ee5116358f4`；工具未修改，未重新发压，等待Leader返工授权。

正式首批完成6cell，第7个`F-A-L-1920-r0`请求运行与清理完成，但收口审计报`incomplete L4 log/session conservation`，runner退出1，后续65cell未执行。全72计划、首错result/ledger和全部原始分片保留。调用为`Run.py --mode formal --manifest ...`，外包`prlimit --fsize=1048576:1048576`，继承前44cell累计预算。

只读逐行定位：44,160条accepted，旧正则仅解析44,122条closure，漏掉38条。漏项原始行均含多词reason，例如：

```
session=93 backend=127.0.0.1:37703 reason=shutdown SHUT_WR sent_c2b=228 sent_b2c=0 errno=107 Transport endpoint is not connected
```

`Analyze.py`使用`reason=([^ ]+) sent_c2b=...`，错误假定reason无空格。6个测试子进程全部正常exit0；捕获5,898,202B与分片总字节相符，文件末尾有换行，未见session行交错/重复；服务停止pending为0/0。独立Reviewer得到相同解释。

只读内存探针仅把reason识别范围改到`sent_c2b`分隔符（不改任何py/证据文件、不发请求），完整审计恢复44,160 accepted/closed；client所有阶段入队10,182,980B等于L4 sent_c2b，接收51,195,456B等于L4 sent_b2c。正式38,400计划=38,374成功+26空响应transport_failure，good99.9323%，lag P95 1.023ms，正文/协议损坏0。该派生数字目前用于定位，不能覆盖原failed结果。

本次问题属于审计器解析，不是日志丢失或产品协议损坏。建议最小Approved rework：允许多词reason并以完整行结构核验；新增多词/未知session行/跨片守恒负控；以版本化派生审计保留首错；经Leader重新冻结工具身份及恢复规则后只执行剩余65cell，不重采已发生请求。未自行实施此建议，未扩大产品范围。

Reviewer重点：独立确认原始session集合、字节与PID退出证据，核验返工未变动请求/时钟/SLO/生成器/速率/预算，已失败cell继续计账。后续状态以新Builder报告为准。
