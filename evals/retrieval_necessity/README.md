# 2026 年公开事实检索对照

12 道题，中英各 6 道，每题 4–5 个事实判分单元。题目覆盖跨机构、跨赛事以及可从单一汇总页查证的结果，设计侧重检索广度。以 2026-11-14 为事实截止日。人工抽查逐项标准答案和出处后，从本地题目与答案文件生成冻结哈希。题目和参考答案在生成期间留在被 Git 忽略的结果目录，避免成为可被搜索到的答案页。

- **闭卷**使用单轮 Writer 的同一提示词，来源列表为空，零搜索。
- **A 单轮检索**最多生成 3 条 Tavily 查询，搜索一次，随后写作一次。
- **P 并行研究**使用 `parallel_web`、`deep_report` 和独占 Tavily，一题最多 12 条查询。

三组均用 Qwen Flash，温度 0，Writer 输出上限 8000 token。每个题组组合运行一次，保留失败结果与 P 组轨迹。事前预期闭卷正确率低、A 高于闭卷、P 在跨机构或跨赛事题上的正确率不低于 A。即使偏离预期也如实报告。题量支持诊断，实时搜索与单次运行限制了结论范围。

Qwen Max 逐项对照官方答案。每个判分单元仅在所有要求字段都正确时得 1 分，错答、缺答和 abstain 得 0 分。判分保留三个状态及理由，可接受同一实体的常见别名与翻译。聚合报告分子、分母，以及按题配对胜负和中英／广度拆分。本测试衡量给定公开事实的正确率，引用支持和长报告的组织质量需要各自的指标。

## 启动与监测

人工确认后先启动航天题 zh04 的三组冒烟，用 Tavily `/usage` 实测 key 的前后额度差，再与两组的查询次数对账。账户计数尚未更新时，可在同一题发一条显式 basic 查询，请求附带单次用量。该探针需要返回 1 credit，并计入 180 次上限。全量固定 basic，并记录成功请求的响应回执。冒烟数据计入正式集。进程启动、服务超时或中断都保留查询审计日志，累计封顶 180 次。断点续跑保留已经写完的报告和有效判分。

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

## 日期与分组修复复测

本轮预先记录三个预期。P 把已发生事件当作未来或尚未公布的失分项至多 2 项。P 的第 4 项正确数高于 1/12。P 总分明显高于旧结果 11/48，操作上按至少多答对 6 项记录。P 是否追上 A 只记录实测结果。时效失分按报告文本逐项复核，明确说未来、尚未举行或尚未公布才计入，仅写不确定或缺资料不计入。

用原题、原参考答案、原判分设置与原搜索预算。只重新生成及评分 A、P，闭卷生成和判分沿用原档。新 A 的 Writer 和新 P 全阶段共享 2026-11-14 日期提示。P 按原顺序将所有简报子问题分配到固定数量的子代理，并附原始任务。A 保存搜索词和 Writer 来源，P 额外导出结构化简报、证据记录、接受论断和压缩／写作实际入参。原始产物留在忽略目录。

修复从这 12 道题的失败中得出，本轮属于同题缺陷复测。搜索实时变化且多处一起修复，比较只描述此次运行的差异。

```bash
review=evals/results/retrieval-necessity-review
previous=evals/results/retrieval-necessity-2026
out=evals/results/retrieval-necessity-2026-repair
mkdir -p "$out"
cmd=".venv/bin/python -m evals.retrieval_necessity.run"
args="'$review' '$out' --previous '$previous' --as-of 2026-11-14"
tmux new-session -d -s retrieval-repair "$cmd generate $args > '$out/generate.log' 2>&1 && $cmd score $args > '$out/score.log' 2>&1"
```

## 网页抓取与子代理复测

事前预期是两组输入证据中的答案覆盖都上升，P 第 2 项正确数高于上轮 1/12。A 与 P 的排序以实测为准。

用 `--web-refresh` 另建结果目录，沿用原题、日期、评分器、闭卷归档与查询上限。A 保留搜索摘要与正文，P 每个研究员预留两次模型调用，在 `deep_report` 调度最多四个研究员。P 将摘要与网页正文按来源类型标注。抓不到正文时保留明确标记的摘要。解析 2 MB 限额内的整份 HTML，优先保留主体块；内容超过上限时按查询匹配选择段落。旧结果与同题复测独立存放。

另备 6 道未参与诊断的题，人工确认后用 `--holdout --web-refresh` 和独立目录各跑 A、P 一次。原题与独立题分别报告。
