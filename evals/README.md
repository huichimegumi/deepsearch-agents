# 项目评测集

本目录包含 DeepSearch Agents 第一阶段的项目内中文评测集，覆盖路由、联网搜索、数据库查询、本地知识库检索和端到端报告生成。

此外，`hybrid/` 提供固定版本的 HybridDeepResearch 三题 smoke 子集，分别覆盖
Search-to-SQL、SQL-to-Search 和 Parallel Fusion。它默认只使用 DuckDuckGo，每题最多两个
搜索查询和两个抓取页面；Tavily、Perplexity、auto 或 advanced 模式必须显式传入
`--allow-paid-search`。该子集只用于检查跨来源执行链，不是可与官方 380 题结果比较的分数。
详细说明见 [`hybrid/README.md`](hybrid/README.md)。

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

- 规则路由一致率、规则基线的禁用路由违规率（不调用 Agent）。
- 搜索结果非空率（不验证答案或时效性）。
- 参考 SQL 可执行率（执行 gold_sql，不评估模型生成 SQL）。
- 报告产物与运行状态；现有 Judge 仅评文本表达与结构。
- 文件名命中率 @8（不验证答案证据片段）。

## E3.7：统一版本的六题本地报告基线

已在干净 `33e91f08`、默认研究路由与固定配置下完整执行六题，每题一次，保留所有降级：1 completed、5 degraded，中位耗时 95.852 秒；2 份报告、3 份 Claim 回退包、1 份零证据说明。离线 `baseline_summary` 将机械指标与带真实报告／证据／Claim 引文的 AI 初审并列，拒绝漏题或篡改材料，人工正确率保持为空。430 项测试通过、6 项跳过；无 Tavily 查询。见 [完整结果表、错误归因及锚点漏标限制](../docs/development/e3-7-six-task-local-baseline.md)。下一阶段补四个 Web／简单跨源任务，不再以人工全量裁定作为实跑前置条件。

## E3.6：人工标注、裁定与结果汇总

`python -m evals.reports_acceptance.adjudication` 提供 `init`／`validate`／`summarize`：从保存审核包生成待填模板，校验逐段真实引文、错误标签和修正建议，显式裁定需绑定并重新校验初始标注。汇总区分待审、裁定、分歧、参考标签不确定及分母排除项，无有效裁定时通过率为 `null`。已准备三份真实报告的待审批次，未代填人工结论；418 项测试通过、6 项跳过，无模型／检索调用。见 [操作步骤与统计边界](../docs/development/e3-6-human-adjudication.md)。

## E3.5：本地缺失结论措辞检查与离线回放

`replay_sources --policy absence_scope` 在核验保存报告／Evidence 哈希后单独回放新交付检查，不重新检索或生成。八份历史报告中，上一轮负样本的两处明确全库缺失表达被拦截，正样本不变；旧负样本的另一类表达仍漏检。未命中不表示支持，拦截说明也不计为语义正确拒答。380 项回归通过、6 项跳过，无模型／搜索调用，实验路由仍默认关闭。见 [规则与已知漏检](../docs/development/e3-5-local-absence-scope.md)。

## E3.4：本地研究能力与补检索预算实验

报告 runner 的 `--indexed-local` 显式启用默认关闭的专用路由：只有固定本地来源的 Evidence 工具，最多 2 次补检索，保留原有首次取证及全局预算。两个试验分别记录“只移除无关工具仍查询 9 次并超时”和“增加上限后约 56／53 秒但均限额降级”。负样本仍有未支持的全库断言，因此没有默认启用、没有语义通过率。见 [完整门槛与限制](../docs/development/e3-4-indexed-local-agent.md) 和 [独立记录](reports/e3-4-indexed-local-agent-2026-10-24.json)。

## E3.3：本地来源身份交付边界

生产流程增加实际文件名来源清单与显式文件名校验；回退稿也会检查。新增 `python -m evals.reports_acceptance.replay_sources --report-results ... --case-id ...`，仅对保存材料重放同一身份规则，不调用模型／数据库／检索，不改写历史报告。旧负样本的 5 个未核验文件名会被拦截，正常对照原文不变；这不是语义验收、全面幻觉率或当前完整工作流的答案正确率。见 [实现与验证](../docs/development/e3-3-local-source-provenance.md)。

