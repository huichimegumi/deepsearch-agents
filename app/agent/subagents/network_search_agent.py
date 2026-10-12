"""
网络搜索子智能体配置模块

将 app/prompt/prompts.yml 中的 search 配置与 research_search 工具组装成
DeepAgents 可识别的字典式子智能体。主智能体后续会根据 description
决定是否把公开网络信息查询任务分派给它。
"""

from app.agent.prompts import sub_agents_content
from app.tools.tavily_tool import research_search

NETWORK_SEARCH_SUBAGENT_NAME = "network_search"

# 机器路由名由代码固定，避免本地化展示名变化破坏 DeepAgents task 白名单。
# 描述和行为约束仍来自 YAML；tools 列表声明该子智能体可以调用的真实外部能力。
network_search_agent = {
    "name": NETWORK_SEARCH_SUBAGENT_NAME,
    "description": (
        f"{sub_agents_content['search']['name']}: {sub_agents_content['search']['description']}"
    ),
    "system_prompt": sub_agents_content["search"]["system_prompt"],
    "tools": [research_search],
}
