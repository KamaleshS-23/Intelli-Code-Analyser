import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ai_assistant.provider import FallbackProvider


class DummyGeminiProvider:
    def generate(self, prompt, context=None):
        raise RuntimeError("Gemini returned 429")


class DummyOpenAIProvider:
    def generate(self, prompt, context=None):
        return "fallback answer from openai"


class FallbackProviderTests(unittest.TestCase):
    def test_fallback_tries_other_provider_when_primary_fails(self):
        provider = FallbackProvider([DummyGeminiProvider(), DummyOpenAIProvider()])
        self.assertEqual(provider.generate("test prompt"), "fallback answer from openai")


if __name__ == "__main__":
    unittest.main()
