# E5-3：模型与流程配对对照（2026-11-01）

本阶段回答一个开发问题：评测无法稳定跑完，主要是 Qwen Flash 的写作能力，还是原 agent 的运行流程？冻结六个公开 DABStep Research 开发题及同一个 SQLite 快照，在 `deepseek-flash`、`qwen-flash` 与「固定 SQL 证据＋一次 Writer」、「原 agent」之间做 2×2 对照。六题此前已在开发中暴露，**不是独立 holdout**；本机没有旧 PDF，故原计划中的本地/Web 混合配对无法执行，这一结论只覆盖公开 SQL 研究题。

## 执行条件

- 四个 run 的 `source_sha256` 均为 `6c0821be47f4002c5be542a548e5176a52272e25605453a1ee1984a183ac710a`，案例、数据库和预检输入一致。两次简单流程的每题 Evidence 序列逐字节相同；原 agent 保持相同来源限制和只读 SQL，不强制命中固定证据。
- 每题硬超时 330 秒，模型最多 10 次请求、180,000 **估算预留** token；批次上限 1,500,000。请求发送前以序列化 prompt 的 `cl100k_base` 估算输入，加上输出上限，写入 `model_requests.jsonl` 并 fsync。它是预算准入和上界估计，不能当作供应商精确计费 token；HTTP 重试被禁用，进程中断时实际使用量仍可能缺失。账本不存 prompt。
- DeepSeek 与 DashScope 都把 LangChain 的 `max_completion_tokens` 映射为供应商接受的 `max_tokens`；评测温度 0。实测 Qwen 修复前对 `max_tokens=16` 返回 936 输出 token，修复后按 16 截断。每个 worker 强制 CPU；没有调用付费网页搜索，也没有使用被占用的 GPU。
- 评分规则沿用 P2：`completed`、三次 DeepSeek judge 的要点覆盖中位数至少 0.80、证据支持覆盖至少 0.75、引用 ID 100% 可解析。相同 DeepSeek 担任两个模型的裁判，因此语义分数仍为暂定；没有人工复核。

## 结果

| 模型 | 流程 | 终态 | 完成 | 暂定通过 | p50 秒 | 模型请求 | 预留 token |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DeepSeek | 固定证据 Writer | 6/6 | 6/6 | 4/6 | 27.6 | 6 | 102,753 |
| Qwen | 固定证据 Writer | 6/6 | 6/6 | 3/6 | 42.7 | 6 | 102,753 |
| DeepSeek | 原 agent | 6/6 | 0/6 | 0/6 | 33.1 | 34 | 899,548 |
| Qwen | 原 agent | 6/6 | 0/6 | 0/6 | 54.1 | 51 | 968,193 |

固定证据下，平均要点覆盖分别为 DeepSeek 0.765、Qwen 0.768。DeepSeek 比 Qwen 多一题越过通过阈值（`dabstep_research_003`），但两者都在 `020`、`041` 的手续费量化与商户策略上不足。六题不足以推断普遍模型优劣；共享裁判还可能偏向 DeepSeek。原 agent 两模型六题全部在进一步请求发送前触及预算，均未交付答案，因此内容评分为缺失，绝不从分母删除。它并非供应商故障，也不意味着模型生成了零 token：agent 报告的 `generator 0` 是旧 trace 未返回 token 用量；请求账本证明已有 34 / 51 次真实准入调用。

这一对照支持先修流程：把任务按源做有界取证、给 Writer 足够且相关的证据、一次交付；不能靠换模型解决反复编排的成本。固定证据 Writer 仍不足以完成手续费类题，下一轮重点加入确定性费用汇总和可引用的原始计算证据。只做一次主要改动，并对同一开发题复验，结果欠佳也不继续逐题调参。

## 复现与边界

比较器：`python scripts/compare_v3.py --run <deepseek-simple> --run <qwen-simple> --run <deepseek-agent> --run <qwen-agent> --output evals/reports/e5-3-paired-comparison-2026-11-01.md`。四个 run ID、逐题状态、manifest、打分与矩阵位于 `evals/reports/e5-3-*`；原始 prompt、trace 和请求账本在本机忽略的 `evals/results/`。比较器拒绝配置不一致或固定证据不相同的输入。

验证：`pytest -q` 为 719 passed、6 skipped；更改文件的 `ruff check` 与 `ruff format --check` 通过。GPU 未分配；Windows CI 未实际运行（推送凭据缺少 workflow scope）。
