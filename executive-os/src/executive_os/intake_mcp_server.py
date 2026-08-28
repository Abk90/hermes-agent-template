from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from .identity import IdentityRegistry
from .intake import InternalIntakeService
from .odoo_context import ContextReceiptSigner, OdooContextResolver, StreamableHttpOdooClient


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
        raise RuntimeError("Install the optional 'mcp' dependency to run the intake MCP server") from exc

    registry = IdentityRegistry.from_json(os.environ.get("INTERNAL_INTAKE_DEVICE_CREDENTIALS_JSON"))
    signing_key = os.environ.get("INTERNAL_INTAKE_CONTEXT_SIGNING_KEY", "")
    signer = ContextReceiptSigner(
        signing_key,
        ttl_minutes=int(os.environ.get("INTERNAL_INTAKE_CONTEXT_RECEIPT_TTL_MINUTES", "60")),
    ) if signing_key else None
    odoo_url = os.environ.get("ODOO_MCP_URL", "").strip()
    resolver = OdooContextResolver(StreamableHttpOdooClient(odoo_url), signer) if odoo_url and signer else None
    service = InternalIntakeService(
        registry=registry,
        bot_username=os.environ.get("INTERNAL_INTAKE_TELEGRAM_BOT_USERNAME"),
        context_signer=signer,
        odoo_resolver=resolver,
    )

    async def list_tools(
        _context: ServerRequestContext,
        _params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        return ListToolsResult(
            tools=[
                Tool(
                    name="search_odoo_context",
                    description="Search only project/task names inside the paired collaborator's allowed Odoo companies. Read-only and field-limited.",
                    input_schema=_schema(
                        {
                            "telegram_user_id": {"type": "string", "minLength": 1},
                            "chat_id": {"type": "string", "minLength": 1},
                            "model": {"type": "string", "enum": ["project.project", "project.task"]},
                            "query": {"type": "string", "minLength": 3, "maxLength": 200},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 8},
                        },
                        ["telegram_user_id", "chat_id", "model", "query"],
                    ),
                ),
                Tool(
                    name="verify_odoo_context",
                    description="Read one exact allowlisted Odoo record by model and numeric ID, then issue a short-lived server-signed reference receipt. Executes zero writes.",
                    input_schema=_schema(
                        {
                            "telegram_user_id": {"type": "string", "minLength": 1},
                            "chat_id": {"type": "string", "minLength": 1},
                            "model": {
                                "type": "string",
                                "enum": [
                                    "project.project",
                                    "project.task",
                                    "documents.document",
                                    "approval.request",
                                ],
                            },
                            "record_id": {"type": "string", "pattern": "^[1-9][0-9]*$"},
                        },
                        ["telegram_user_id", "chat_id", "model", "record_id"],
                    ),
                ),
                Tool(
                    name="bind_telegram_start",
                    description="Consume a one-time API continuation token and bind only the pre-verified Telegram numeric ID.",
                    input_schema=_schema(
                        {
                            "start_token": {"type": "string", "minLength": 16},
                            "telegram_user_id": {"type": "string", "minLength": 1},
                            "chat_id": {"type": "string", "minLength": 1},
                        },
                        ["start_token", "telegram_user_id", "chat_id"],
                    ),
                ),
                Tool(
                    name="submit_telegram_request",
                    description="Validate and record a prepared request pack from an already paired Telegram collaborator. Executes zero business writes.",
                    input_schema=_schema(
                        {
                            "pack_json": {"type": "string", "minLength": 2},
                            "telegram_user_id": {"type": "string", "minLength": 1},
                            "chat_id": {"type": "string", "minLength": 1},
                            "message_id": {"type": "string", "minLength": 1},
                        },
                        ["pack_json", "telegram_user_id", "chat_id", "message_id"],
                    ),
                ),
                Tool(
                    name="append_intake_message",
                    description="Append one Telegram clarification to the exact request without changing Odoo or other systems.",
                    input_schema=_schema(
                        {
                            "request_id": {"type": "string", "minLength": 1},
                            "telegram_user_id": {"type": "string", "minLength": 1},
                            "chat_id": {"type": "string", "minLength": 1},
                            "message_id": {"type": "string", "minLength": 1},
                            "body": {"type": "string", "minLength": 1, "maxLength": 8000},
                        },
                        ["request_id", "telegram_user_id", "chat_id", "message_id", "body"],
                    ),
                ),
                Tool(
                    name="get_intake_request",
                    description="Read one request only when it belongs to the exact paired Telegram identity.",
                    input_schema=_schema(
                        {
                            "request_id": {"type": "string", "minLength": 1},
                            "telegram_user_id": {"type": "string", "minLength": 1},
                        },
                        ["request_id", "telegram_user_id"],
                    ),
                ),
                Tool(
                    name="list_my_intake_requests",
                    description="List open requests belonging to the exact paired Telegram identity.",
                    input_schema=_schema(
                        {
                            "telegram_user_id": {"type": "string", "minLength": 1},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                        },
                        ["telegram_user_id"],
                    ),
                ),
            ]
        )

    async def call_tool(
        _context: ServerRequestContext,
        params: CallToolRequestParams,
    ) -> CallToolResult:
        args = params.arguments or {}
        if params.name == "search_odoo_context":
            result = await service.search_telegram_odoo_context(
                telegram_user_id=str(args["telegram_user_id"]),
                chat_id=str(args["chat_id"]),
                model=str(args["model"]),
                query=str(args["query"]),
                limit=int(args.get("limit", 8)),
            )
        elif params.name == "verify_odoo_context":
            result = await service.verify_telegram_odoo_context(
                telegram_user_id=str(args["telegram_user_id"]),
                chat_id=str(args["chat_id"]),
                model=str(args["model"]),
                record_id=str(args["record_id"]),
            )
        elif params.name == "bind_telegram_start":
            result = service.bind_telegram_start(
                start_token=str(args["start_token"]),
                telegram_user_id=str(args["telegram_user_id"]),
                chat_id=str(args["chat_id"]),
            )
        elif params.name == "submit_telegram_request":
            result = service.submit_telegram_pack(
                json.loads(str(args["pack_json"])),
                telegram_user_id=str(args["telegram_user_id"]),
                chat_id=str(args["chat_id"]),
                message_id=str(args["message_id"]),
            )
        elif params.name == "append_intake_message":
            result = service.append_telegram_message(
                str(args["request_id"]),
                telegram_user_id=str(args["telegram_user_id"]),
                chat_id=str(args["chat_id"]),
                message_id=str(args["message_id"]),
                body=str(args["body"]),
            )
        elif params.name == "get_intake_request":
            result = service.get_telegram_request(
                str(args["request_id"]),
                telegram_user_id=str(args["telegram_user_id"]),
            )
        elif params.name == "list_my_intake_requests":
            result = service.list_telegram_requests(
                telegram_user_id=str(args["telegram_user_id"]),
                limit=int(args.get("limit", 20)),
            )
        else:
            raise ValueError(f"Unknown tool: {params.name}")

        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, sort_keys=True))]
        )

    return Server(
        "belkora-internal-intake",
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
