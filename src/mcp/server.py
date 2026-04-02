"""
MCP Server — Azure Self-Service
Exposes list_directory and read_file over the MCP protocol.
The LLM uses these two tools to explore terraform/ and build deployment plans.
"""
import asyncio
import json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from src.tools.fs_tools import list_directory, read_file

server = Server("azure-self-service")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_directory",
            description=(
                "List the contents of a directory. "
                "Use this to explore the terraform/ folder structure and discover "
                "available services, template types (create, create_common_resource), "
                "and files (main.tf, variables.tf, outputs.tf, README.md)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root, e.g. 'terraform/' or 'terraform/aks/create'"
                    }
                },
                "required": ["path"]
            }
        ),
        types.Tool(
            name="read_file",
            description=(
                "Read the full content of a file. "
                "Use this to read README.md files for service descriptions, "
                "main.tf to understand what is deployed and find data{} blocks (dependencies), "
                "variables.tf to know what inputs the customer must provide, "
                "and outputs.tf to understand what values a template exposes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root, e.g. 'terraform/aks/create/main.tf'"
                    }
                },
                "required": ["path"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        if name == "list_directory":
            result = list_directory(arguments["path"])
        elif name == "read_file":
            result = read_file(arguments["path"])
        else:
            result = {"error": f"Unknown tool: {name}"}
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
