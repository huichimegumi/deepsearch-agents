# E6-4：可复现的 CPU 评测入口与故障恢复

统一入口为 `python -m scripts.evaluate`，支持离线检查、锁定语料准备、执行/恢复、保存答案评分、纯机械审计和对比报告。详细命令、费用边界和结果解释见 `docs/evaluation-v4.md`。离线检查不需要模型密钥、原个人 PDF、benchmark 下载或 GPU。新增 Linux/Windows Actions 矩阵；真实模型 API smoke 只允许手动触发并显式开启。

恢复时读取每个 attempt 的持久请求账本，保留中断前的 token 预留，不自动重复可能已付费的研究。追加前截断未完成的末行，避免下一条请求与半行 JSON 粘连；完整 fsync 行继续计费。故障注入覆盖半行、中断 worker、worker 已完成而父进程尚未写汇总三种场景。无效引用交付额外保留被拒绝的原始结构化候选和原因，最终报告使用简明失败说明；没有放宽评分门槛或重跑 holdout。监控结束事件的运行结果使用 runtime_status，避免覆盖阶段结束标记。

独立实时 Web 探针四次免费 DuckDuckGo 查询均取得页面，无模型请求；见 `evals/reports/e6-4-live-web.json`。这只表明当前检索可用，不能代表页面质量或答案正确率。E6-3 的 snapshot-only 成绩保持原样。兼容默认仍为 legacy，新执行链通过 RESEARCH_WORKFLOW=bounded 或显式来源列表启用。

本地 CPU 离线契约检查：26 passed。完整本地测试：737 passed，6 skipped。实际 CI 结果在阶段完成后补记。
