"""
tests/unit/test_memory.py — Unit tests for ScopedMemory and MemoryItem.

Uses an in-memory SQLite database (via a patched resolve_data_file) so no
files are written to disk during the test run.

Run with:  pytest tests/unit/test_memory.py -v
"""

import sys
import os
import hashlib
import sqlite3
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))

import pytest
import memory as _mem_module
from memory import MemoryItem, ScopedMemory, make_item


# ---------------------------------------------------------------------------
# Test fixture — isolated temp-dir database per test
# ---------------------------------------------------------------------------

@pytest.fixture
def mem(tmp_path):
    """Return a ScopedMemory backed by a temp-dir SQLite file."""
    db_file = str(tmp_path / "memory.db")
    with patch.object(_mem_module, "resolve_data_file", return_value=db_file):
        yield ScopedMemory("test_company")


def _item(key="last_emotion", value="frustrated", scope="client",
          scope_id="abc123", ttl_hours=24) -> MemoryItem:
    return make_item(scope, scope_id, key, value, ttl_hours=ttl_hours)


# ---------------------------------------------------------------------------
# MemoryItem construction and redaction
# ---------------------------------------------------------------------------

class TestMemoryItem:
    def test_checksum_is_8_chars(self):
        item = _item()
        assert len(item.checksum) == 8
        assert all(c in "0123456789abcdef" for c in item.checksum)

    def test_redaction_removes_email_from_value(self):
        item = _item(value="Sent from user@example.com about delivery")
        assert "[EMAIL]" in item.value
        assert "user@example.com" not in item.value

    def test_clean_value_unchanged(self):
        item = _item(value="frustrated")
        assert item.value == "frustrated"

    def test_not_expired_when_fresh(self):
        item = _item(ttl_hours=24)
        assert item.is_expired() is False

    def test_expired_when_ttl_zero(self):
        item = _item(ttl_hours=0)
        # ttl=0 → expires_at == created_at, which is already ≤ now
        assert item.is_expired() is True

    def test_expired_past_timestamp(self):
        past = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        item = MemoryItem(
            scope="client", scope_id="x", key="k", value="v",
            created_at=past, expires_at=past,
        )
        assert item.is_expired() is True

    def test_checksum_differs_for_different_values(self):
        a = _item(value="angry")
        b = _item(value="calm")
        assert a.checksum != b.checksum

    def test_make_item_sets_correct_fields(self):
        item = make_item("client", "cid1", "last_intent", "complaint", ttl_hours=48)
        assert item.scope    == "client"
        assert item.scope_id == "cid1"
        assert item.key      == "last_intent"
        assert item.value    == "complaint"
        assert item.expires_at > item.created_at


# ---------------------------------------------------------------------------
# store() + recall()
# ---------------------------------------------------------------------------

class TestStoreAndRecall:
    def test_stored_item_is_recalled(self, mem):
        item = _item(key="last_emotion", value="frustrated")
        mem.store(item)
        results = mem.recall("client", "abc123")
        assert len(results) == 1
        assert results[0].key   == "last_emotion"
        assert results[0].value == "frustrated"

    def test_multiple_keys_recalled(self, mem):
        mem.store(_item(key="last_emotion", value="angry"))
        mem.store(_item(key="last_intent",  value="complaint"))
        results = mem.recall("client", "abc123")
        keys = {r.key for r in results}
        assert "last_emotion" in keys
        assert "last_intent"  in keys

    def test_different_scope_id_not_returned(self, mem):
        mem.store(_item(scope_id="abc123", key="k", value="v1"))
        mem.store(_item(scope_id="xyz999", key="k", value="v2"))
        results = mem.recall("client", "abc123")
        assert all(r.scope_id == "abc123" for r in results)
        assert len(results) == 1

    def test_upsert_updates_value(self, mem):
        mem.store(_item(key="last_emotion", value="frustrated"))
        mem.store(_item(key="last_emotion", value="angry"))      # same key
        results = mem.recall("client", "abc123")
        assert len(results) == 1
        assert results[0].value == "angry"

    def test_recall_empty_scope_returns_empty(self, mem):
        assert mem.recall("client", "nonexistent") == []


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

class TestExpiry:
    def test_expired_item_not_recalled(self, mem):
        past  = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        item  = MemoryItem(
            scope="client", scope_id="abc123", key="old_emotion", value="frustrated",
            created_at=past, expires_at=past,
        )
        mem.store(item)
        results = mem.recall("client", "abc123")
        assert all(r.key != "old_emotion" for r in results)

    def test_fresh_item_returned_after_expired_skipped(self, mem):
        past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        mem.store(MemoryItem(
            scope="client", scope_id="abc123", key="old", value="x",
            created_at=past, expires_at=past,
        ))
        mem.store(_item(key="new_emotion", value="calm"))
        results = mem.recall("client", "abc123")
        keys = {r.key for r in results}
        assert "new_emotion" in keys
        assert "old"         not in keys


