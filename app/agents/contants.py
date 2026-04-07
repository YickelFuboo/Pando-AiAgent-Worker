from pathlib import Path
from app.config.settings import PROJECT_BASE_DIR


# Ageng相关的配置文件
AGENT_META_FILENAME = "meta.json"
MCP_SERVERS_FILENAME = "mcp_servers.json"
USABLE_TOOLS_FILENAME = "usable_tools.json"
USABLE_SKILLS_FILENAME = "usable_skills.json"

AGENTS_ROOT_PATH = Path(PROJECT_BASE_DIR) / "app" / "agents" / ".agent"
WORKSPACE_ROOT_PATH = Path(PROJECT_BASE_DIR) / "data" / ".workspace"
USER_ROOT_PATH = Path(PROJECT_BASE_DIR) / "data" / ".users"

# Agent 目录下引导文件所在子目录（.agent/agent_type/prompt）
AGENT_CONTEXT_PATH = "prompts"
# 会被读入 system prompt 的引导文件名（按顺序，存在则读）
AGENT_CONTEXT_FILES = ["AGENT.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md", "RUNTIME.md"]