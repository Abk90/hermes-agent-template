from __future__ import annotations

import asyncio
import json
from typing import Any

from .ledger import Ledger
from .service import ExecutiveOSService


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        result["required"] = required
    return result


def build_server():
    try:
        from mcp.server import Server, ServerRequestContext
        from mcp.types import (
            CallToolRequestParams,
            CallToolResult,
            ListToolsResult,
            PaginatedRequestParams,
            TextContent,
            Tool,
        )
    except ImportError as exc:  # pragma: no cover - exercised in the Railway image
        raise RuntimeError("Install the optional 'mcp' dependency to run the MCP server") from exc

    service = ExecutiveOSService()

    async def list_tools(
        _context: ServerRequestContext,
        _params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        tools = [
            Tool(
                name="triage_request",
                description="Qualify a request and persist it idempotently in the private ledger.",
                input_schema=_schema(
                    {
                        "payload_json": {"type": "string"},
                        "idempotency_key": {"type": "string", "minLength": 1},
                        "actor": {"type": "string", "minLength": 1},
                    },
                    ["payload_json", "idempotency_key", "actor"],
                ),
            ),
            Tool(
                name="list_executive_queue",
                description="List open normalized requests ordered P0, P1, then P2.",
                input_schema=_schema(
                    {
                        "priorities_csv": {"type": "string", "default": "P0,P1,P2"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                    }
                ),
            ),
            Tool(
                name="why_request",
                description="Return a request, its classification and append-only audit events.",
                input_schema=_schema(
                    {"request_id": {"type": "string", "minLength": 1}},
                    ["request_id"],
                ),
            ),
            Tool(
                name="transition_request",
                description="Apply a validated ledger transition; never writes Odoo or OmniFocus.",
                input_schema=_schema(
                    {
                        "request_id": {"type": "string", "minLength": 1},
                        "new_status": {
                            "type": "string",
                            "enum": [
                                "NEW",
                                "QUALIFYING",
                                "READY",
                                "PENDING",
                                "RETRYING",
                                "DONE",
                                "FAILED",
                                "REJECTED",
                            ],
                        },
                        "actor": {"type": "string", "minLength": 1},
                        "justification": {"type": "string", "minLength": 1},
                        "result": {"type": "string", "default": "DONE"},
                        "error": {"type": "string", "default": ""},
                    },
                    ["request_id", "new_status", "actor", "justification"],
                ),
            ),
            Tool(
                name="connector_status",
                description="Return connector freshness and failures recorded by deterministic probes.",
                input_schema=_schema({}),
            ),
        ]
        return ListToolsResult(tools=tools)

    async def call_tool(
        _context: ServerRequestContext,
        params: CallToolRequestParams,
    ) -> CallToolResult:
        name = params.name
        args = params.arguments or {}
        if name == "triage_request":
            payload: dict[str, Any] = json.loads(str(args["payload_json"]))
            result = service.triage_request(
                payload,
                idempotency_key=str(args["idempotency_key"]),
                actor=str(args["actor"]),
            )
        elif name == "list_executive_queue":
            priorities = [
                part.strip()
                for part in str(args.get("priorities_csv", "P0,P1,P2")).split(",")
                if part.strip()
            ]
            result = service.list_queue(priorities, int(args.get("limit", 50)))
        elif name == "why_request":
            result = service.explain(str(args["request_id"]))
        elif name == "transition_request":
            result = service.transition(
                str(args["request_id"]),
                str(args["new_status"]),
                str(args["actor"]),
                str(args["justification"]),
                str(args.get("result", "DONE")),
                str(args.get("error") or "") or None,
            )
        elif name == "connector_status":
            result = Ledger().connector_status()
        else:
            raise ValueError(f"Unknown tool: {name}")

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False, sort_keys=True),
                )
            ]
        )

    return Server(
        "belkora-executive-os",
        version="0.1.0",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def run_server() -> None:
    from mcp.server.stdio import stdio_server

    server = build_server()
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


def main() -> None:
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
