import unittest
from types import SimpleNamespace

from ja_video_subtitles.api_util import chat_options, safe_error


class TestApiUtil(unittest.TestCase):
    def test_disable_thinking_only_for_official_deepseek(self):
        self.assertEqual(chat_options(SimpleNamespace(base_url="https://api.deepseek.com/v1")),
                         {"extra_body": {"thinking": {"type": "disabled"}}})
        for url in ("https://example.invalid", "https://api.deepseek.com.example.invalid"):
            self.assertEqual(chat_options(SimpleNamespace(base_url=url)), {})

    def test_secret_error_redaction(self):
        self.assertEqual(safe_error("bad arbitrary-secret", "arbitrary-secret"),
                         "bad [REDACTED]")
        self.assertEqual(safe_error(RuntimeError("token sk-1234567890abcdefgh")),
                         "token [REDACTED]")
