# E5-5：一次性公开任务验证（2026-11-01）

P4 的最终流程在已暴露的八个开发题上暂定通过 7/8。本阶段没有再修改取证、写作或评分规则，而是先以固定种子 `deepsearch-e5-2026-11-01` 从锁定版本 `RUC-DataLab/DABStep-Research@62ae9e0...` 选择 20 道此前未用于本仓库开发的任务。排除原八题；按 Data Analysis、Data Insight、Data Preparation、Report Generation 各五题分层，排除没有可解析条目检查表的 Open 类。`evals/dabstep/holdout20.json` 仅记录 ID、任务类型、原题和检查表哈希；原始题目从本机校验过哈希的公开数据文件读取，不在仓库重新发布（上游衍生数据许可未声明）。选题在运行前冻结，评分后即转为已暴露的回归题。

两种流程都使用 DeepSeek Flash non-thinking、同一题序、只读 SQL 快照、330 秒硬超时、每题 10 次请求 / 180,000 估算预留 token 上限、批次 1,500,000 上限，以及同一个三次复评 DeepSeek judge。P2 简单流程使用原八个 SQL 汇总查询和 Writer；P4 最终流程在相同 SQL Evidence 后附加五个确定性费用汇总 Evidence。比较器检查 20 题的 SQL Evidence 前缀逐字节一致、最终流程恰好多五条，并检查源码、数据、超时、模型和预算摘要一致。两个 run 的源码摘要均为 `87541403fd386f52c6b0bb235791eb40dd6d6a78810a06a9ed1de9a9505b40d7`。未并发运行，以免服务竞争影响延时。

| 指标 | P2 简单流程 | P4 最终流程 |
| --- | ---: | ---: |
| 排定／有终态／正常完成 | 20/20/20 | 20/20/20 |
| 暂定端到端通过 | 10/20 | **19/20** |
| 平均要点覆盖 | 0.770 | **0.929** |
| 引用 ID 全部合法的题 | 20/20 | 20/20 |
| p50 / p95 秒 | 26.6 / 34.8 | 25.0 / 31.2 |
| 生成器记录 token | 258,519 | 333,418 |
| 裁判记录 token | 804,056 | 1,026,412 |

分层通过：Data Analysis 0/5 → 4/5，Data Insight 1/5 → 5/5，Data Preparation 4/5 → 5/5，Report Generation 5/5 → 5/5。最终流程唯一未通过的 `dabstep_research_022` 覆盖 0.75：能给出费用分布、境内外比较与商户建议，但没有可验证的最优 ACI / 交易量层级反事实及节省额。它在旧流程中也未通过（0.375）。不因这题低分而调整已冻结流程或裁判。`evals/reports/e5-5-holdout20-comparison-2026-11-01.md` 保留 20 题全表，两个 run 的 manifest、scores、终态、报告也在同目录；原始 trace 和模型文本留在忽略的 `evals/results/`。

这是一组**任务级、同语料**的一次性验证，不能称作跨文档、跨站点或完整 Deep Research 榜单成绩。20 题都使用同一份商户手册、交易和规则，且生成器按原始问题收到检查表；没有旧个人电脑 PDF、无答案题、Web 或混合来源题。语义覆盖和证据支持由与生成器同族的 DeepSeek judge 给出，未做盲法人工审核或独立数值逐项重算；引用 ID 合法性和费用汇总对参考总额的核对是机械检查。生成器额外消耗约 75k token，裁判额外消耗约 222k token；本轮没有 GPU 和付费网页搜索。上游数据许可未声明，复现须自行从锁定源下载，不应把本仓库当原始数据镜像。

复现命令：`python -m evals.benchmark_preflight`，按 `holdout20.json` 的顺序运行 `evals.run_v3.run(case_ids=..., profile="deepseek", workflow="simple_sql")` 与 `workflow="simple_sql_no_fee"`，分别执行 `python -m evals.score_v3 --run <目录> --judge deepseek`，最后运行 `python -m scripts.compare_holdout20 --baseline <目录> --final <目录> --output evals/reports/e5-5-holdout20-comparison-2026-11-01.md`。实际 run ID：最终 `benchmark_v3_20261101T120648Z_182c79f4`，基线 `benchmark_v3_20261101T121542Z_a4a07448`。
