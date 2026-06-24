# DeepSearch Agents

基于 DeepAgents 的对话式多智能体深度研究系统。项目现在已经不只是“提交任务、调用搜索、生成报告”的演示，而是具备了用户登录、历史会话、短期执行记忆、长期用户记忆、知识库管理、附件读取和多源检索的完整研究工作台。

![DeepSearch Agents 首页](docs/images/deepsearch-agent-home.jpg)

## 主要功能

- 多智能体研究：主智能体负责规划、调度和汇总，网络搜索、数据库查询、本地知识库三个子智能体分别处理不同信息源。
- 多源检索：支持 Tavily、DuckDuckGo、Perplexity、SearXNG、MySQL，以及基于 PostgreSQL、Qdrant、MinIO、Redis 和 FastEmbed 的本地 RAG。
- 用户与会话：提供注册、登录、JWT 鉴权、会话列表、历史消息恢复、会话归档和按用户隔离的数据目录。
- 记忆系统：包含当前会话摘要、最近消息上下文、LangGraph 短期 checkpoint，以及可由用户管理的长期记忆。
- 文件处理：支持读取 PDF、Word、Excel、Markdown 和文本附件，并生成 Markdown、PDF 等交付文件。
- 实时任务状态：通过 WebSocket 推送工具调用、子智能体执行、最终结果、异常和取消事件。
- Web 工作台：前端提供聊天、任务事件流、附件上传、知识库管理、长期记忆抽屉、历史会话侧栏和结果下载。
- 审计日志：任务开始、结果、取消、异常等事件会按会话写入 `app/logs/session_*.jsonl`，便于排查执行过程。

## 系统架构

项目采用 Orchestrator-Workers 模式，并把会话、记忆和检索状态持久化到本地基础设施中：

```text
用户登录 / 前端会话
  -> FastAPI 鉴权并创建 thread_id
  -> 注入历史会话摘要、最近消息和长期记忆
  -> DeepAgents 主智能体规划任务
  -> 调度网络搜索 / MySQL / 本地知识库 / 上传附件 / 记忆工具
  -> LangGraph checkpoint 保存同一 thread 的短期执行上下文
  -> 主智能体汇总答案并生成 Markdown 或 PDF
  -> WebSocket 实时推送过程和结果
  -> 写入历史消息、更新会话摘要、抽取长期记忆
```

核心技术栈：

| 模块 | 技术 |
| --- | --- |
| 智能体 | DeepAgents、LangChain、LangGraph |
| 后端 | FastAPI、Uvicorn、WebSocket、Celery |
| 认证与会话 | JWT、passlib/bcrypt、SQLAlchemy |
| 网络搜索 | Tavily、DuckDuckGo、Perplexity、SearXNG |
| 结构化数据 | MySQL |
| 本地知识库 | PostgreSQL、Qdrant、MinIO、Redis、FastEmbed |
| 记忆 | PostgreSQL、Qdrant、LangGraph checkpointer |
| 前端 | React、TypeScript、Vite、Ant Design、Tailwind CSS |
| 依赖管理 | uv、pnpm |

## 记忆与会话机制

项目里有几类“记忆”，用途不同：

- 历史会话：`chat_conversations` 和 `chat_messages` 存储每个用户的会话、消息、标题和归档状态，前端可恢复历史聊天。
- 会话摘要：任务结束后会维护当前 thread 的滚动摘要，并在下一轮同一会话中注入提示词，适合保留目标、结论、约束和待办。
- 最近消息：每轮执行会带入当前会话最近若干条消息，避免模型只看到本轮问题。
- 短期 checkpoint：LangGraph checkpointer 按 `user_id__thread_id` 保存智能体图状态，默认使用 PostgreSQL；不可用时可按配置退回进程内存。
- 长期记忆：`user_memories` 存储稳定偏好、事实、项目背景、指令和摘要，并同步到 Qdrant 做语义召回；前端“长期记忆”抽屉可新增、搜索和删除。

长期记忆保存前会过滤明显的 API key、密码、token 等敏感内容。Agent 可以在用户明确要求“记住”时调用 `remember_user_memory` 工具保存记忆；每次任务开始时会按当前问题检索相关长期记忆并注入上下文。任务完成后，系统也会尝试从本轮对话中自动抽取最多 5 条稳定记忆。

相关环境变量：

```dotenv
MEMORY_QDRANT_COLLECTION=user_memories
MEMORY_TOP_K=6
MEMORY_MIN_CONFIDENCE=0.55
SHORT_TERM_MEMORY_BACKEND=postgres
SHORT_TERM_MEMORY_DATABASE_URL=
SHORT_TERM_MEMORY_POOL_SIZE=8
SHORT_TERM_MEMORY_FALLBACK_ENABLED=true
```

