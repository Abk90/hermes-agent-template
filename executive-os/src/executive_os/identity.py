from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any


class IdentityError(ValueError):
    pass


@dataclass(frozen=True)
class DeviceIdentity:
    credential_id: str
    requester_id: str
    display_name: str
    device_id: str
    token_sha256: str
    telegram_user_id: str | None = None
    odoo_company_ids: tuple[str, ...] = ()
    active: bool = True


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class IdentityRegistry:
    def __init__(self, identities: list[DeviceIdentity] | None = None):
        self.identities = identities or []
        self._validate()

    @classmethod
    def from_json(cls, raw: str | None) -> "IdentityRegistry":
        if not raw:
            return cls([])
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise IdentityError("Device credentials JSON is invalid") from exc
        rows = parsed.get("credentials") if isinstance(parsed, dict) else None
        if not isinstance(rows, list):
            raise IdentityError("Device credentials JSON must contain a credentials list")
        identities: list[DeviceIdentity] = []
        for row in rows:
            if not isinstance(row, dict):
                raise IdentityError("Each device credential must be an object")
            company_ids = row.get("odoo_company_ids", [])
            if not isinstance(company_ids, list):
                raise IdentityError("odoo_company_ids must be a list")
            try:
                identities.append(
                    DeviceIdentity(
                        credential_id=str(row["credential_id"]),
                        requester_id=str(row["requester_id"]),
                        display_name=str(row["display_name"]),
                        device_id=str(row["device_id"]),
                        token_sha256=str(row["token_sha256"]).lower(),
                        telegram_user_id=(str(row["telegram_user_id"]) if row.get("telegram_user_id") else None),
                        odoo_company_ids=tuple(str(value) for value in company_ids),
                        active=bool(row.get("active", True)),
                    )
                )
            except KeyError as exc:
                raise IdentityError(f"Missing device credential field: {exc.args[0]}") from exc
        return cls(identities)

    def _validate(self) -> None:
        credential_ids: set[str] = set()
        device_ids: set[str] = set()
        telegram_ids: dict[str, DeviceIdentity] = {}
        for identity in self.identities:
            if not identity.credential_id or not identity.requester_id or not identity.display_name or not identity.device_id:
                raise IdentityError("Credential identity fields must be non-empty")
            if len(identity.token_sha256) != 64 or any(char not in "0123456789abcdef" for char in identity.token_sha256):
                raise IdentityError(f"Invalid token hash for credential {identity.credential_id}")
            if any(not company_id.isdigit() or int(company_id) <= 0 for company_id in identity.odoo_company_ids):
                raise IdentityError(f"Invalid Odoo company scope for credential {identity.credential_id}")
            if identity.credential_id in credential_ids:
                raise IdentityError(f"Duplicate credential_id: {identity.credential_id}")
            if identity.device_id in device_ids:
                raise IdentityError(f"Duplicate device_id: {identity.device_id}")
            credential_ids.add(identity.credential_id)
            device_ids.add(identity.device_id)
            if identity.telegram_user_id and identity.active:
                owner = telegram_ids.get(identity.telegram_user_id)
                if owner and owner.requester_id != identity.requester_id:
                    raise IdentityError(
                        f"Telegram user ID {identity.telegram_user_id} is assigned to multiple collaborators"
                    )
                if owner and (
                    owner.display_name != identity.display_name
                    or owner.odoo_company_ids != identity.odoo_company_ids
                ):
                    raise IdentityError(
                        f"Telegram user ID {identity.telegram_user_id} has inconsistent identity scopes"
                    )
                telegram_ids[identity.telegram_user_id] = identity

    def authenticate(self, token: str) -> DeviceIdentity | None:
        candidate = token_sha256(token)
        found: DeviceIdentity | None = None
        for identity in self.identities:
            matches = hmac.compare_digest(candidate, identity.token_sha256)
            if matches and identity.active:
                found = identity
        return found

    def by_telegram_user_id(self, telegram_user_id: str | int) -> DeviceIdentity | None:
        exact = str(telegram_user_id)
        matches = [
            identity
            for identity in self.identities
            if identity.active and identity.telegram_user_id == exact
        ]
        if len(matches) > 1:
            matches.sort(key=lambda identity: identity.credential_id)
        return matches[0] if matches else None

    @property
    def active_count(self) -> int:
        return sum(1 for identity in self.identities if identity.active)


def registry_public_summary(registry: IdentityRegistry) -> dict[str, Any]:
    return {"active_credentials": registry.active_count}
