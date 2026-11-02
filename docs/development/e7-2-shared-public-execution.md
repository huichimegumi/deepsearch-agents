# E7-2：公开任务接入应用共享执行链

新增生成器专用任务投影和独立 references 文件，保存在忽略的 evals/results；worker 只读取 public.json。DABStep 获得真实 SQLite 和完整商户手册，Hybrid 获得 alien 实库及通用语义说明，DRB 使用实时免费 Web。没有按题注入 SQL/gold Evidence。元数据、代码、依赖锁、数据库与输入摘要写入 manifest，源变化拒绝恢复；终态不重跑，中断保留预留费用。每题进程硬截止 330 秒。

应用 Step 增加显式 depends_on。SQL→Web 继续后端占位符替换；Web→SQL 在取回页面后，用一次有预算的结构化请求构造 SQL，并核对绑定值确实出现在父步骤 Evidence 和实际 SQL 中，不能提前硬编码搜索答案。schema_notes 为通用源说明，不是题目 oracle。两个流程共享这些真实工具，仅 bounded 额外补查一次。

五个旧公开开发题初跑 3/5 正常交付：两个 DABStep 报告在结构化上限失败。做一轮集中修复：Writer 明确限制声明/数值/引用数量；格式失败最多修复一次，沿用已有证据，不重取证、不中途扩预算，原始失败候选保存。另发现模型默认输出上限可覆盖 bind 的阶段上限，修正为发送前规范化 provider 字段，再按实际 payload 预留额度；两种适配器均有回归验证。复验 5/5 completed，不代表内容都正确，评分留 E7-3；未运行新验证题。

完整测试 744 passed、6 skipped，Ruff 通过。摘要见 evals/reports/e7-2-development.json，仅发布 ID/运行状态/资源，不公开 Hybrid 解密原题、答案或诊断文本。统一 CLI 增加 public-preflight/public-prepare/public-run。CPU，开发 Hybrid 为实际免费搜索；无付费搜索或 GPU。