`SHORT_TERM_MEMORY_DATABASE_URL` 为空时复用 `RAG_DATABASE_URL`。如果希望调试时完全不持久化短期 checkpoint，可设置 `SHORT_TERM_MEMORY_BACKEND=memory`。

## 项目结构

```text
deepsearch-agents/
├── app/
│   ├── agent/              # 主智能体、子智能体、模型和提示词加载
│   ├── api/                # FastAPI、WebSocket、会话、知识库、健康检查和审计
│   ├── auth/               # 注册、登录、JWT 和当前用户依赖
│   ├── memory/             # 长期记忆、会话摘要和 LangGraph checkpoint
│   ├── prompt/             # 智能体提示词配置
│   ├── rag/                # 文档解析、索引、检索、存储、模型和 Celery 任务
│   ├── search/             # 多搜索后端、降级、聚合和正文抓取
│   ├── tools/              # 搜索、数据库、RAG、附件、记忆和报告工具
│   └── utils/              # 路径及文档转换工具
├── docker/                 # Dockerfile、Compose 和 MySQL 初始化数据
├── docs/knowledge_base/    # 示例知识库文档
├── frontend/               # React 前端
├── tests/                  # 自动化测试
├── .env.example            # 环境变量示例
└── pyproject.toml          # Python 项目配置
```

## 环境要求

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker 和 Docker Compose
- Node.js 与 pnpm
- OpenAI 兼容的大模型 API
- 可选搜索服务凭据：Tavily、Perplexity 或 SearXNG。DuckDuckGo 无需 API Key。

## 快速开始

### 1. 获取代码并配置环境

```bash
git clone https://github.com/huichimegumi/deepsearch-agents.git
cd deepsearch-agents
cp .env.example .env
```

Windows PowerShell 可使用：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，至少配置模型地址、模型名称和密钥：

```dotenv
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_NAME=qwen-max
DASHSCOPE_API_KEY=
OPENAI_API_KEY=
```

使用 DashScope 时优先配置 `DASHSCOPE_API_KEY`；其他 OpenAI 兼容服务可配置 `OPENAI_API_KEY`。宿主机同名变量优先于 `.env`，Docker Compose 会将最终值传入 API 容器。

搜索后端默认为自动降级模式：

```dotenv
SEARCH_BACKEND=auto
SEARCH_BACKEND_ORDER=tavily,searxng,duckduckgo,perplexity
TAVILY_API_KEY=
PERPLEXITY_API_KEY=
SEARXNG_URL=http://localhost:8888
```

未配置的搜索后端会被自动跳过。其余 RAG、记忆、MySQL 和搜索参数可参考 [`.env.example`](.env.example)。

### 2. 启动后端服务

使用 Docker Compose 启动 API、RAG Worker 和全部基础设施：

```bash
docker compose -f docker/docker-compose.yaml up -d --build
```

后端默认地址为 `http://localhost:8000`。首次索引知识库文档或首次使用记忆语义检索时会下载 FastEmbed 模型，因此可能需要等待一段时间。

查看服务状态或日志：

```bash
docker compose -f docker/docker-compose.yaml ps
docker compose -f docker/docker-compose.yaml logs -f api rag-worker
```

服务启动后可检查运行状态：

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

`live` 只检查 API 进程是否存活；`ready` 会检查模型配置、PostgreSQL、短期记忆、Redis、Qdrant 和 MinIO。

### 3. 导入示例知识库（可选）

```bash
uv sync
uv run python -m app.rag.bootstrap docs/knowledge_base
```

也可以在前端的知识库管理界面创建知识库并上传文档。

### 4. 启动前端

```bash
cd frontend
pnpm install
pnpm dev
```

浏览器访问 Vite 输出的本地地址，通常为 `http://localhost:5173`。前端默认连接：

```text
API: http://localhost:8000
WS:  ws://localhost:8000
```

