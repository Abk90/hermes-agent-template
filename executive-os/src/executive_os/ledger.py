from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .models import RequestStatus, TriageDecision


DEFAULT_DB_PATH = Path(os.environ.get("EXECUTIVE_OS_DB", "/data/.hermes/executive-os/ledger.sqlite3"))

ALLOWED_TRANSITIONS = {
    RequestStatus.NEW: {RequestStatus.QUALIFYING, RequestStatus.READY, RequestStatus.REJECTED},
    RequestStatus.QUALIFYING: {RequestStatus.READY, RequestStatus.REJECTED, RequestStatus.FAILED},
    RequestStatus.READY: {RequestStatus.PENDING, RequestStatus.REJECTED, RequestStatus.DONE},
    RequestStatus.PENDING: {RequestStatus.RETRYING, RequestStatus.DONE, RequestStatus.FAILED},
    RequestStatus.RETRYING: {RequestStatus.PENDING, RequestStatus.DONE, RequestStatus.FAILED},
    RequestStatus.FAILED: {RequestStatus.RETRYING, RequestStatus.REJECTED},
    RequestStatus.DONE: set(),
    RequestStatus.REJECTED: set(),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_request_id(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:12].upper()
    return f"REQ-{digest}"


class Ledger:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,
                    source_message_id TEXT,
                    requester_id TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    route TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL REFERENCES requests(request_id),
                    system TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    target_url TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(request_id, system, target_type, target_id)
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT REFERENCES requests(request_id),
                    timestamp TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT,
                    justification TEXT,
                    result TEXT,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS connector_state (
                    connector TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    last_attempt_at TEXT NOT NULL,
                    last_success_at TEXT,
                    cursor TEXT,
                    error TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS events_no_update
                BEFORE UPDATE ON events BEGIN
                    SELECT RAISE(ABORT, 'audit events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete
                BEFORE DELETE ON events BEGIN
                    SELECT RAISE(ABORT, 'audit events are append-only');
                END;
                """
            )
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def create_or_get(
        self,
        *,
        payload: dict[str, Any],
        decision: TriageDecision,
        idempotency_key: str,
        actor: str,
    ) -> tuple[dict[str, Any], bool]:
        if not idempotency_key.strip():
            raise ValueError("idempotency_key is required")
        requester_id = str(payload.get("requester_id") or "").strip()
        subject = str(payload.get("subject") or "").strip()
        source = str(payload.get("source") or "").strip()
        if not requester_id or not subject or not source:
            raise ValueError("source, requester_id and subject are required")

        request_id = stable_request_id(idempotency_key)
        now = utc_now()
        status = RequestStatus.QUALIFYING if decision.missing_fields else RequestStatus.READY
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM requests WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                return dict(existing), False

            conn.execute(
                """
                INSERT INTO requests (
                    request_id, idempotency_key, source, source_message_id,
                    requester_id, subject, priority, route, confidence, status,
                    payload_json, decision_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    idempotency_key,
                    source,
                    str(payload.get("source_message_id") or "") or None,
                    requester_id,
                    subject,
                    decision.priority.value,
                    decision.route.value,
                    decision.confidence,
                    status.value,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    json.dumps(decision.as_dict(), ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO events (request_id, timestamp, actor, action, new_status, justification, result)
                VALUES (?, ?, ?, 'REQUEST_CREATED', ?, ?, 'DONE')
                """,
                (request_id, now, actor, status.value, "Demande creee avec cle d'idempotence."),
            )
            created = conn.execute("SELECT * FROM requests WHERE request_id = ?", (request_id,)).fetchone()
            return dict(created), True

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM requests WHERE request_id = ?", (request_id,)).fetchone()
            return dict(row) if row else None

    def list_queue(self, priorities: list[str] | None = None, limit: int = 50) -> list[dict[str, Any]]:
        priorities = priorities or ["P0", "P1", "P2"]
        placeholders = ",".join("?" for _ in priorities)
        query = f"""
            SELECT * FROM requests
            WHERE priority IN ({placeholders})
              AND status NOT IN ('DONE', 'REJECTED')
            ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,
                     created_at ASC
            LIMIT ?
        """
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(query, (*priorities, min(limit, 200))).fetchall()]

    def transition(
        self,
        request_id: str,
        new_status: RequestStatus,
        *,
        actor: str,
        justification: str,
        result: str = "DONE",
        error: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM requests WHERE request_id = ?", (request_id,)).fetchone()
            if not row:
                raise KeyError(request_id)
            old_status = RequestStatus(row["status"])
            if new_status not in ALLOWED_TRANSITIONS[old_status]:
                raise ValueError(f"Invalid transition {old_status.value} -> {new_status.value}")
            now = utc_now()
            conn.execute(
                "UPDATE requests SET status = ?, updated_at = ? WHERE request_id = ?",
                (new_status.value, now, request_id),
            )
            conn.execute(
                """
                INSERT INTO events (
                    request_id, timestamp, actor, action, old_status, new_status,
                    justification, result, error
                ) VALUES (?, ?, ?, 'STATUS_CHANGED', ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    now,
                    actor,
                    old_status.value,
                    new_status.value,
                    justification,
                    result,
                    error,
                ),
            )
        updated = self.get_request(request_id)
        assert updated is not None
        return updated

    def explain(self, request_id: str) -> dict[str, Any]:
        request = self.get_request(request_id)
        if not request:
            raise KeyError(request_id)
        with self.connect() as conn:
            events = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM events WHERE request_id = ? ORDER BY event_id", (request_id,)
                ).fetchall()
            ]
        request["payload"] = json.loads(request.pop("payload_json"))
        request["decision"] = json.loads(request.pop("decision_json"))
        return {"request": request, "events": events}

    def record_connector_state(
        self,
        connector: str,
        status: str,
        *,
        success: bool,
        cursor: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO connector_state (
                    connector, status, last_attempt_at, last_success_at, cursor, error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(connector) DO UPDATE SET
                    status=excluded.status,
                    last_attempt_at=excluded.last_attempt_at,
                    last_success_at=COALESCE(excluded.last_success_at, connector_state.last_success_at),
                    cursor=COALESCE(excluded.cursor, connector_state.cursor),
                    error=excluded.error,
                    updated_at=excluded.updated_at
                """,
                (connector, status, now, now if success else None, cursor, error, now),
            )
            row = conn.execute(
                "SELECT * FROM connector_state WHERE connector = ?", (connector,)
            ).fetchone()
            return dict(row)

    def connector_status(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                dict(row)
                for row in conn.execute("SELECT * FROM connector_state ORDER BY connector").fetchall()
            ]
