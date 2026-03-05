"""连接 MCP 服务并将工具注册到 ToolsFactory。"""
import logging
import os
from contextlib import AsyncExitStack
from typing import Any, Dict, List
from app.agents.tools.factory import ToolsFactory
from app.agents.tools.mcp.caller import MCPToolWrapper


class MCPServerConnector:
    """根据配置连接 MCP 服务，并将各服务的工具注册到 factory。"""

    @classmethod
    async def connect(
        cls,
        servers: List[Dict[str, Any]],
        factory: ToolsFactory,
        stack: AsyncExitStack,
    ) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client, StdioServerParameters
        from mcp.client.sse import sse_client

        for cfg in servers:
            server_id = cfg.get("id") or cfg.get("name") or "mcp"
            server_type = (cfg.get("type") or "stdio").lower()
            timeout_ms = cfg.get("timeout_ms") or 30000
            timeout_sec = timeout_ms / 1000.0
            allow_tools = cfg.get("tools") or []

            try:
                if server_type == "stdio":
                    command = cfg.get("command")
                    args = cfg.get("args") or []
                    if not command:
                        logging.warning("MCP server %s: missing 'command', skipping", server_id)
                        continue
                    env = cfg.get("env") or {}
                    params = StdioServerParameters(command=command, args=args, env=env or None)
                    read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
                elif server_type == "sse":
                    endpoint = cfg.get("endpoint") or cfg.get("url")
                    if not endpoint:
                        logging.warning("MCP server %s: missing 'endpoint' or 'url', skipping", server_id)
                        continue
                    headers = {}
                    api_key_env = cfg.get("api_key_env")
                    if api_key_env and os.environ.get(api_key_env):
                        headers["Authorization"] = f"Bearer {os.environ[api_key_env]}"
                    read_stream, write_stream = await stack.enter_async_context(
                        sse_client(endpoint, headers=headers or None, timeout=timeout_sec)
                    )
                else:
                    logging.warning(f"MCP server {server_id}: unknown type {server_type}, skipping")
                    continue

                mcp_session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
                await mcp_session.initialize()

                list_result = await mcp_session.list_tools()
                tools = getattr(list_result, "tools", []) or []
                registered = 0
                for tool_def in tools:
                    name = getattr(tool_def, "name", None)
                    if not name:
                        continue
                    if allow_tools and name not in allow_tools:
                        continue
                    wrapper = MCPToolWrapper(mcp_session, server_id, tool_def, timeout_seconds=timeout_sec)
                    factory.register_tool(wrapper)
                    registered += 1
                    logging.debug(f"MCP: registered tool {name} from server {server_id}")
                logging.info(f"MCP server {server_id}: connected, {registered} tools registered")
            except Exception as e:
                logging.error(f"MCP server {server_id}: failed to connect: {e}")
