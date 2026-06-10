import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.config import MCPServerConfig
from backend.mcp_loader import MCPLoader


@pytest.mark.asyncio
async def test_no_servers_returns_empty():
    loader = MCPLoader(servers=[])
    tools = await loader.load_tool_definitions()
    assert tools == []


@pytest.mark.asyncio
async def test_tool_definition_schema_shape():
    # MCPLoader converts MCP tool schemas into Gemini FunctionDeclaration dicts
    mock_tool = MagicMock()
    mock_tool.name = "search_files"
    mock_tool.description = "Search for files"
    mock_tool.inputSchema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    loader = MCPLoader(servers=[])
    result = loader._mcp_tool_to_gemini(mock_tool)

    assert result["name"] == "search_files"
    assert result["description"] == "Search for files"
    assert "parameters" in result
    assert result["parameters"]["properties"]["query"]["type"] == "string"
