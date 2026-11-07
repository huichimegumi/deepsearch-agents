# 实习演示版第 1 步：HTTP 规范问答

在现有聊天页面勾选 **HTTP 规范问答**，提问 RFC 9110 / 9111 正文中的问题。答案中的章节链接指向 RFC Editor 原文。不需要个人 PDF；示例范围不包括附件、实时 Web 搜索、SQL 或跨轮记忆。

## 复现

1. 启动现有 API、前端、PostgreSQL、Qdrant、MinIO、Redis 和索引 worker。使用项目现有的模型配置，将生成模型设为 `qwen-flash`。
2. 在仓库根目录，用与服务相同的 RAG 配置执行 `uv run python -m scripts.seed_rfc_demo`。脚本优先读取本地 RFC 快照；缺失时下载固定原文，验证来源哈希，再标记章节并用现有导入器索引。原文和索引副本不进入 Git。
3. 在知识库页面确认 **HTTP 规范示例 · RFC 9110 与 9111** 的两份文档就绪。回到聊天页，勾选 **HTTP 规范问答** 并提交下表问题。

页面提交至现有 `POST /api/task`，通过 WebSocket 返回 Markdown。应用和后续评测使用同一个 `app.research.rfc_demo.run_rfc_qa`。普通提问复用词法与向量融合，最多八段；明确指出 RFC 和章节时，最多定位两个指定章节、各取八段。没有启用重排。请求至多调用一次 Writer；没有证据时可直接拒答。运行记录保存状态、证据、耗时、请求数及供应商返回的 token 用量。Writer 只输出段落编号，链接由后端解析；有效链接不等于内容得到语义支持。

## 真实界面验收

使用 Chromium 通过注册、勾选和提交操作，走实际 API、PostgreSQL/Qdrant、CPU embedding 和 qwen-flash。最终一轮三次模型调用；核对了下列官方 HTML 的章节锚点。

| 开发题 | 最后一轮结果 | 请求 / 秒 / 实际 token |
| --- | --- | --- |
| List only the four HTTP request methods defined as safe by RFC 9110. | 四种方法均正确，链接定位 RFC 9110 §9.2.1。 | 1 / 3.316 / 1,014 |
| According to RFC 9110 section 12.5.5 and RFC 9111 section 4.1, what does the Vary response header tell a recipient, and when may a cache reuse a stored response with Vary without revalidation? | 两个要点均覆盖，两份 RFC 的链接均存在；说明了字段匹配和通配符限制，回答仍偏长。 | 1 / 3.708 / 1,455 |
| What is the capital of Mongolia? | 告知本次检索片段证据不足，无虚构引用。 | 1 / 1.040 / 1,111 |

前三轮的问题没有计为通过：第一轮事实题格式失败，跨文档题漏检并格式失败，拒答正常；第二轮事实题和跨文档题能展示引用，拒答标记带句号被拒绝；第三轮宽泛事实题夹带了错误的 DELETE 例子，跨文档题的行内引用没通过旧检查，拒答正常。随后修正行内引用解析，并把演示事实题限定为只列所问四种方法。跨文档例子显式给出了章节，只验证联合使用两份文档的路径。普通问法下的跨文档召回、回答简洁性和引用支持度仍要单独评测。

这是重复使用的开发冒烟题，不是保留集或准确率统计。共进行四轮各三次生成，早期失败记录留在本地会话目录。没有调用 DeepSeek、使用 GPU、运行新评测集或改变 E13 成绩。下一步是准备小型参考答案与原文位置，供人工核对。

验证：集成版全量回归 838 通过、6 跳过；最后一次调整行内引用解析后，相关 10 项测试通过。前端 TypeScript/Vite 构建及本次改动的 Ruff、格式和 diff 检查通过。GitHub Actions 保持关闭。
