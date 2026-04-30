import json
import asyncio
import importlib.util
import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from memo_clover import memory_manager as mem
from memo_clover.db import DB_PATH as _orig_db_path
from chat_cleaner import parse_conversations, split_by_gap


from memo_clover import db as db_mod

class MemoryManagerReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

        self.old_db = db_mod.DB_PATH
        self.old_index = db_mod.MEMORY_INDEX
        self.old_bank_dir = db_mod.BANK_DIR
        self.old_embed = mem._embed

        db_mod.DB_PATH = self.root / "memory.db"
        db_mod.MEMORY_INDEX = self.root / "MEMORY.md"
        mem.MEMORY_INDEX = self.root / "MEMORY.md"
        db_mod.BANK_DIR = self.root / "bank"
        mem.BANK_DIR = self.root / "bank"
        mem.BANK_DIR.mkdir(parents=True, exist_ok=True)
        mem._embed = lambda text: None

        db = db_mod._get_db()
        db.close()

    def tearDown(self):
        db_mod.DB_PATH = self.old_db
        db_mod.MEMORY_INDEX = self.old_index
        mem.MEMORY_INDEX = self.old_index
        db_mod.BANK_DIR = self.old_bank_dir
        mem.BANK_DIR = self.old_bank_dir
        mem._embed = self.old_embed
        self.temp_dir.cleanup()

    def test_update_and_delete_keep_index_in_sync(self):
        mem.remember("hello world", category="facts")

        updated = mem.update_memory(1, "changed world", "experience", 8)
        self.assertTrue(updated["ok"])
        self.assertIn("changed world", mem.MEMORY_INDEX.read_text(encoding="utf-8"))
        self.assertNotIn("hello world", mem.MEMORY_INDEX.read_text(encoding="utf-8"))

        deleted = mem.delete_memory(1)
        self.assertTrue(deleted["ok"])
        self.assertIn("*0 memories", mem.MEMORY_INDEX.read_text(encoding="utf-8"))

    def test_bank_reindex_cleans_stale_template_rows(self):
        bank_file = mem.BANK_DIR / "test-stale.md"
        bank_file.write_text("# Test\n\n<!-- template only -->\n", encoding="utf-8")

        db = db_mod._get_db()
        db.execute(
            """INSERT INTO bank_chunks
               (file_path, chunk_text, embedding, file_mtime, index_version)
               VALUES (?, ?, ?, ?, ?)""",
            (str(bank_file), "# Test\n\n<!-- template only -->", None, bank_file.stat().st_mtime, 1),
        )
        db.commit()
        db.close()

        mem._index_bank_files()

        con = sqlite3.connect(str(db_mod.DB_PATH))
        try:
            rows = con.execute("SELECT file_path, chunk_text, index_version FROM bank_chunks").fetchall()
        finally:
            con.close()
        self.assertEqual(rows, [])


class ChatCleanerReleaseTests(unittest.TestCase):
    def test_mixed_timestamp_formats_normalize_without_crashing(self):
        sample = [
            {
                "messages": [
                    {"role": "user", "text": "hi", "created_at": 1710028800},
                    {"role": "assistant", "text": "hello", "created_at": "2024-03-10T00:00:00Z"},
                ]
            }
        ]

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(sample, f)
            path = f.name

        try:
            conversations = parse_conversations(path)
            sessions = split_by_gap(conversations)
        finally:
            Path(path).unlink(missing_ok=True)

        self.assertEqual(len(conversations), 1)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(len(sessions[0]), 2)
        self.assertIsNone(sessions[0][0]["ts"].tzinfo)
        self.assertEqual(sessions[0][0]["ts"], sessions[0][1]["ts"])


