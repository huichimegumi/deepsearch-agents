# E7-0：公开任务选取与预算冻结

30 个任务按预先指定的散列排名选取：DABStep 四类各三题、Hybrid 三方向各四题、DeepResearch Bench 中英文各三题。排除本项目以前运行的 DABStep 28 题及 Hybrid 三题。选题未使用生成器成绩。选取与文件摘要写入 `evals/public_benchmarks/suite.lock.json`；公开仓库只保存 ID/哈希，原题、检查表及 Hybrid 解密内容留本地。

无模型/搜索预检 ready=true，三类任务数量 12/12/6。原有 benchmark 预检同时通过。便携离线测试核对分层、排除规则和无标签泄漏。HF CLI 核对 Hybrid 锁定 revision；DRB 锁定 f2735b5c。全程 CPU，无 GPU 或付费调用。

开发使用旧公开 smoke/RFC dev 与新编写的拒答、部分可答、工具故障用例。最终实现冻结后，simple/bounded 各运行一次；不根据这 30 题的输出做修复。预算每题 300 秒、硬截止 330 秒，最多 8 模型请求、180k 估算预留 token、5 次取证、每 Web 查询至多 2 页面；每组 5.4M 预留 token。评分单独每组 60 请求/1.5M 预留 token。缺失/超时/低分都保留。

DABStep 仅 checklist/证据暂评，不混称独立数值准确率；Hybrid 比较公开参考结果并检查依赖方向；DRB 按公开细则使用自定义裁判，不称官方 RACE/FACT。三类分开报告。现有 DABStep 数据相同、Hybrid 限 alien 数据库、题目公开、Web 随时间变化，均限制泛化与配对结论。独立裁判未配置时必须披露，并交付匿名审阅包；不因缺少人工复核而不发布自动报告。
