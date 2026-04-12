import os
import sys
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient

import config
import main
import providers
from questions import DAY_COUNTS, QUESTIONS, SESSIONS
from session_store import MemorySessionStore, SQLiteSessionStore


class ConfigTests(unittest.TestCase):
    def test_get_config_value_reads_dotenv_without_mutating_process_env(self):
        with TemporaryDirectory() as tmp_dir:
            project_env = Path(tmp_dir) / ".env"
            project_env.write_text("OPENAI_API_KEY=file-key\n", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                value = config.get_config_value(
                    "OPENAI_API_KEY",
                    project_env_path=project_env,
                    backend_env_path=Path(tmp_dir) / "missing.env",
                )

            self.assertEqual(value, "file-key")
            self.assertNotIn("OPENAI_API_KEY", os.environ)

    def test_process_env_overrides_dotenv_values(self):
        with TemporaryDirectory() as tmp_dir:
            project_env = Path(tmp_dir) / ".env"
            project_env.write_text("OPENAI_API_KEY=file-key\n", encoding="utf-8")

            value = config.get_config_value(
                "OPENAI_API_KEY",
                env={"OPENAI_API_KEY": "process-key"},
                project_env_path=project_env,
                backend_env_path=Path(tmp_dir) / "missing.env",
            )

            self.assertEqual(value, "process-key")


class SessionStoreTests(unittest.TestCase):
    def test_sqlite_session_store_persists_across_instances(self):
        with TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "sessions.sqlite3"
            store_a = SQLiteSessionStore(db_path)
            store_a.set("session-1", {"state": {"currentQuestionNumber": 3}, "provider": "gemini"})

            store_b = SQLiteSessionStore(db_path)
            self.assertEqual(
                store_b.get("session-1"),
                {"state": {"currentQuestionNumber": 3}, "provider": "gemini"},
            )

            store_b.delete("session-1")
            self.assertIsNone(store_a.get("session-1"))


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

        session_store_patcher = patch.object(main, "INTERVIEW_SESSION_STORE", new=MemorySessionStore())
        session_store_patcher.start()
        self.addCleanup(session_store_patcher.stop)

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
        with patch.dict(os.environ, {
            "OPENAI_API_KEY": "server-key",
            "GROQ_API_KEY": "",
            "GEMINI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
        }, clear=False):
            client = self.make_client()
            response = client.get("/api/providers")

        self.assertEqual(response.status_code, 200)
        providers_payload = {provider["id"]: provider for provider in response.json()["providers"]}
        self.assertTrue(providers_payload["openai"]["server_key_available"])
        self.assertFalse(providers_payload["groq"]["server_key_available"])

    def test_interview_report_uses_backend_persisted_answers(self):
        client = self.make_client()
        session_id = "session-123"
        main.INTERVIEW_SESSION_STORE.set(
            session_id,
            {
                "blueprint": {
                    "candidate_name": "Candidate",
                    "primary_domain": "React Frontend Development",
                    "seniority_level": "senior",
                    "experience_years": 8,
                },
                "profile": {
                    "domain": "React Frontend Development",
                    "roles": ["Senior Frontend Engineer"],
                    "yearsOfExperience": 8,
                    "experienceLevel": "senior",
                    "isTechnical": True,
                    "topSkills": ["React"],
                },
                "state": {
                    "currentQuestionNumber": 1,
                    "current_question_category": "intro",
                    "questionsAsked": ["Tell me about yourself."],
                    "answers": [],
                },
                "provider": "groq",
                "model": "llama-3.1-8b-instant",
            },
        )

        eval_result = {
            "score": 88,
            "verdict": "correct",
            "strength": "Clear career narrative",
            "missing": "",
            "gaps": [],
            "hint": "",
            "ideal": "I build frontend systems with React.",
        }
        with patch("main.evaluate_with_provider", new=AsyncMock(return_value=eval_result)):
            response = client.post(
                "/api/evaluate",
                json={
                    "question_id": "interview-1",
                    "question_text": "Tell me about yourself.",
                    "section": "Introduction",
                    "answer": "I have been building React applications for eight years.",
                    "provider": "groq",
                    "api_key": "test-key",
                    "interview_session_id": session_id,
                },
            )

        self.assertEqual(response.status_code, 200)
        persisted_answers = main.INTERVIEW_SESSION_STORE.get(session_id)["state"]["answers"]
        self.assertEqual(len(persisted_answers), 1)
        self.assertEqual(persisted_answers[0]["score"], 88)
        self.assertEqual(persisted_answers[0]["questionIndex"], 1)

        with patch("main.generate_session_report", new=AsyncMock(return_value={"overall_score": 88, "next_steps": []})) as report_mock:
            report_response = client.post(
                "/api/interview/report",
                json={
                    "session_id": session_id,
                    "provider": "groq",
                    "api_key": "test-key",
                    "answers": [],
                },
            )

        self.assertEqual(report_response.status_code, 200)
        report_answers = report_mock.await_args.kwargs["answers"]
        self.assertEqual(len(report_answers), 1)
        self.assertEqual(report_answers[0]["score"], 88)
        self.assertEqual(report_response.json()["answers"][0]["score"], 88)


if __name__ == "__main__":
    unittest.main()
