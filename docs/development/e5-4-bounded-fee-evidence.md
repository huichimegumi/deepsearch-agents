# E5-4：有界费用证据复验（2026-11-01）

P3 显示原 agent 在六个 SQL 开发题上对两个模型均耗尽预算，而一次取证＋一次 Writer 能交付。该简单链路对手续费量化题仍缺少已计算的费用分解。本阶段只改一类变量：为现有只读 SQL 证据补充确定性费用汇总，不改变模型、评分阈值或任务集合。

`evals/dabstep/fee_aggregates.py` 从锁定的公开 DABStep 交易和规则，以已有 `FeeDataset` 的匹配器及 Decimal 公式计算商户、ACI、卡组织、是否境内、商户×ACI 五个维度。生成时与已提交的独立费用引擎参考总额精确核对；每组同时记录交易数、已匹配数、未定价数、交易额、已匹配规则手续费及欺诈争议数。`evals/dabstep/fee_aggregates.json` 是版本固定的计算产物。Writer 收到五个内容寻址的 `fee_engine` Evidence ID，提示明确把未定价交易视为未知费用，不宣称观察差异具有因果性，也不凭空编造节省金额。全部在 CPU 运行。

同一八题、DeepSeek non-thinking、同一 330 秒硬超时及 P2 评分规则复验：旧版 8/8 运行完成、5/8 暂定通过、平均要点覆盖 0.847、p50 28.0 秒；新版 8/8 运行完成、**7/8 暂定通过**、平均要点覆盖 0.922、p50 27.0 秒。`003` 从 0.71 升至 0.93，`041` 从 0.50 升至 0.90；`002` 从 1.00 降至 0.92，其余仍通过。新增证据使生成器记录 token 从 104,424 增至 134,802；裁判 token 从 323,659 增至 414,189。所有交付引用 ID 均能解析。

`020` 仍为 0.71，未通过：现有证据可比较费用和欺诈分布，但不能给出有效的成本节省反事实测算；报告明确拒绝虚构节省额。此轮按计划停止，不为该题继续调整提示或评分。费用总额只覆盖能匹配规则的交易，56,464 笔未定价交易不可当作零手续费；汇总观察也不能作为改变路由或 ACI 后的因果估计。

复现：先运行 `python -m evals.dabstep.fee_aggregates`，再按 `evals/reports/e5-4-bounded-fee-manifest.json` 中八题与配置运行 `python -m evals.run_v3 --workflow simple_sql --profile deepseek`，最后 `python -m evals.score_v3 --run <run目录> --judge deepseek`。正式运行 `benchmark_v3_20261101T115306Z_3a9669ef`，源码摘要 `adb70c106a6a80b081daaa02911cf665a1f12cecdb6a4a23c0f9014d5e5cf59a`；已发布 manifest、结果、分数与报告于 `evals/reports/e5-4-bounded-fee-*`。原始 trace 留在忽略目录。

验证：费用汇总每一维都与参考交易数、未定价数和总额核对；Evidence ID 唯一性检查通过；全套离线测试 721 passed、6 skipped；Ruff check 通过。评分仍由生成器同族 DeepSeek judge 三次复评，尚未经人工审核。八题均是已暴露的开发题，不能当独立泛化成绩。原计划的本地 PDF 不在本机；Hybrid 三题是另一个公开跨源 smoke，未混入这八题的分母。下一阶段应一次性冻结新公开任务作独立验证。
