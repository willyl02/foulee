"""Vérifie que le serveur MCP de Foulée démarre et répond, comme Claude Desktop le lancerait.

    python mcp_check.py <python.exe de Foulée>
"""

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main(python: str) -> int:
    params = StdioServerParameters(command=python, args=["-m", "foulee", "mcp"], env={**os.environ, "PYTHONUTF8": "1"})
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await asyncio.wait_for(session.initialize(), timeout=60)
        tools = (await session.list_tools()).tools
        status = await session.call_tool("statut", {})
    failed = getattr(status, "is_error", getattr(status, "isError", False))  # selon la version du SDK MCP
    if failed or len(tools) < 10:
        print(f"Réponse inattendue : {len(tools)} outils, statut en erreur : {failed}")
        return 1
    print(f"serveur MCP : {len(tools)} outils, « statut » répond")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else sys.executable)))
