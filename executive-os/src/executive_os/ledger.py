from __future__ import annotations

import hashlib
import json
import os
import secrets
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
                    target_model TEXT,
                    company_id TEXT,
                    target_label TEXT,
                    verification_state TEXT,
                    target_url TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(request_id, system, target_type, target_id)
                );
                CREATE TABLE IF NOT EXISTS request_revisions (
                    revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL REFERENCES requests(request_id),
                    revision INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(request_id, revision)
                );
                CREATE TABLE IF NOT EXISTS request_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL REFERENCES requests(request_id),
                    source TEXT NOT NULL,
                    source_message_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(source, source_message_id)
                );
                CREATE TABLE IF NOT EXISTS operation_proposals (
                    proposal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL REFERENCES requests(request_id),
                    operation_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_system TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    target_model TEXT,
                    target_company_id TEXT,
                    target_label TEXT,
                    requested_executor TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    approval_required INTEGER NOT NULL CHECK (approval_required = 1),
                    reversible INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK (status = 'PROPOSED'),
                    created_at TEXT NOT NULL,
                    UNIQUE(request_id, operation_id)
                );
                CREATE TABLE IF NOT EXISTS telegram_start_tokens (
                    token_hash TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES requests(request_id),
                    requester_id TEXT NOT NULL,
                    expected_telegram_user_id TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS telegram_bindings (
                    requester_id TEXT PRIMARY KEY,
                    telegram_user_id TEXT NOT NULL UNIQUE,
                    chat_id TEXT NOT NULL,
                    verified_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1
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
                CREATE TRIGGER IF NOT EXISTS request_revisions_no_update
                BEFORE UPDATE ON request_revisions BEGIN
                    SELECT RAISE(ABORT, 'request revisions are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS request_revisions_no_delete
                BEFORE DELETE ON request_revisions BEGIN
                    SELECT RAISE(ABORT, 'request revisions are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS request_messages_no_update
                BEFORE UPDATE ON request_messages BEGIN
                    SELECT RAISE(ABORT, 'request messages are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS request_messages_no_delete
                BEFORE DELETE ON request_messages BEGIN
                    SELECT RAISE(ABORT, 'request messages are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS operation_proposals_no_update
                BEFORE UPDATE ON operation_proposals BEGIN
                    SELECT RAISE(ABORT, 'operation proposals are append-only in observe mode');
                END;
                CREATE TRIGGER IF NOT EXISTS operation_proposals_no_delete
                BEFORE DELETE ON operation_proposals BEGIN
                    SELECT RAISE(ABORT, 'operation proposals are append-only in observe mode');
                END;
                """
            )
            migrations = {
                "links": {
                    "target_model": "TEXT",
                    "company_id": "TEXT",
                    "target_label": "TEXT",
                    "verification_state": "TEXT",
                },
                "operation_proposals": {
                    "target_model": "TEXT",
                    "target_company_id": "TEXT",
                    "target_label": "TEXT",
                },
            }
            for table, columns in migrations.items():
                existing = {
                    row["name"]
                    for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
                }
                for column, declaration in columns.items():
                    if column not in existing:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
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

    def record_request_pack(
        self,
        request_id: str,
        *,
        pack: dict[str, Any],
        decision: TriageDecision,
        actor: str,
    ) -> dict[str, int]:
        now = utc_now()
        links_added = 0
        proposals_added = 0
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT request_id FROM requests WHERE request_id = ?", (request_id,)).fetchone()
            if not row:
                raise KeyError(request_id)

            existing_revision = conn.execute(
                "SELECT COUNT(*) AS count FROM request_revisions WHERE request_id = ?",
                (request_id,),
            ).fetchone()["count"]
            if existing_revision == 0:
                conn.execute(
                    """
                    INSERT INTO request_revisions (
                        request_id, revision, payload_json, decision_json, actor, created_at
                    ) VALUES (?, 1, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        json.dumps(pack, ensure_ascii=False, sort_keys=True),
                        json.dumps(decision.as_dict(), ensure_ascii=False, sort_keys=True),
                        actor,
                        now,
                    ),
                )

            context = pack["business_context"]
            references: list[tuple[str, dict[str, Any]]] = []
            if context.get("primary_object"):
                references.append(("primary", context["primary_object"]))
            references.extend(("related", item) for item in context.get("related_objects", []))
            for role, reference in references:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO links (
                        request_id, system, target_type, target_id, target_model,
                        company_id, target_label, verification_state, target_url, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request_id,
                        reference["system"],
                        f"{role}:{reference['object_type']}",
                        str(reference["record_id"]),
                        reference.get("model"),
                        reference.get("company_id"),
                        reference.get("label"),
                        "VERIFIED" if reference.get("verification_receipt") else "DECLARED",
                        reference.get("url"),
                        now,
                    ),
                )
                links_added += max(cursor.rowcount, 0)

            for evidence in pack.get("evidence", []):
                reference = str(evidence["reference"])
                evidence_id = hashlib.sha256(reference.encode("utf-8")).hexdigest()[:32]
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO links (
                        request_id, system, target_type, target_id, target_url, created_at
                    ) VALUES (?, ?, 'evidence', ?, ?, ?)
                    """,
                    (request_id, evidence["kind"], evidence_id, reference, now),
                )
                links_added += max(cursor.rowcount, 0)

            for operation in pack.get("proposed_operations", []):
                target = operation["target"]
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO operation_proposals (
                        request_id, operation_id, action, target_system, target_type,
                        target_id, target_model, target_company_id, target_label,
                        requested_executor, payload_json, rationale,
                        approval_required, reversible, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, 'PROPOSED', ?)
                    """,
                    (
                        request_id,
                        operation["operation_id"],
                        operation["action"],
                        target["system"],
                        target["object_type"],
                        str(target["record_id"]),
                        target.get("model"),
                        target.get("company_id"),
                        target.get("label"),
                        operation["requested_executor"],
                        json.dumps(operation["payload"], ensure_ascii=False, sort_keys=True),
                        operation["rationale"],
                        int(operation["reversible"]),
                        now,
                    ),
                )
                proposals_added += max(cursor.rowcount, 0)

            if links_added or proposals_added or existing_revision == 0:
                conn.execute(
                    """
                    INSERT INTO events (
                        request_id, timestamp, actor, action, justification, result
                    ) VALUES (?, ?, ?, 'REQUEST_PACK_INDEXED', ?, 'DONE')
                    """,
                    (
                        request_id,
                        now,
                        actor,
                        f"links={links_added}; proposals={proposals_added}; writes=0",
                    ),
                )
        return {"links_added": links_added, "proposals_added": proposals_added}

    def revise_request(
        self,
        request_id: str,
        *,
        payload: dict[str, Any],
        pack: dict[str, Any],
        decision: TriageDecision,
        actor: str,
    ) -> dict[str, Any]:
        now = utc_now()
        new_status = RequestStatus.QUALIFYING if decision.missing_fields else RequestStatus.READY
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM requests WHERE request_id = ?", (request_id,)).fetchone()
            if not row:
                raise KeyError(request_id)
            if row["status"] not in {RequestStatus.QUALIFYING.value, RequestStatus.READY.value}:
                raise ValueError("Only qualifying or ready requests can be revised")
            revision = conn.execute(
                "SELECT COALESCE(MAX(revision), 0) + 1 AS next FROM request_revisions WHERE request_id = ?",
                (request_id,),
            ).fetchone()["next"]
            conn.execute(
                """
                INSERT INTO request_revisions (
                    request_id, revision, payload_json, decision_json, actor, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    revision,
                    json.dumps(pack, ensure_ascii=False, sort_keys=True),
                    json.dumps(decision.as_dict(), ensure_ascii=False, sort_keys=True),
                    actor,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE requests SET
                    subject = ?, priority = ?, route = ?, confidence = ?, status = ?,
                    payload_json = ?, decision_json = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (
                    payload["subject"],
                    decision.priority.value,
                    decision.route.value,
                    decision.confidence,
                    new_status.value,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    json.dumps(decision.as_dict(), ensure_ascii=False, sort_keys=True),
                    now,
                    request_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO events (
                    request_id, timestamp, actor, action, old_status, new_status,
                    justification, result
                ) VALUES (?, ?, ?, 'REQUEST_REVISED', ?, ?, ?, 'DONE')
                """,
                (
                    request_id,
                    now,
                    actor,
                    row["status"],
                    new_status.value,
                    f"revision={revision}",
                ),
            )
        updated = self.get_request(request_id)
        assert updated is not None
        return updated

    def assert_operation_proposals_compatible(
        self,
        request_id: str,
        operations: list[dict[str, Any]],
    ) -> None:
        with self.connect() as conn:
            rows = {
                row["operation_id"]: dict(row)
                for row in conn.execute(
                    "SELECT * FROM operation_proposals WHERE request_id = ?",
                    (request_id,),
                ).fetchall()
            }
        for operation in operations:
            existing = rows.get(operation["operation_id"])
            if not existing:
                continue
            target = operation["target"]
            expected = {
                "action": operation["action"],
                "target_system": target["system"],
                "target_type": target["object_type"],
                "target_id": str(target["record_id"]),
                "target_model": target.get("model"),
                "target_company_id": target.get("company_id"),
                "target_label": target.get("label"),
                "requested_executor": operation["requested_executor"],
                "payload_json": json.dumps(operation["payload"], ensure_ascii=False, sort_keys=True),
                "rationale": operation["rationale"],
                "reversible": int(operation["reversible"]),
            }
            if any(existing.get(key) != value for key, value in expected.items()):
                raise ValueError(
                    f"Operation proposal {operation['operation_id']} is immutable; use a new operation_id"
                )

    def append_message(
        self,
        request_id: str,
        *,
        source: str,
        source_message_id: str,
        actor: str,
        body: str,
    ) -> bool:
        if not body.strip():
            raise ValueError("message body is required")
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if not conn.execute("SELECT 1 FROM requests WHERE request_id = ?", (request_id,)).fetchone():
                raise KeyError(request_id)
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO request_messages (
                    request_id, source, source_message_id, actor, body, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (request_id, source, source_message_id, actor, body.strip(), now),
            )
            created = cursor.rowcount == 1
            if created:
                conn.execute(
                    """
                    INSERT INTO events (
                        request_id, timestamp, actor, action, justification, result
                    ) VALUES (?, ?, ?, 'MESSAGE_APPENDED', ?, 'DONE')
                    """,
                    (request_id, now, actor, f"source={source}; source_message_id={source_message_id}"),
                )
        return created

    def issue_telegram_start_token(
        self,
        request_id: str,
        *,
        requester_id: str,
        expected_telegram_user_id: str,
        expires_at: str,
    ) -> str:
        raw_token = secrets.token_urlsafe(24)
        digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO telegram_start_tokens (
                    token_hash, request_id, requester_id, expected_telegram_user_id,
                    expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (digest, request_id, requester_id, expected_telegram_user_id, expires_at, now),
            )
        return raw_token

    def consume_telegram_start_token(
        self,
        raw_token: str,
        *,
        telegram_user_id: str,
        chat_id: str,
        actor: str,
    ) -> dict[str, Any]:
        digest = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = utc_now()
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            token = conn.execute(
                "SELECT * FROM telegram_start_tokens WHERE token_hash = ?",
                (digest,),
            ).fetchone()
            if not token or token["consumed_at"]:
                raise ValueError("Telegram start token is invalid or already used")
            if token["expires_at"] < now:
                raise ValueError("Telegram start token has expired")
            if str(token["expected_telegram_user_id"]) != str(telegram_user_id):
                raise PermissionError("Telegram identity does not match the verified collaborator")

            conflicting = conn.execute(
                """
                SELECT requester_id FROM telegram_bindings
                WHERE telegram_user_id = ? AND requester_id != ? AND active = 1
                """,
                (str(telegram_user_id), token["requester_id"]),
            ).fetchone()
            if conflicting:
                raise PermissionError("Telegram identity is already bound to another collaborator")

            existing = conn.execute(
                "SELECT * FROM telegram_bindings WHERE requester_id = ?",
                (token["requester_id"],),
            ).fetchone()
            if existing and str(existing["telegram_user_id"]) != str(telegram_user_id):
                raise PermissionError("Collaborator is already bound to another Telegram identity")

            conn.execute(
                """
                INSERT INTO telegram_bindings (
                    requester_id, telegram_user_id, chat_id, verified_at, active
                ) VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(requester_id) DO UPDATE SET
                    chat_id=excluded.chat_id,
                    verified_at=excluded.verified_at,
                    active=1
                """,
                (token["requester_id"], str(telegram_user_id), str(chat_id), now),
            )
            conn.execute(
                "UPDATE telegram_start_tokens SET consumed_at = ? WHERE token_hash = ?",
                (now, digest),
            )
            conn.execute(
                """
                INSERT INTO events (
                    request_id, timestamp, actor, action, justification, result
                ) VALUES (?, ?, ?, 'TELEGRAM_BOUND', ?, 'DONE')
                """,
                (
                    token["request_id"],
                    now,
                    actor,
                    f"requester_id={token['requester_id']}; telegram_id_verified=true",
                ),
            )
            return {
                "request_id": token["request_id"],
                "requester_id": token["requester_id"],
                "telegram_user_id": str(telegram_user_id),
                "chat_id": str(chat_id),
                "verified_at": now,
            }

    def get_telegram_binding(self, requester_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM telegram_bindings WHERE requester_id = ? AND active = 1",
                (requester_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_requests_for_requester(self, requester_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT * FROM requests
                    WHERE requester_id = ? AND status NOT IN ('DONE', 'REJECTED')
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (requester_id, min(max(limit, 1), 200)),
                ).fetchall()
            ]

    def get_request(self, request_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM requests WHERE request_id = ?", (request_id,)).fetchone()
            return dict(row) if row else None

    def get_request_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM requests WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
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
            links = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM links WHERE request_id = ? ORDER BY id", (request_id,)
                ).fetchall()
            ]
            messages = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM request_messages WHERE request_id = ? ORDER BY message_id",
                    (request_id,),
                ).fetchall()
            ]
            proposals = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM operation_proposals WHERE request_id = ? ORDER BY proposal_id",
                    (request_id,),
                ).fetchall()
            ]
            revisions = [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM request_revisions WHERE request_id = ? ORDER BY revision",
                    (request_id,),
                ).fetchall()
            ]
        request["payload"] = json.loads(request.pop("payload_json"))
        request["decision"] = json.loads(request.pop("decision_json"))
        for proposal in proposals:
            proposal["payload"] = json.loads(proposal.pop("payload_json"))
        for revision in revisions:
            revision["payload"] = json.loads(revision.pop("payload_json"))
            revision["decision"] = json.loads(revision.pop("decision_json"))
        return {
            "request": request,
            "links": links,
            "messages": messages,
            "operation_proposals": proposals,
            "revisions": revisions,
            "events": events,
        }

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