class CompressContextWrapperTests(unittest.TestCase):
    def test_wrapper_delegates_to_compress_file(self):
        script_path = Path(__file__).parent.parent / "scripts" / "compress_context.py"
        spec = importlib.util.spec_from_file_location("compress_context_wrapper", script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("[one]\n[two]\n")
            context_path = Path(f.name)

        calls = []
        fake_compress = types.ModuleType("memo_clover.compress")
        fake_compress.compress_file = lambda path: calls.append(path)
        fake_package = types.ModuleType("memo_clover")
        fake_package.compress = fake_compress

        try:
            with mock.patch.dict(
                sys.modules,
                {
                    "memo_clover": fake_package,
                    "memo_clover.compress": fake_compress,
                },
            ), mock.patch.object(sys, "argv", ["compress_context.py", str(context_path)]):
                module.main()
        finally:
            context_path.unlink(missing_ok=True)

        self.assertEqual(calls, [context_path])


class DataDirPolicyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent.parent

    def test_hooks_respect_existing_imprint_data_dir(self):
        for rel_path in ["hooks/post-response.sh", "hooks/pre-compact-flush.sh"]:
            text = (self.root / rel_path).read_text(encoding="utf-8")
            self.assertIn('export IMPRINT_DATA_DIR="${IMPRINT_DATA_DIR:-$HOME/.imprint}"', text)
            self.assertNotIn('export IMPRINT_DATA_DIR="$SCRIPT_DIR"', text)

    def test_recent_context_uses_data_dir_as_primary_path(self):
        post_response = (self.root / "hooks/post-response.sh").read_text(encoding="utf-8")
        processor = (self.root / "hooks/post_response_processor.py").read_text(encoding="utf-8")
        updater = (self.root / "update_claude_md.py").read_text(encoding="utf-8")
        cron = (self.root / "cron-task.sh").read_text(encoding="utf-8")

        self.assertIn('CONTEXT_FILE="$IMPRINT_DATA_DIR/recent_context.md"', post_response)
        self.assertIn('CONTEXT_FILE = DATA_DIR / "recent_context.md"', processor)
        self.assertIn('context_file = DATA_DIR / "recent_context.md"', updater)
        self.assertIn('CONTEXT_FILE="$IMPRINT_DATA_DIR/recent_context.md"', cron)

    def test_telegram_service_exports_imprint_data_dir(self):
        service = (self.root / "deploy/imprint-telegram@.service").read_text(encoding="utf-8")
        self.assertIn("Environment=IMPRINT_DATA_DIR=/home/%i/.imprint", service)


class ReindexDocumentationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent.parent

    def test_memory_reindex_docs_cover_derived_indexes(self):
        api = (self.root / "docs/api-reference.md").read_text(encoding="utf-8")
        runbook = (self.root / "docs/deployment-runbook.md").read_text(encoding="utf-8")
        lifecycle = (self.root / "docs/memory-lifecycle.md").read_text(encoding="utf-8")

        for text in (api, runbook, lifecycle):
            self.assertIn("memories_fts", text)
            self.assertIn("conversation_log_fts", text)
            self.assertIn("bank_chunks", text)

        self.assertIn("SQLite FTS5 或 bank_chunks 索引异常", runbook)
        self.assertIn("SQLite FTS5 检索", lifecycle)


class DashboardSummaryApiTests(unittest.TestCase):
    def test_summary_put_invalid_json_returns_400(self):
        from packages.imprint_dashboard import dashboard

        class BadJsonRequest:
            async def json(self):
                raise json.JSONDecodeError("bad json", "{", 0)

        response = asyncio.run(dashboard.api_update_summary(1, BadJsonRequest()))

        self.assertEqual(response.status_code, 400)
        self.assertIn("invalid JSON body", response.body.decode("utf-8"))

    def test_summary_put_non_object_json_returns_400(self):
        from packages.imprint_dashboard import dashboard

        class ListJsonRequest:
            async def json(self):
                return []

        response = asyncio.run(dashboard.api_update_summary(1, ListJsonRequest()))

        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON body must be an object", response.body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
