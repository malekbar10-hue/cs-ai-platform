"""
tests/unit/test_prompt_registry.py — Unit tests for PromptRegistry and PromptSpec.

No database, network, or LLM required.
Run with:  pytest tests/unit/test_prompt_registry.py -v
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "cs_ai", "engine"))

import pytest
from prompt_registry import PromptSpec, PromptRegistry, get_registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec(content: str = "Hello {name}!", variables=None, **kwargs) -> PromptSpec:
    defaults = dict(
        prompt_id="test.prompt",
        version="1.0.0",
        content=content,
        variables=variables or ["name"],
        changelog="test",
    )
    defaults.update(kwargs)
    return PromptSpec(**defaults)


def _tmp_registry(prompts: dict[str, dict]) -> PromptRegistry:
    """Write prompt JSON files to a temp dir and return a PromptRegistry over it."""
    d = tempfile.mkdtemp()
    for fname, data in prompts.items():
        with open(os.path.join(d, fname), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    return PromptRegistry(d)


# ---------------------------------------------------------------------------
# PromptSpec construction and checksum
# ---------------------------------------------------------------------------

class TestPromptSpec:
    def test_checksum_is_12_char_hex(self):
        spec = _spec()
        assert len(spec.checksum) == 12
        assert all(c in "0123456789abcdef" for c in spec.checksum)

    def test_checksum_derived_from_content(self):
        s1 = _spec(content="Hello {name}!")
        s2 = _spec(content="Goodbye {name}!")
        assert s1.checksum != s2.checksum

    def test_same_content_same_checksum(self):
        s1 = _spec(content="Static prompt text")
        s2 = _spec(content="Static prompt text")
        assert s1.checksum == s2.checksum

    def test_provided_checksum_overwritten(self):
        """__post_init__ always recomputes checksum from content."""
        spec = PromptSpec(
            prompt_id="x", version="1.0.0",
            content="Hello {name}!", checksum="WRONG",
        )
        assert spec.checksum != "WRONG"
        assert len(spec.checksum) == 12

    def test_default_changelog_empty(self):
        spec = PromptSpec(prompt_id="x", version="1.0.0", content="hi")
        assert spec.changelog == ""

    def test_default_variables_empty_list(self):
        spec = PromptSpec(prompt_id="x", version="1.0.0", content="hi")
        assert spec.variables == []


# ---------------------------------------------------------------------------
# PromptSpec.render()
# ---------------------------------------------------------------------------

class TestRender:
    def test_render_single_variable(self):
        spec = _spec(content="Hello {name}!")
        assert spec.render(name="World") == "Hello World!"

    def test_render_multiple_variables(self):
        spec = _spec(
            content=    "{greeting}, {name}! Welcome to {place}.",
            variables=  ["greeting", "name", "place"],
        )
        result = spec.render(greeting="Hi", name="Alice", place="Paris")
        assert result == "Hi, Alice! Welcome to Paris."

    def test_render_no_variables_static_prompt(self):
        spec = _spec(content="Static prompt text.", variables=[])
        assert spec.render() == "Static prompt text."

    def test_render_missing_variable_raises_value_error(self):
        spec = _spec(content="Hello {name}!", variables=["name"])
        with pytest.raises(ValueError) as exc_info:
            spec.render()
        assert "name" in str(exc_info.value)
        assert "test.prompt" in str(exc_info.value)

    def test_render_escaped_braces_output_literal_braces(self):
        spec = _spec(
            content=    'Return JSON: {{"key": "{value}"}}',
            variables=  ["value"],
        )
        result = spec.render(value="hello")
        assert result == 'Return JSON: {"key": "hello"}'

    def test_render_returns_non_empty_string(self):
        spec = _spec(content="Prompt body: {body}", variables=["body"])
        result = spec.render(body="test content")
        assert len(result) > 0

    def test_render_extra_kwargs_ignored(self):
        spec = _spec(content="Hello {name}!", variables=["name"])
        # Extra kwargs are silently ignored by str.format
        result = spec.render(name="Bob", unused="ignored")
        assert result == "Hello Bob!"


# ---------------------------------------------------------------------------
# PromptRegistry
# ---------------------------------------------------------------------------

class TestPromptRegistry:
    def test_get_returns_spec(self):
        reg = _tmp_registry({
            "my_prompt.json": {
                "prompt_id": "my_prompt",
                "version":   "1.0.0",
                "content":   "Hello {name}",
                "variables": ["name"],
            }
        })
        spec = reg.get("my_prompt")
        assert isinstance(spec, PromptSpec)
        assert spec.prompt_id == "my_prompt"

    def test_get_missing_raises_key_error(self):
        reg = _tmp_registry({})
        with pytest.raises(KeyError) as exc_info:
            reg.get("nonexistent")
        assert "nonexistent" in str(exc_info.value)

    def test_checksum_computed_on_load(self):
        import hashlib
        content = "My prompt content"
        reg = _tmp_registry({
            "p.json": {"prompt_id": "p", "version": "1.0.0", "content": content}
        })
        expected = hashlib.sha256(content.encode()).hexdigest()[:12]
        assert reg.get("p").checksum == expected

    def test_non_json_files_ignored(self):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "README.txt"), "w") as fh:
            fh.write("not a prompt")
        with open(os.path.join(d, "p.json"), "w") as fh:
            json.dump({"prompt_id": "p", "version": "1.0.0", "content": "hi"}, fh)
        reg = PromptRegistry(d)
        assert reg.get("p").prompt_id == "p"

    def test_missing_dir_does_not_raise(self):
        reg = PromptRegistry("/nonexistent/path/that/does/not/exist")
        with pytest.raises(KeyError):
            reg.get("anything")

    def test_all_ids_sorted(self):
        reg = _tmp_registry({
            "b.json": {"prompt_id": "b", "version": "1.0.0", "content": "B"},
            "a.json": {"prompt_id": "a", "version": "1.0.0", "content": "A"},
        })
        assert reg.all_ids() == ["a", "b"]

    def test_loading_same_file_twice_same_checksum(self):
        content = "Stable content"
        data = {"prompt_id": "stable", "version": "1.0.0", "content": content}
        reg1 = _tmp_registry({"stable.json": data})
        reg2 = _tmp_registry({"stable.json": data})
        assert reg1.get("stable").checksum == reg2.get("stable").checksum


# ---------------------------------------------------------------------------
# Production prompt files (integration smoke tests)
# ---------------------------------------------------------------------------

class TestProductionPrompts:
    def test_get_registry_returns_registry(self):
        reg = get_registry()
        assert isinstance(reg, PromptRegistry)

    def test_response_system_exists(self):
        spec = get_registry().get("response_system")
        assert isinstance(spec, PromptSpec)
        assert spec.version == "1.0.0"

    def test_qa_review_exists(self):
        spec = get_registry().get("qa_review")
        assert isinstance(spec, PromptSpec)

    def test_triage_system_exists(self):
        spec = get_registry().get("triage_system")
        assert isinstance(spec, PromptSpec)

    def test_response_system_render_with_all_variables(self):
        spec = get_registry().get("response_system")
        result = spec.render(
            role=               "Customer Service Manager",
            company=            "Acme Corp",
            signature=          "Jane Smith | CS Team",
            customer_profile=   "CUSTOMER ANALYSIS:\n- Language: English",
            order_block=        "ORDER DATA: ORD-001 shipped",
            profile_context=    "",
            trajectory_context= "",
            kb_context=         "",
            history_context=    "",
            emotion_instruction="Be professional and calm.",
            priority=           "Normal",
            language=           "English",
            lessons_block=      "",
        )
        assert len(result) > 100
        assert "Acme Corp" in result
        assert "Customer Service Manager" in result
        assert "Jane Smith" in result

    def test_response_system_render_missing_variable_raises(self):
        spec = get_registry().get("response_system")
        with pytest.raises(ValueError):
            spec.render(role="Agent")  # all other vars missing

    def test_qa_review_render_no_variables(self):
        spec = get_registry().get("qa_review")
        result = spec.render()
        assert "QA reviewer" in result
        assert "needs_revision" in result
        # Escaped braces must have been rendered as literal braces
        assert "{" in result
        assert "}" in result

    def test_triage_system_render_no_variables(self):
        spec = get_registry().get("triage_system")
        result = spec.render()
        assert len(result) > 50

    def test_all_checksums_are_12_char_hex(self):
        for pid in get_registry().all_ids():
            spec = get_registry().get(pid)
            assert len(spec.checksum) == 12, f"{pid} checksum length wrong"
            assert all(c in "0123456789abcdef" for c in spec.checksum)

    def test_get_registry_singleton(self):
        assert get_registry() is get_registry()
