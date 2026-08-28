from __future__ import annotations

import json
from typing import Any

from .ledger import Ledger
from .service import ExecutiveOSService


def build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised in the Railway image
        raise RuntimeError("Install the optional 'mcp' dependency to run the MCP server") from exc

    mcp = FastMCP("belkora-executive-os")
    service = ExecutiveOSService()

    @mcp.tool()
    def triage_request(payload_json: str, idempotency_key: str, actor: str) -> str:
        """Qualify a request, persist it idempotently, and return priority, route and questions."""
        payload: dict[str, Any] = json.loads(payload_json)
        return json.dumps(
            service.triage_request(payload, idempotency_key=idempotency_key, actor=actor),
            ensure_ascii=False,
            sort_keys=True,
        )

    @mcp.tool()
    def list_executive_queue(priorities_csv: str = "P0,P1,P2", limit: int = 50) -> str:
        """List open normalized requests ordered P0, P1, then P2."""
        priorities = [part.strip() for part in priorities_csv.split(",") if part.strip()]
        return json.dumps(service.list_queue(priorities, limit), ensure_ascii=False, sort_keys=True)

    @mcp.tool()
    def why_request(request_id: str) -> str:
        """Return the normalized request, classification and append-only audit events."""
        return json.dumps(service.explain(request_id), ensure_ascii=False, sort_keys=True)

    @mcp.tool()
    def transition_request(
        request_id: str,
        new_status: str,
        actor: str,
        justification: str,
        result: str = "DONE",
        error: str = "",
    ) -> str:
        """Apply a validated technical state transition. Does not write Odoo or OmniFocus."""
        return json.dumps(
            service.transition(
                request_id,
                new_status,
                actor,
                justification,
                result,
                error or None,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )

    @mcp.tool()
    def connector_status() -> str:
        """Return connector freshness and failures recorded by deterministic probes."""
        return json.dumps(Ledger().connector_status(), ensure_ascii=False, sort_keys=True)

    return mcp


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
