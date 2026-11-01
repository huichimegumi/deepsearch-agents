# E6-1：实际 API 与评测共享有界执行

应用实现位于 `app/research/bounded.py`，不导入 evals。流程为真实 schema 描述 → 最多四个问题驱动请求 → 一次缺口补查 → 结构化 Writer；没有 benchmark ID 分支、固定好证据或递归委派。SQL 结果可以通过 `{{s0.column}}` 进入后续来源查询，必须解析出唯一值；SQL 替换值以转义字面量插入。只读 SQL、知识库检索、公开网页和费用计算复用现有适配器；快照文档/Web 使用 CPU 词法检索，并明确标注 snapshot_only。

请求账本迁入应用，历史 `evals.request_budget` 保留兼容导入。ContextVar 为并发任务隔离预算；预留最后一次 Writer 请求和 32k 估算 token。默认每任务最多 8 次模型请求、180k 预留 token，最多 5 次分析取证；取消向上传播。自动 HTTP 重试关闭，避免未记账的重复请求。数值必须绑定实际 Evidence content 字段；未知引用、缺引或绑定错误会保存失败状态并交付部分证据，而不是标为成功。规划/补查失败后仍尝试使用保留额度交付。模型返回用量按所有已记录阶段汇总，不完整时标为未知。

`app.api.server` 的真实任务入口调用 `app.research.service.run_research`。现有安装默认 legacy；配置 `RESEARCH_WORKFLOW=bounded`，或者在 `/api/task` 显式传入 `sources:["sql"]` 等来源限制即可进入共享新流程。会话目录、上传解析、对话保存与 monitor 交付事件保留。默认切换等待跨来源验证；显式来源集合在执行器中强制限制，不会因模型提议而扩张。

真实 HTTP smoke：`python -m evals.api_smoke_v4 --output evals/results/e6-1-api-final`。实际 FastAPI POST → 后台任务 → 真实 DeepSeek → 真实只读 SQLite → Markdown/JSON 文件 → assistant message，结果 HTTP 200、completed、正确 item_count=3、3 次请求、13,984 预留 token。测试身份和会话存储被隔离替换，未声称验证真实 PostgreSQL 登录、WebSocket 客户端或长期记忆。结果摘要位于 `evals/reports/e6-1-api-summary.json`。

验证：全套 730 passed、6 skipped；定向验证真实 SQL→Web 查询依赖、非法来源和写 SQL 拦截、并发请求预算隔离、Writer 保留请求、取消时不发布 completed。同步工具取消后可能仍在有限超时线程内结束；评测继续使用独立进程硬终止。全程 CPU、无付费搜索。下一阶段只在新的跨来源开发集上做一次集中复验。
