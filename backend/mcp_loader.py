import asyncio
from typing import Any

from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.sse import sse_client

from backend.config import MCPServerConfig


class MCPLoader:
    def __init__(self, servers: list[MCPServerConfig]):
        self._servers = servers

    def _mcp_tool_to_gemini(self, tool: Any) -> dict:
        return {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        }

    async def _load_from_http_server(self, server: MCPServerConfig) -> list[dict]:
        try:
            async with sse_client(server.url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [self._mcp_tool_to_gemini(t) for t in result.tools]
        except Exception as e:
            print(f"[MCPLoader] Failed to connect to {server.name} ({server.url}): {e}")
            return []

    async def _load_from_stdio_server(self, server: MCPServerConfig) -> list[dict]:
        try:
            params = StdioServerParameters(command=server.command, args=server.args)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [self._mcp_tool_to_gemini(t) for t in result.tools]
        except Exception as e:
            print(f"[MCPLoader] Failed to connect to {server.name}: {e}")
            return []

    async def load_tool_definitions(self) -> list[dict]:
        tasks = []
        for server in self._servers:
            if server.type == "http":
                tasks.append(self._load_from_http_server(server))
            elif server.type == "stdio":
                tasks.append(self._load_from_stdio_server(server))

        results = await asyncio.gather(*tasks)
        return [tool for server_tools in results for tool in server_tools]