新生成 002/006 均降级，没有新的文件名拦截；006 零取证触发既有 `no_evidence` 边界。身份拦截分支由历史材料重放及集成测试验证，不能算作在线拦截成功。独立 [记录](reports/e3-3-source-provenance-2026-10-24.json) 保留两类结果；人工语义验收仍未完成。

## E3.2：证据支持审核基础

新增 `python -m evals.reports_acceptance.support_review --report-results ... --case-id ...`：默认不调用模型，生成完整报告／实际引用片段／文档目录候选项的人工复核包。可选 `--execute-judge` 意见需要通过逐字引文、实际引用绑定、逐段完整性校验；`--segment-id` 子集禁止全文覆盖和拒答评分。首轮 3 次整报告与 3 次逐段模型审核均无效或超时，没有可采信的自动支持率；人工语义验收仍待完成。见 [实测与限制](../docs/development/e3-2-evidence-support-review.md) 和 [无原文汇总](reports/e3-2-support-review-2026-10-19.json)。

## E3.1b：引用格式规范化与离线重放

仅对完整的一层 `[ev1_…]` 且内部 ID 已在允许清单中的引用去除包装；未知 ID、多 ID、附带文本等仍拒绝。评测模式额外保存原始结构化 Claim 与当时允许清单，可用 `python -m evals.reports_acceptance.replay_claims --report-results ...` 在同一批输入上对照旧规则和新规则，不额外调用模型或检索。旧快照缺少结构化 Claim 时明确拒绝重建；结构校验通过不代表证据支持或报告正确。见 [开发记录](../docs/development/e3-1b-canonical-claim-references.md)。

仅重跑 001/002，两个引用校验均通过；001 仍调用预算降级、002 正常完成。同输入离线重放中，旧格式规则拒绝全部 9 条，新规则结构通过 9 条（14 个已知包装引用）。这不代表语义验收，也不替换原六题结果。见 [独立记录](reports/e3-1b-claim-reference-replay-2026-10-19.json)。

## E3.1：真实本地报告验收

E3.1a 增加强制本地取证和无证据报告边界，runner 保存新的 `local_retrieval` 状态。仍使用同一组 6 题开发任务作前后对照，不修改 gold、检索参数或模型；实际取回证据不等于回答正确。边界定义、预算与线程超时限制见 [开发记录](../docs/development/e3-1a-required-local-retrieval.md)。

实跑 12 次强制本地检索后，有答案题零取证从 2/5 降到 0/5，执行结果为 3 completed、3 degraded；这不是报告验收通过率。负样本补检索取得无关片段后仍输出无依据的文档目录，不能计为正确拒答。原始基线不覆盖；新 [前后对照](reports/e3-1a-local-retrieval-2026-10-19.json) 保留独立记录，人工语义复核仍待完成。

新增 `python -m evals.reports_acceptance.run --execute`，执行 6 个固定开发任务（4 个单文档、1 个跨文档、1 个无答案）。完整报告与 Evidence 正文、引用核验、参考要点、未勾选的人工复核表均保存到独立且被忽略的运行目录。提示不注入参考答案；搜索/抓取预算均为 0。ID 有效、参考证据取回和被引用分别统计，不据此自动判定事实正确；答案准确率保持空值，验收仍待人工复核。见 [使用说明](reports_acceptance/README.md) 与 [开发记录](../docs/development/e3-1-local-report-acceptance.md)。余下 2 个 Web、2 个简单跨源任务属于后续 E3 范围。

## E1/E2：评测运行基础与 RAG 实验

E2 保留了首轮 5 题 RAG 开发实验，并扩展为 v2 的 20 条开发题与 10 条新查询测试题。首轮 v1 锚点 Recall@5 为 A 0.25、B 1.00、C 0.25，但复核发现漏标的等价证据；仅用 v2 对同一批已保存片段重评分，C 即变为 1.00。这个变化来自标注修正，不是模型改善。v2 在实跑前冻结数据、语料、模型文件及检索配置；全部标注仍待人工复核。见 [RAG 实验说明](rag/README.md)、[首轮原始记录](reports/e2-rag-pilot-2026-10-18.json) 与 [v2 分析](../docs/development/e2-rag-suite-v2.md)。

