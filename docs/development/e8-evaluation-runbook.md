# E8 评测复现与停止规则

## 数据和服务

不依赖个人 PDF、不需要 GPU。公开 DABStep SQLite 和 Hybrid SQL/Web 资产沿用 E7 的固定来源、revision 与校验；冻结开发题从已暴露 E7 题中选取，清单为 evals/diagnostics/e8-dev.lock.json。题目、参考、SQL、原始模型/网页响应放在忽略目录 evals/results，不提交公开解密内容。数据路径沿用本机已准备资产，换机器需要按原数据准备流程 materialize；不能把本机绝对路径摘要当作跨机器相同文件内容的承诺。

生成器只读 public.json；references.json 仅评分端使用。模型密钥从本地环境配置读取，不进入报告。主生成器与主评分器为 DeepSeek Flash，免费 live Web；网页会变化，比较不等于确定性重放。开发只用 CPU，不占用任何 GPU。

## 操作顺序

1. `.venv/bin/python -m scripts.evaluate check`：离线检查，不访问模型或下载数据；Windows 用 `uv run python` 替换解释器前缀。
2. `.venv/bin/python -m evals.diagnostics.e8 --freeze --output evals/reports/e8-0-diagnosis.json`：校验并复用已有开发选择，输入变化即拒绝。
3. `.venv/bin/python -m scripts.evaluate public-run --inputs evals/results/e8-inputs/development/public.json --output RUN --workflow adaptive`：逐题有界 worker，最多 8 个请求、180k 预留 token、5 个工具、300 秒内部期限/330 秒进程硬期限。RUN 是新目录；续跑同目录只继续未开始题，不重做已中断/低分题。
4. `.venv/bin/python -m scripts.evaluate e8-score --run RUN --inputs evals/results/e8-inputs/development --output RUN/score-e8`：小批评分和独立 SQL 审计。原始结果/评分器/schema 变化禁止同目录恢复；需要新版本与新输出目录，不覆盖旧成绩。
5. `.venv/bin/python -m scripts.evaluate e8-gate --run RUN --score RUN/score-e8 --output RUN/gate.json`：开发至少 6/8 严格通过、引用 ID 合法且额度合规才允许准备新验证。
6. `.venv/bin/python -m evals.api_smoke_v4 --workflow adaptive --output SMOKE`，可加 `--web`：真实 HTTP→共享执行器→实际模型/来源→交付；认证与会话存储被隔离替换，因此不代表完整部署验收，也不代表语义正确率。

运行期间不修改 app、公开 benchmark runner 或 diagnostics 下的 Python 源码。worker 检测源码变化并停止，避免跨题混入不同实现。长任务应在独立进程会话运行并写日志，终态、模型额度、原始工具、上下文视图和被拒报告均保留。

## 质量门槛

严格成功需要 runtime completed、回答完整、必要来源齐全、数值路径正确、引用存在、覆盖率 >=0.8、逐条主张支持率 >=0.9；Hybrid 还必须实际 SQL 结果匹配与实际依赖方向正确。8 道已暴露题不能估计泛化性能；受控评分校准不能替代自然报告人工复核。

允许一次集中修复和一次整组复查。仍不足 6/8 时，输出失败诊断并停止新验证，不通过重试、更换题目、提高预算或放松评分凑出结果。门槛通过后才准备独立新题和冻结清单，进行同预算候选/基线比较；此前不提前消费新题。
