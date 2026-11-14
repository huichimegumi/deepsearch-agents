# 2026 年公开事实检索对照

12 道题，中英各 6 道，每题 4–5 个事实判分单元。题目覆盖跨机构、跨赛事以及可从单一汇总页查证的结果，设计侧重检索广度。以 2026-11-14 为事实截止日。人工抽查逐项标准答案和出处后，从本地题目与答案文件生成冻结哈希。题目和参考答案在生成期间留在被 Git 忽略的结果目录，避免成为可被搜索到的答案页。

- **闭卷**使用单轮 Writer 的同一提示词，来源列表为空，零搜索。
- **A 单轮检索**最多生成 3 条 Tavily 查询，搜索一次，随后写作一次。
- **P 并行研究**使用 `parallel_web`、`deep_report` 和独占 Tavily，一题最多 12 条查询。

三组均用 Qwen Flash，温度 0，Writer 输出上限 8000 token。每个题组组合运行一次，保留失败结果与 P 组轨迹。事前预期闭卷正确率低、A 高于闭卷、P 在跨机构或跨赛事题上的正确率不低于 A。即使偏离预期也如实报告。题量支持诊断，实时搜索与单次运行限制了结论范围。

Qwen Max 逐项对照官方答案。每个判分单元仅在所有要求字段都正确时得 1 分，错答、缺答和 abstain 得 0 分。判分保留三个状态及理由，可接受同一实体的常见别名与翻译。聚合报告分子、分母，以及按题配对胜负和中英／广度拆分。本测试衡量给定公开事实的正确率，引用支持和长报告的组织质量需要各自的指标。

## 启动与监测

人工确认后先启动航天题 zh04 的三组冒烟，用 Tavily `/usage` 实测 key 的前后额度差，再与两组的查询次数对账。冒烟数据计入正式集。进程启动、服务超时或中断都保留查询审计日志，累计封顶 180 次。断点续跑保留已经写完的报告和有效判分。

```bash
review=evals/results/retrieval-necessity-review
out=evals/results/retrieval-necessity-2026
mkdir -p "$out"
cmd=".venv/bin/python -m evals.retrieval_necessity.run"
$cmd validate "$review" "$out"
tmux new-session -d -s retrieval-necessity-pilot "$cmd pilot '$review' '$out' > '$out/pilot.log' 2>&1"
```

核对 `pilot.log` 和 `pilot_usage.json`，确认 `passed` 为 true 后启动其余生成和判分。查询日志及逐题状态可用于诊断运行。

```bash
tmux new-session -d -s retrieval-necessity-full "$cmd generate '$review' '$out' > '$out/generate.log' 2>&1 && $cmd score '$review' '$out' > '$out/score.log' 2>&1"
```
