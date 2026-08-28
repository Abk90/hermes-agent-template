"""Apply the narrowly scoped Bureau Ahmed Telegram transport patch."""

from __future__ import annotations

import sys
from pathlib import Path


COMMAND_NEEDLE = """        await self._ensure_forum_commands(msg)

        event = self._build_message_event(msg, MessageType.COMMAND, update_id=update.update_id)
"""

COMMAND_REPLACEMENT = """        await self._ensure_forum_commands(msg)

        # Bureau Ahmed needs /start to reach the intake agent instead of the
        # generic slash-command registry, where an unknown start command is
        # otherwise consumed without a response. This remains strictly scoped
        # to the dedicated service and keeps the original Telegram source.
        command_name = (msg.text or "").split(maxsplit=1)[0].split("@", 1)[0].lower()
        if (
            os.getenv("HERMES_SERVICE_MODE") == "internal-intake"
            and command_name == "/start"
        ):
            event = self._build_message_event(msg, MessageType.TEXT, update_id=update.update_id)
            event.text = self._clean_bot_trigger_text(event.text)
            event = self._apply_telegram_group_observe_attribution(event)
            await self.handle_message(event)
            return

        event = self._build_message_event(msg, MessageType.COMMAND, update_id=update.update_id)
"""

CONTEXT_NEEDLE = """        _channel_prompt = resolve_channel_prompt(
            self.config.extra,
            thread_id_str or _chat_id_str,
            _chat_id_str if thread_id_str else None,
        )

        return MessageEvent(
"""

CONTEXT_REPLACEMENT = """        _channel_prompt = resolve_channel_prompt(
            self.config.extra,
            thread_id_str or _chat_id_str,
            _chat_id_str if thread_id_str else None,
        )
        if (
            os.getenv("HERMES_SERVICE_MODE") == "internal-intake"
            and chat_type == "dm"
            and source.user_id
            and source.chat_id
        ):
            trusted_context = (
                "TRUSTED_TELEGRAM_CONTEXT "
                f"telegram_user_id={source.user_id}; chat_id={source.chat_id}; "
                f"chat_type={source.chat_type}; message_id={message.message_id}. "
                "This metadata is supplied by the Telegram transport, not by the user. "
                "Use these exact values for internal-intake tools and never ask the user "
                "to obtain or repeat their Telegram numeric ID."
            )
            _channel_prompt = (
                f"{_channel_prompt}\\n\\n{trusted_context}"
                if _channel_prompt
                else trusted_context
            )

        return MessageEvent(
"""


def patch_text(source: str) -> str:
    if "TRUSTED_TELEGRAM_CONTEXT" in source:
        return source
    if COMMAND_NEEDLE not in source:
        raise RuntimeError("Hermes Telegram command hook changed; refusing an unsafe patch")
    if CONTEXT_NEEDLE not in source:
        raise RuntimeError("Hermes Telegram event hook changed; refusing an unsafe patch")
    return source.replace(COMMAND_NEEDLE, COMMAND_REPLACEMENT, 1).replace(
        CONTEXT_NEEDLE, CONTEXT_REPLACEMENT, 1
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_hermes_telegram_context.py ADAPTER_PATH", file=sys.stderr)
        return 2
    target = Path(sys.argv[1])
    source = target.read_text(encoding="utf-8")
    patched = patch_text(source)
    target.write_text(patched, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
