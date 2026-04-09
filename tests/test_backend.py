import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient

import main
import providers
from questions import DAY_COUNTS, QUESTIONS, SESSIONS


class SessionMetadataTests(unittest.TestCase):
    def test_session_labels_track_question_counts(self):
        self.assertEqual(SESSIONS[0]["sub"], f"All {len(QUESTIONS)} questions")
        self.assertEqual(SESSIONS[1]["sub"], f"{DAY_COUNTS[1]} questions · Core JS + Arrays + Objects")
        self.assertEqual(SESSIONS[2]["sub"], f"{DAY_COUNTS[2]} questions")
        self.assertEqual(SESSIONS[3]["sub"], f"{DAY_COUNTS[3]} questions")

    def test_resolve_api_key_prefers_request_then_env(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "env-key"}, clear=False):
            self.assertEqual(providers.resolve_api_key("groq", "inline-key"), "inline-key")
            self.assertEqual(providers.resolve_api_key("groq", ""), "env-key")

    def test_resolve_api_key_requires_cloud_key_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(providers.ClientInputError):
                providers.resolve_api_key("openai", "")


class ApiRouteTests(unittest.TestCase):
    def make_client(self):
        patcher = patch("main._fetch_ollama_models", new=AsyncMock(return_value=[]))
        patcher.start()
        self.addCleanup(patcher.stop)
        client = TestClient(main.app)
        self.addCleanup(client.close)
        return client

    def test_evaluate_rejects_empty_answer(self):
        client = self.make_client()
        response = client.post("/api/evaluate", json={
            "question_id": QUESTIONS[0]["id"],
            "answer": "   ",
            "provider": "ollama",
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("Answer is required", response.json()["detail"])

    def test_evaluate_maps_provider_response_errors_to_422(self):
        client = self.make_client()
        with patch("main.evaluate_with_provider", new=AsyncMock(side_effect=providers.ProviderResponseError("bad llm output"))):
            response = client.post("/api/evaluate", json={
                "question_id": QUESTIONS[0]["id"],
                "answer": "closures keep access to outer scope",
                "provider": "groq",
                "api_key": "test-key",
            })
        self.assertEqual(response.status_code, 422)
        self.assertIn("bad llm output", response.json()["detail"])

    def test_generate_from_file_rejects_invalid_type(self):
        client = self.make_client()
        response = client.post(
            "/api/generate-from-file",
            data={"provider": "groq", "api_key": "test-key"},
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file type", response.json()["detail"])

    def test_generate_from_file_rejects_oversized_upload(self):
        client = self.make_client()
        response = client.post(
            "/api/generate-from-file",
            data={"provider": "groq", "api_key": "test-key"},
            files={"file": ("resume.pdf", b"x" * (main.MAX_UPLOAD_BYTES + 1), "application/pdf")},
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("max 10 MB", response.json()["detail"])

    def test_providers_expose_backend_key_availability(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "server-key"}, clear=False):
            client = self.make_client()
            response = client.get("/api/providers")

        self.assertEqual(response.status_code, 200)
        providers_payload = {provider["id"]: provider for provider in response.json()["providers"]}
        self.assertTrue(providers_payload["openai"]["server_key_available"])
        self.assertFalse(providers_payload["groq"]["server_key_available"])


if __name__ == "__main__":
    unittest.main()
