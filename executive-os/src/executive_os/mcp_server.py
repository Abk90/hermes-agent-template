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
        import mcp.types as types
        from mcp.server import Server
    except ImportError as exc:  # pragma: no cover - exercised in the Railway image
        raise RuntimeError("Install the optional 'mcp' dependency to run the MCP server") from exc

    server = Server("belkora-executive-os")
    service = ExecutiveOSService()

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="triage_request",
                description="Qualify a request and persist it idempotently in the private ledger.",
                inputSchema=_schema(
                    {
                        "payload_json": {"type": "string"},
                        "idempotency_key": {"type": "string", "minLength": 1},
                        "actor": {"type": "string", "minLength": 1},
                    },
                    ["payload_json", "idempotency_key", "actor"],
                ),
            ),
            types.Tool(
                name="list_executive_queue",
                description="List open normalized requests ordered P0, P1, then P2.",
                inputSchema=_schema(
                    {
                        "priorities_csv": {"type": "string", "default": "P0,P1,P2"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
                    }
                ),
            ),
            types.Tool(
                name="why_request",
                description="Return a request, its classification and append-only audit events.",
                inputSchema=_schema(
                    {"request_id": {"type": "string", "minLength": 1}},
                    ["request_id"],
                ),
            ),
            types.Tool(
                name="transition_request",
                description="Apply a validated ledger transition; never writes Odoo or OmniFocus.",
                inputSchema=_schema(
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
            types.Tool(
                name="connector_status",
                description="Return connector freshness and failures recorded by deterministic probes.",
                inputSchema=_schema({}),
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        args = arguments or {}
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

        return [
            types.TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, sort_keys=True),
            )
        ]

    return server


async def run_server() -> None:
    from mcp.server.stdio import stdio_server

    server = build_server()
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


def main() -> None:
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
