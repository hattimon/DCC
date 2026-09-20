import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

import DockerControlCenter as dcc


class LlmProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_settings_dialog_lists_all_providers_and_persists_provider_secret(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = QSettings(str(root / "ui.ini"), QSettings.Format.IniFormat)
            secrets = dcc.SecretStore(root / "secrets.json")
            dialog = dcc.LlmSettingsDialog(settings, secrets, dcc.TEXTS["EN"])

            providers = [dialog.provider_combo.itemData(index) for index in range(dialog.provider_combo.count())]
            self.assertEqual(providers, dcc.LLM_PROVIDER_ORDER)

            for provider in dcc.LLM_PROVIDER_ORDER:
                dialog.provider_combo.setCurrentIndex(dialog.provider_combo.findData(provider))
                self.assertGreater(dialog.model_combo.count(), 0, provider)
                self.assertEqual(dialog.api_key_edit.isHidden(), provider == "ollama")
                self.assertEqual(dialog.ollama_url_edit.isHidden(), provider != "ollama")

            dialog.provider_combo.setCurrentIndex(dialog.provider_combo.findData("anthropic"))
            dialog.api_key_edit.setText("test-anthropic-key")
            dialog.model_combo.setCurrentText("claude-opus-5")
            dialog.save_and_close()

            self.assertEqual(secrets.get_secret("llm/anthropic_api_key"), "test-anthropic-key")
            self.assertEqual(settings.value("llm/anthropic_model"), "claude-opus-5")

    def test_model_discovery_parsing(self):
        original_request_json = dcc.request_json

        def fake_request_json(url, headers=None, payload=None, timeout=20):
            if "anthropic.com/v1/models" in url:
                return {"data": [{"id": "claude-opus-5"}, {"id": "other"}]}
            if "generativelanguage.googleapis.com/v1beta/models?" in url:
                return {
                    "models": [
                        {
                            "name": "models/gemini-3.8-flash",
                            "supportedGenerationMethods": ["generateContent"],
                        },
                        {
                            "name": "models/gemini-embedding-001",
                            "supportedGenerationMethods": ["embedContent"],
                        },
                    ]
                }
            if "api.openai.com/v1/models" in url:
                return {"data": [{"id": "gpt-5.6"}, {"id": "text-embedding-3-large"}]}
            if "api.x.ai/v1/models" in url:
                return {"data": [{"id": "grok-4.6"}]}
            return {}

        try:
            dcc.request_json = fake_request_json
            self.assertEqual(dcc.fetch_anthropic_models("x"), ["claude-opus-5"])
            self.assertEqual(dcc.fetch_gemini_models("x"), ["gemini-3.8-flash"])
            self.assertEqual(dcc.fetch_openai_models("x"), ["gpt-5.6"])
            self.assertEqual(dcc.fetch_provider_models("xai", api_key="x"), ["grok-4.6"])
        finally:
            dcc.request_json = original_request_json

    def test_provider_request_shapes(self):
        original_request_json = dcc.request_json
        calls = []

        def fake_request_json(url, headers=None, payload=None, timeout=20):
            calls.append((url, headers or {}, payload or {}))
            if "anthropic.com/v1/messages" in url:
                return {"content": [{"type": "text", "text": "anthropic-ok"}]}
            if "generativelanguage.googleapis.com" in url:
                return {"candidates": [{"content": {"parts": [{"text": "gemini-ok"}]}}]}
            return {"choices": [{"message": {"content": "compat-ok"}}]}

        try:
            dcc.request_json = fake_request_json
            self.assertEqual(
                dcc.call_anthropic_model("k", "claude-opus-5", "sys", "usr"),
                "anthropic-ok",
            )
            self.assertEqual(
                dcc.call_gemini_model("k", "gemini-3.8-flash", "sys", "usr"),
                "gemini-ok",
            )
            self.assertEqual(
                dcc.call_openai_compatible_model("https://api.x.ai/v1", "k", "grok-4.6", "sys", "usr"),
                "compat-ok",
            )
        finally:
            dcc.request_json = original_request_json

        self.assertEqual(calls[0][1]["anthropic-version"], "2023-06-01")
        self.assertEqual(calls[1][1]["x-goog-api-key"], "k")
        self.assertTrue(calls[2][0].endswith("/chat/completions"))


if __name__ == "__main__":
    unittest.main()
