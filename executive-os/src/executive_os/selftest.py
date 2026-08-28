from __future__ import annotations

import asyncio
import json
import os
import sys


EXPECTED_TOOLS = {
    "triage_request",
    "list_executive_queue",
    "why_request",
    "transition_request",
    "connector_status",
}


async def run_selftest() -> list[str]:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    child_env = {
        "PYTHONPATH": os.environ.get("PYTHONPATH", "/app/executive-os/src"),
        "EXECUTIVE_OS_CONFIG": os.environ.get(
            "EXECUTIVE_OS_CONFIG", "/app/executive-os/config/executive-os.toml"
        ),
        "EXECUTIVE_OS_DB": os.environ.get(
            "EXECUTIVE_OS_DB", "/data/.hermes/executive-os/ledger.sqlite3"
        ),
        "HOME": os.environ.get("HOME", "/data"),
        "HERMES_HOME": os.environ.get("HERMES_HOME", "/data/.hermes"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
    }
    params = StdioServerParameters(
        command=os.environ.get("EXECUTIVE_OS_PYTHON", sys.executable),
        args=["-m", "executive_os.mcp_server"],
        env=child_env,
    )
    async with asyncio.timeout(20):
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                discovered = await session.list_tools()

    names = sorted(tool.name for tool in discovered.tools)
    if set(names) != EXPECTED_TOOLS:
        raise RuntimeError(f"Unexpected Executive OS MCP tools: {names}")
    return names


def main() -> None:
    names = asyncio.run(run_selftest())
    print(json.dumps({"executive_os_mcp_selftest": "ok", "tools": names}, sort_keys=True))


if __name__ == "__main__":
    main()
