# E5.1 公开基准独立执行器

日期：2026-11-01。

新入口 `python -m evals.run_v3` 在父进程先校验已锁定的 DABStep/Hybrid 资产，然后逐题启动独立 worker。每题固定保存 stdout、stderr、worker_result、结果行与状态汇总；`--resume-run` 只跳过已有终态，未完成的题建立新 attempt。当前串行执行。父进程在每题 deadline 到达时先发终止信号，最多再等五秒，仍存活则强制终止进程组。评测环境禁用 GPU、锁定 DuckDuckGo，并移除付费搜索密钥。模型配置固定 `deepseek-flash` 或 `qwen-flash`；评测 SDK 的隐式重试关闭。

运行示例：

```bash
.venv/bin/python -m evals.benchmark_preflight
.venv/bin/python -m evals.run_v3 --case-id s2sql_041 --profile deepseek
.venv/bin/python -m evals.run_v3 --case-id s2sql_041 --profile deepseek --resume-run evals/results/<run_id>
```

`evals/results/`、运行 Trace 与解密的 Hybrid 题目均不进入 Git。Manifest 保存源码、依赖锁、语料选择的哈希。Hybrid gold 只参与本地分数计算，不进入 prompt 或公开报告。DABStep 使用只读 SQLite；原商户手册和表结构说明作为公共题目上下文提供。私有 PDF 不参与。

验证：Linux 故障注入覆盖忽略 SIGTERM 的永久等待、异常退出、缺失可执行文件，以及 timeout 后继续下一题和 resume 幂等；Windows 实机 CI 尚未运行。当前主机的 GPU 已被其他作业占用，本轮 CPU 运行。一次真实 DeepSeek Hybrid `s2sql_041` 在 57.466 秒内达到 `degraded` 终态：SQL 和网页 Evidence 均有记录，但没有生成正确的最终 SQL，报告被交付守卫拦截。一次 DABStep `002` 用缩短的 120 秒外层 deadline 验证了超时终态和日志保存；它不是正式 330 秒评分样本。

当前未完成的运行治理：对子 agent 所有请求的发送前预算准入、token/HTTP attempt 账本、跨 worker 的全局付费额度，以及 Windows CI 的实际运行结果。新执行器先保证批次能终止、保留失败，并在下一阶段以完整评分基线暴露这些问题。正式成绩必须显式披露这些限制。
