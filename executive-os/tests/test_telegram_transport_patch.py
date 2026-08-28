from __future__ import annotations

import unittest

from patches.patch_hermes_telegram_context import (
    COMMAND_NEEDLE,
    CONTEXT_NEEDLE,
    patch_text,
)


class TelegramTransportPatchTests(unittest.TestCase):
    def test_patch_routes_start_and_injects_trusted_transport_context(self):
        source = "prefix\n" + COMMAND_NEEDLE + "middle\n" + CONTEXT_NEEDLE + "suffix\n"
        patched = patch_text(source)
        self.assertIn('command_name == "/start"', patched)
        self.assertIn("MessageType.TEXT", patched)
        self.assertIn("TRUSTED_TELEGRAM_CONTEXT", patched)
        self.assertIn("telegram_user_id={source.user_id}", patched)
        self.assertIn("chat_id={source.chat_id}", patched)
        self.assertEqual(patched, patch_text(patched))


if __name__ == "__main__":
    unittest.main()
