"""本地知识库子智能体配置模块。"""

from app.agent.prompts import sub_agents_content
from app.tools.local_rag_tools import create_ask_delete, get_assistant_list

# 本地 RAG 子智能体处理内部非结构化文档，与网络搜索、数据库查询形成互补
# 它遵循“先查助手列表 -> 再向指定助手提问”的工作顺序
# tools 列表声明该子智能体可以发现知识库助手，并发起一次性临时会话查询
knowledge_base_agent = {
    "name": sub_agents_content["knowledge_base"]["name"],
    "description": sub_agents_content["knowledge_base"]["description"],
    "system_prompt": sub_agents_content["knowledge_base"]["system_prompt"],
    "tools": [get_assistant_list, create_ask_delete],
}
