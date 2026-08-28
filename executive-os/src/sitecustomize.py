"""Optional non-secret lifecycle tracing for the dedicated Telegram intake."""

from __future__ import annotations

import functools
import os


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


if (
    os.environ.get("HERMES_SERVICE_MODE") == "internal-intake"
    and _enabled(os.environ.get("HERMES_TELEGRAM_TRACE_LIFECYCLE"))
):
    try:
        from telegram.ext import Application, ExtBot, Updater

        def _trace(cls, method_name: str, label: str) -> None:
            original = getattr(cls, method_name)
            if getattr(original, "_bureau_ahmed_traced", False):
                return

            @functools.wraps(original)
            async def wrapped(self, *args, **kwargs):
                print(f"[telegram-lifecycle] {label} start", flush=True)
                try:
                    result = await original(self, *args, **kwargs)
                except BaseException as exc:
                    print(
                        f"[telegram-lifecycle] {label} error={type(exc).__name__}",
                        flush=True,
                    )
                    raise
                print(f"[telegram-lifecycle] {label} done", flush=True)
                return result

            wrapped._bureau_ahmed_traced = True
            setattr(cls, method_name, wrapped)

        _trace(ExtBot, "initialize", "ExtBot.initialize")
        _trace(Application, "initialize", "Application.initialize")
        _trace(Application, "start", "Application.start")
        _trace(Updater, "start_polling", "Updater.start_polling")
    except Exception as exc:
        print(
            f"[telegram-lifecycle] instrumentation unavailable={type(exc).__name__}",
            flush=True,
        )