如需修改，在 `frontend/.env.local` 中配置：

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```

首次进入前端需要注册或登录。注册开关由 `ALLOW_REGISTER` 控制，默认允许；公开部署前应改为关闭或接入正式用户体系。`JWT_SECRET_KEY` 默认值仅适合本地开发，部署时必须替换。

## 本地开发

如需在本机运行 Python 服务并使用热重载，可只启动基础设施：

```bash
docker compose -f docker/docker-compose.yaml up -d postgres redis qdrant minio mysql
uv sync --group dev
uv run celery -A app.rag.celery_app:celery_app worker --loglevel=INFO --pool=solo
```

另开终端启动 API：

```bash
uv run uvicorn app.api.server:app --host 0.0.0.0 --port 8000 --reload
```

运行后端质量检查和测试：

```bash
uv run ruff check app tests
uv run ruff format --check app tests
uv run pytest
```

构建前端：

```bash
cd frontend
pnpm build
```

## API 概览

会话、任务、文件和记忆接口需要 `Authorization: Bearer <token>`。WebSocket 连接通过查询参数传入 token，例如 `/ws/{thread_id}?token=<token>`。知识库接口当前是全局资源接口，尚未按用户隔离。

| 接口 | 用途 |
| --- | --- |
| `POST /api/auth/register` | 注册用户并返回 token |
| `POST /api/auth/login` | 登录并返回 token |
| `GET /api/auth/me` | 获取当前用户 |
| `GET /health/live` | API 存活检查 |
| `GET /health/ready` | 外部依赖就绪检查 |
| `POST /api/task` | 启动研究任务 |
| `POST /api/task/{thread_id}/cancel` | 取消指定任务 |
| `POST /api/upload` | 上传会话附件 |
| `GET /api/files` | 获取当前用户生成文件列表 |
| `GET /api/download` | 下载当前用户生成文件 |
| `GET /api/conversations` | 获取当前用户会话列表 |
| `POST /api/conversations` | 创建会话 |
| `GET /api/conversations/{thread_id}` | 获取会话详情和历史消息 |
| `PATCH /api/conversations/{thread_id}` | 更新标题或归档状态 |
| `DELETE /api/conversations/{thread_id}` | 归档会话并清理短期 checkpoint |
| `GET /api/memories` | 获取长期记忆 |
| `POST /api/memories` | 手动创建长期记忆 |
| `POST /api/memories/search` | 检索长期记忆 |
| `PATCH /api/memories/{memory_id}` | 更新长期记忆 |
| `DELETE /api/memories/{memory_id}` | 删除长期记忆 |
| `GET /api/knowledge-bases` | 获取知识库列表 |
| `POST /api/knowledge-bases` | 创建知识库 |
| `DELETE /api/knowledge-bases/{id}` | 删除知识库 |
| `POST /api/knowledge-bases/{id}/documents` | 上传并索引知识库文档 |
| `GET /api/knowledge-bases/{id}/documents` | 获取文档及索引状态 |
| `POST /api/knowledge-bases/documents/{document_id}/reindex` | 重新索引文档 |
| `DELETE /api/knowledge-bases/documents/{document_id}` | 删除文档 |
| `GET /api/knowledge-bases/index-jobs/{job_id}` | 查询索引任务状态 |
| `POST /api/knowledge-bases/{id}/search` | 执行知识库混合检索 |
| `WebSocket /ws/{thread_id}` | 接收任务实时事件 |

启动后可访问 `http://localhost:8000/docs` 查看完整 OpenAPI 文档。

## 使用示例

可在前端提交类似任务：

```text
从数据库中查询心血管药品的库存情况，并生成 Markdown 报告。
```

```text
搜索 AI 在电商行业的最新应用趋势，并结合知识库资料生成一份 PDF。
```

```text
记住：我更喜欢先给结论、再列证据。然后读取我上传的行业报告，整理一份研究摘要。
```

```text
结合我之前关于电商直播项目的长期记忆，搜索最新公开资料并生成一份竞品分析。
```

## 数据与输出

- 用户上传文件按用户和会话暂存在 `app/updated/user_{user_id}/session_{thread_id}/`。
- Markdown、PDF 等生成结果保存在 `app/output/user_{user_id}/session_{thread_id}/`。
- 会话审计日志保存在 `app/logs/session_{user_id}__{thread_id}.jsonl`。
- 用户、会话、消息、长期记忆、知识库元数据和文档 chunk 存储在 PostgreSQL。
- 长期记忆和知识库 chunk 的向量索引存储在 Qdrant。
- 知识库原始文件存储在 MinIO。
- RAG 索引任务使用 Redis 和 Celery Worker 执行。
- MySQL 示例数据由 `docker/mysql/mysql.sql` 在数据卷首次创建时导入。
- 本地运行时产生的输出文件、数据库卷、日志和模型缓存不应提交到版本库。

## 能力边界

当前项目已经具备基本用户体系、会话隔离和可管理记忆，但仍不是开箱即用的生产系统：

- 默认注册、JWT 密钥和本地服务凭据主要面向开发环境。
- 尚未提供角色权限、组织/租户管理、精细授权和限流。
- 文件安全扫描、内容审核和敏感数据治理仍需外部补齐。
- 长任务并发、队列治理、可观测性和告警仍偏向本地开发形态。
- 记忆抽取依赖模型判断，重要生产场景应增加人工确认、评测和回滚机制。

用于公开网络或生产环境前，请补充正式身份认证、授权策略、限流、数据隔离、密钥管理、监控告警、安全审计和质量回归流程。
