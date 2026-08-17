# 项目评测集

本目录包含 DeepSearch Agents 第一阶段的项目内中文评测集，覆盖路由、联网搜索、数据库查询、本地知识库检索和端到端报告生成。

## 数据集

- `datasets/web_research_zh.jsonl`：20 条联网搜索 QA 任务。
- `datasets/db_query_zh.jsonl`：20 条 MySQL 业务数据查询任务。
- `datasets/routing_boundary_zh.jsonl`：20 条路由、拒答和边界样本。
- `datasets/end_to_end_report_zh.jsonl`：10 条端到端报告生成任务。
- `datasets/rag_local_zh.jsonl`：20 条本地知识库检索 QA 任务。

## 通用字段

每条 JSONL 样本包含以下核心字段：

- `id`：稳定的样本 ID。
- `category`：样本类别，例如 `web_research`、`db_query`、`routing_boundary`、`end_to_end_report`。
- `task`：面向用户的中文任务描述。
- `expected_route`：期望使用的高层路由或工具链。
- `disallowed_routes`：不应使用的路由或工具链。
- `success_criteria` 或 `answer_checks`：人工可读的通过标准。

部分数据集包含额外字段：

- 联网搜索样本包含 `expected_source_types`、`freshness` 和 `answer_checks`。
- DB 样本包含 `gold_sql` 和 `answer_checks`。
- 路由/边界样本包含 `boundary_type`。
- 报告生成样本包含 `required_sections` 和 `artifact_expectation`。

## 路由标签

评测 runner 中使用以下标准路由标签：

- `network_search`
- `database_query`
- `knowledge_base`
- `file_read`
- `memory`
- `report_generation`
- `direct_answer`
- `refusal`

## 当前指标

- 路由准确率。
- 禁用路由违规率。
- 联网搜索结果覆盖和时效性。
- DB 查询可执行性和结果正确性。
- 报告章节覆盖和产物生成情况。
- 本地知识库检索命中情况。

## 历史结果快照（M0 之前）

最新本地结果：

- 联网搜索 QA：20/20 通过。
- DB 查询 QA：20/20 通过。
- 路由/拒答/边界：20/20 通过。
- 本地知识库 QA：20/20 通过。
- 端到端报告生成：8/10 通过。剩余失败样本为 `report_zh_004` 和 `report_zh_008`，两者都在生成最终 Markdown 产物前停止。

该快照来自旧版执行方式，未包含运行级 Budget 和结构化 Trace，不能与 M0 结果直接比较。

## 轻量版报告质量 Judge

`runners/run_report_quality_judge.py` 使用项目相同的大模型配置，对已生成的报告产物进行轻量版 LLM-as-a-judge 评分。

当前 judge 输入仅包括：

- 原始任务
- `required_sections`
- 生成的 Markdown 内容

当前版本还不会核查网页来源真实性、数据库数字准确性或 RAG 证据对齐。评分维度如下：

- 任务完成度：30 分
- 必需章节覆盖：20 分
- 可执行性：25 分
- 表达质量：25 分

运行命令：

```powershell
$env:UV_CACHE_DIR='.uv-cache'
$env:PYTHONIOENCODING='utf-8'
uv run python evals\runners\run_report_quality_judge.py --output evals\results\report_quality_judge_eval.json
```

当前 judge 结果：

- 10 条报告样本中，8 条已有 Markdown 产物并完成评分。
- 产物覆盖率：80%。
- 有产物样本平均分：99.75/100。
- 全部 10 条样本平均分，缺失产物按 0 分计：79.8/100。

## M0 Baseline、Budget 与 Trace

端到端报告 runner 现在默认使用任务自身的运行 SLO，并额外保留 15 秒清理时间，
不再使用一个与应用预算无关的固定超时。需要人为覆盖时仍可传入
`--timeout-seconds`。

```powershell
$env:UV_CACHE_DIR='.uv-cache'
$env:PYTHONIOENCODING='utf-8'
uv run python evals\runners\run_report_eval.py --execute-ready --output evals\results\report_eval.json
```

输出中的 `baseline` 包含：

- Trace 覆盖率
- P50/P95 端到端耗时
- LLM、工具、搜索查询和全文页面总量
- 按原因分类的失败数量

每条已执行样本同时带有完整 `research_trace`。达到预算后生成的降级结果使用
`degraded` 状态，不再计入正常 `passed`。

### 2026-08-17 M0 baseline

本轮共包含 10 条报告样本：

- 5 条 MySQL 样本因 `localhost:3307` 不可用而标记为 `blocked`。
- 5 条纯 Web 样本完成执行，但全部标记为 `degraded`。
- 5 条执行样本均未生成要求的 Markdown 文件。
- 已执行样本的 Trace 覆盖率为 100%。
- P50 为 131.2 秒，P95 为 208.3 秒。
- 共调用 LLM 99 次，使用 880,549 个输入 Token 和 23,166 个输出 Token。
- 共执行 52 个搜索查询，获得 75 个唯一候选来源，只读取了 6 个网页全文。

`average_score=42.5` 不是内容质量分数。半数样本没有执行，其余样本也没有生成要求的文件。本轮真正有效的 baseline 指标是 artifact completion、degraded rate、阶段失败、延迟、Token 使用量和全文阅读率。

详细分析与下一步 M0.1 验收目标见 [`docs/development/m0-baseline-budget-trace.md`](../docs/development/m0-baseline-budget-trace.md)。
