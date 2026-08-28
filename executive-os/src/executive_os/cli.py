from __future__ import annotations

import argparse
import json

from .ledger import Ledger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="executive-os")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("connectors", help="Show connector freshness and status")
    queue = sub.add_parser("queue", help="List the executive queue")
    queue.add_argument("--priority", default="P0,P1,P2")
    queue.add_argument("--limit", type=int, default=50)
    why = sub.add_parser("why", help="Explain one request")
    why.add_argument("request_id")
    sub.add_parser("status", help="Show ledger and queue counts")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ledger = Ledger()
    if args.command == "connectors":
        result = ledger.connector_status()
    elif args.command == "queue":
        result = ledger.list_queue(args.priority.split(","), args.limit)
    elif args.command == "why":
        result = ledger.explain(args.request_id)
    else:
        queue = ledger.list_queue(["P0", "P1", "P2"], 200)
        result = {
            "database": str(ledger.path),
            "open_queue": len(queue),
            "p0": sum(1 for item in queue if item["priority"] == "P0"),
            "p1": sum(1 for item in queue if item["priority"] == "P1"),
            "connectors": ledger.connector_status(),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0