v2 的 90 次配置运行全部有效。19 条有答案开发题的 A/B/C Recall@5 为 0.158/0.500/0.675；8 条有答案测试题为 0.625/0.500/0.875。无答案题共 3 条，单独记录，不纳入 Recall/MRR。两个新测试多文档题在 C 中都只召回一半必需证据，后续报告验收应重点检查其证据缺口。逐题数据见 [开发集结果](reports/e2-v2-dev-2026-10-18.json)、[测试集结果](reports/e2-v2-test-2026-10-18.json)；人工复核见 [清单](rag/suites/v2/REVIEW.md)。

复杂 Hybrid 子集当前仅用作开发诊断。近期主实验为 RAG 证据级 A/B/C 对照，其次为约 10 条真实报告验收。
上述旧 runner 的兼容字段保留，并新增 `measured_metric` 明确实际口径。

报告 runner 现在为每次调用生成唯一 `run_id`，每题也使用独立 session，不再清理上次报告和日志。
CLI 默认输出到 `evals/results/<run_id>/report.json`；显式输出文件已存在会拒绝覆盖。
manifest 记录代码版本/dirty 状态、数据和依赖锁哈希、模型、配置及依赖版本，不记录密钥。
现有报告提示仍注入数据源约束，manifest 将此模式标为 `source_constrained_legacy_not_autonomous_routing`。
Trace Token 仅代表当前被埋点的模型调用，不视为完整供应商计费统计。

```powershell
.venv\Scripts\python.exe -m evals.runners.run_report_eval --execute-ready
.venv\Scripts\python.exe -m evals.runners.run_report_quality_judge --report-results evals/results/<run_id>/report.json --output evals/results/<run_id>/text_judge.json
```

未提供 `--report-results` 的 Judge 仍读取旧路径，仅用于兼容历史记录。新实验应始终指定运行结果。
SQL 实体恢复预留现在由 `run_deep_agent(sql_entity_recovery_enabled=True)` 显式启用，Hybrid runner 已接入；普通 Web clue 任务不会预留额度。
零时间的流式和直接模型阶段都不会发起模型调用。重排记录 `rerank_model`、`rerank_applied` 和 `rerank_error_type`，随本地 Evidence 传递；退化记录不能作为真实重排效果。

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

### 2026-08-17 M0.1 Trace 复测

M0.1 修改后重新执行了 5 条纯 Web 报告样本。MySQL 仍未运行，因此另外 5 条样本继续标记为 `blocked`。

本轮命令生成了新的 schema v2 Trace 和报告文件，但没有完成 `evals/results/report_eval.json` 的最终覆盖。该 JSON 仍是 19:45 生成的 M0 旧汇总。下面的数据直接来自 `app/output/user_evals/session_eval_report_zh_*/research_trace.json`，不要与旧 JSON 中的 schema v1 指标混用。

- 1 条正常完成，4 条因 Supervisor 或 Compression 超时而降级。
- 5 条样本都生成了非空 `report.md`。
- Clarify 全部缩减为 1 次 LLM 调用，未再超时或调用工具。
- 平均 LLM 调用为 9.2 次，较 M0 下降 53.5%。
- 平均输入 Token 为 76,843，较 M0 下降 56.4%。
- P50 为 199.6 秒，P95 为 216.6 秒，延迟目标未通过。
- 60 个搜索查询中有 12 个重复查询，19 个查询没有带来新来源。
- 只有 `report_zh_009` 抓取了网页全文，其余 4 条样本仍只使用搜索摘要。

当前 artifact 判断还有一个已知误差。评测提示中的 `convert_md_to_pdf` 工具名称被运行时误判为 PDF 请求，导致 5 条 Markdown-only 样本都额外生成了 PDF。按 `_artifact_matches_expectation()` 的严格规则，这些样本仍不满足格式要求。

本轮没有发现未配置的子智能体类型，但 Research 阶段仍调用了 `write_todos`、`write_file` 和 `read_file`。最终报告 URL 与审计日志记录的 `search_result.top_results` 没有精确重合，说明下一步评测必须增加引用来源约束，不能只检查文件和章节是否存在。

完整分析和 M0.2 建议见 [`docs/development/m0-baseline-budget-trace.md`](../docs/development/m0-baseline-budget-trace.md)。