# ---------------------------------------------------------------------------
# Cap enforcement — MAX_ITEMS_PER_SCOPE = 20
# ---------------------------------------------------------------------------

class TestCap:
    def test_25_items_capped_to_20(self, mem):
        for i in range(25):
            mem.store(make_item("client", "abc123", f"key_{i:02d}", f"val_{i}"))
        results = mem.recall("client", "abc123")
        assert len(results) == 20

    def test_cap_keeps_newest_items(self, mem):
        for i in range(25):
            mem.store(make_item("client", "abc123", f"key_{i:02d}", f"val_{i}"))
        results   = mem.recall("client", "abc123")
        kept_keys = {r.key for r in results}
        # The 5 oldest (key_00 … key_04) should have been evicted
        for old in [f"key_{i:02d}" for i in range(5)]:
            assert old not in kept_keys, f"{old} should have been evicted"

    def test_cap_does_not_affect_other_scopes(self, mem):
        for i in range(25):
            mem.store(make_item("client", "abc123", f"key_{i:02d}", "v"))
        # Store one item under a different scope_id
        mem.store(make_item("client", "xyz999", "solo_key", "solo_val"))
        other = mem.recall("client", "xyz999")
        assert len(other) == 1


# ---------------------------------------------------------------------------
# recall_as_context()
# ---------------------------------------------------------------------------

class TestRecallAsContext:
    def test_format_contains_key_and_value(self, mem):
        mem.store(_item(key="last_emotion", value="frustrated"))
        ctx_str = mem.recall_as_context("client", "abc123")
        assert "[MEMORY:last_emotion]" in ctx_str
        assert "frustrated"            in ctx_str

    def test_multiple_items_each_on_own_line(self, mem):
        mem.store(_item(key="last_emotion", value="angry"))
        mem.store(_item(key="last_intent",  value="complaint"))
        lines = mem.recall_as_context("client", "abc123").strip().splitlines()
        assert len(lines) == 2

    def test_empty_scope_returns_empty_string(self, mem):
        assert mem.recall_as_context("client", "nobody") == ""


# ---------------------------------------------------------------------------
# purge_expired()
# ---------------------------------------------------------------------------

class TestPurgeExpired:
    def test_purge_removes_expired_items(self, mem):
        past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        for key in ("a", "b", "c"):
            mem.store(MemoryItem(
                scope="client", scope_id="abc123", key=key, value="v",
                created_at=past, expires_at=past,
            ))
        deleted = mem.purge_expired()
        assert deleted == 3

    def test_purge_leaves_fresh_items(self, mem):
        past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        mem.store(MemoryItem(
            scope="client", scope_id="abc123", key="old", value="v",
            created_at=past, expires_at=past,
        ))
        mem.store(_item(key="fresh", value="v"))
        mem.purge_expired()
        results = mem.recall("client", "abc123")
        assert len(results) == 1
        assert results[0].key == "fresh"

    def test_purge_returns_zero_when_nothing_expired(self, mem):
        mem.store(_item())
        assert mem.purge_expired() == 0


# ---------------------------------------------------------------------------
# Scope isolation
# ---------------------------------------------------------------------------

class TestScopeIsolation:
    def test_client_scope_does_not_leak_to_account(self, mem):
        mem.store(make_item("client",  "id1", "k", "v1"))
        mem.store(make_item("account", "id1", "k", "v2"))
        client  = mem.recall("client",  "id1")
        account = mem.recall("account", "id1")
        assert client[0].value  == "v1"
        assert account[0].value == "v2"

    def test_ticket_scope_separate(self, mem):
        mem.store(make_item("ticket", "t42",  "note", "draft ok"))
        mem.store(make_item("client", "c42",  "note", "frustrated"))
        assert mem.recall("ticket", "t42")[0].value == "draft ok"
        assert mem.recall("client", "c42")[0].value == "frustrated"


# ---------------------------------------------------------------------------
# Redaction contract — only _redact() is tested here (unit)
# ---------------------------------------------------------------------------

class TestRedaction:
    def test_email_in_stored_value_is_redacted(self, mem):
        mem.store(_item(value="Contact: alice@acme.com"))
        r = mem.recall("client", "abc123")
        assert "alice@acme.com" not in r[0].value
        assert "[EMAIL]"        in r[0].value

    def test_non_pii_value_unchanged(self, mem):
        mem.store(_item(value="complaint about delay"))
        r = mem.recall("client", "abc123")
        assert r[0].value == "complaint about delay"
