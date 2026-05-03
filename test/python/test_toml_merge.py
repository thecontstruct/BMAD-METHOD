"""Unit tests for bmad_compile.toml_merge — structural merge + file loading."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.scripts.bmad_compile import io
from src.scripts.bmad_compile.toml_merge import load_toml_file, merge_layers


class TestMergeLayers(unittest.TestCase):
    def test_merge_empty_layers_returns_empty(self) -> None:
        self.assertEqual(merge_layers(), {})
        self.assertEqual(merge_layers({}), {})
        self.assertEqual(merge_layers({}, {}), {})

    def test_scalar_override_wins(self) -> None:
        result = merge_layers({"a": 1}, {"a": 2})
        self.assertEqual(result, {"a": 2})

    def test_missing_key_in_override_keeps_base(self) -> None:
        result = merge_layers({"a": 1, "b": 2}, {"a": 3})
        self.assertEqual(result, {"a": 3, "b": 2})

    def test_table_deep_merge(self) -> None:
        base = {"agent": {"name": "Base", "role": "assistant"}}
        override = {"agent": {"name": "Override"}}
        result = merge_layers(base, override)
        self.assertEqual(result["agent"]["name"], "Override")
        self.assertEqual(result["agent"]["role"], "assistant")  # preserved

    def test_three_layers_cumulative(self) -> None:
        base = {"a": 1, "b": 2, "c": 3}
        team = {"a": 10, "b": 20}
        user = {"a": 100}
        result = merge_layers(base, team, user)
        self.assertEqual(result["a"], 100)  # user wins
        self.assertEqual(result["b"], 20)   # team wins over base
        self.assertEqual(result["c"], 3)    # base preserved

    def test_array_of_tables_replace_by_code(self) -> None:
        base = [{"code": "x", "name": "foo", "bio": "hello"}, {"code": "y", "name": "qux"}]
        override = [{"code": "x", "name": "bar"}, {"code": "z", "name": "new"}]
        result = merge_layers({"items": base}, {"items": override})["items"]

        # code=x: full replacement — bio MUST be dropped (upstream _merge_by_key)
        self.assertEqual(result[0]["code"], "x")
        self.assertEqual(result[0]["name"], "bar")
        self.assertNotIn("bio", result[0])  # critical: no deep-merge, full replace

        # code=y: unmatched base item preserved in original position
        self.assertEqual(result[1]["code"], "y")
        self.assertEqual(result[1]["name"], "qux")

        # code=z: new override item appended after base items
        self.assertEqual(result[2]["code"], "z")
        self.assertEqual(result[2]["name"], "new")

    def test_array_of_tables_replace_by_id(self) -> None:
        base = [{"id": "a", "label": "Alpha"}, {"id": "b", "label": "Beta"}]
        override = [{"id": "a", "label": "New Alpha"}, {"id": "c", "label": "Gamma"}]
        result = merge_layers({"items": base}, {"items": override})["items"]
        self.assertEqual(result[0], {"id": "a", "label": "New Alpha"})
        self.assertEqual(result[1], {"id": "b", "label": "Beta"})
        self.assertEqual(result[2], {"id": "c", "label": "Gamma"})

    def test_plain_array_appends(self) -> None:
        result = merge_layers({"tags": ["a", "b"]}, {"tags": ["c"]})
        self.assertEqual(result["tags"], ["a", "b", "c"])

    def test_mixed_keyed_condition_not_met_falls_back_to_append(self) -> None:
        # Not every item has the same key field → plain array append.
        base = [{"code": "x"}, {"name": "no-code"}]
        override = [{"code": "y"}]
        result = merge_layers({"items": base}, {"items": override})["items"]
        # Condition not met (mixed) → append
        self.assertEqual(len(result), 3)
        self.assertEqual(result[2]["code"], "y")

    def test_merge_layers_output_is_deterministic(self) -> None:
        # Two calls with dicts in different key-insertion orders must produce
        # identical output (NFR-R2 — no order-dependent non-determinism).
        r1 = merge_layers({"b": 2, "a": 1}, {"c": 3})
        r2 = merge_layers({"a": 1, "b": 2}, {"c": 3})
        self.assertEqual(r1, r2)


class TestAoTMergeEdgeCases(unittest.TestCase):
    """Edge cases for arrays-of-tables (AoT) merge — Story 3.2 AC 3."""

    def test_aot_id_keyed_three_layer_full_replacement(self) -> None:
        # Base: two id-keyed items, both with `enabled = true`.
        base = {"steps": [
            {"id": "plan", "label": "Plan", "enabled": True},
            {"id": "review", "label": "Review", "enabled": True},
        ]}
        # Team layer: overrides "plan" — `enabled` NOT present, must be DROPPED.
        team = {"steps": [
            {"id": "plan", "label": "Plan (Team)"},
        ]}
        # User layer: overrides "review" with explicit `enabled = false`.
        user = {"steps": [
            {"id": "review", "label": "Review (User)", "enabled": False},
        ]}

        result = merge_layers(base, team, user)["steps"]
        self.assertEqual(len(result), 2)

        plan = next(s for s in result if s["id"] == "plan")
        self.assertEqual(plan["label"], "Plan (Team)")
        self.assertNotIn("enabled", plan)  # full replacement — base field dropped

        review = next(s for s in result if s["id"] == "review")
        self.assertEqual(review["label"], "Review (User)")
        self.assertIs(review["enabled"], False)

    def test_aot_code_keyed_full_replacement(self) -> None:
        base = {"agents": [
            {"code": "pm", "name": "PM", "bio": "manages product"},
            {"code": "dev", "name": "Dev"},
        ]}
        override = {"agents": [
            {"code": "pm", "name": "PM Override"},  # bio NOT present → dropped
        ]}
        result = merge_layers(base, override)["agents"]
        self.assertEqual(len(result), 2)
        pm = next(a for a in result if a["code"] == "pm")
        self.assertEqual(pm["name"], "PM Override")
        self.assertNotIn("bio", pm)
        dev = next(a for a in result if a["code"] == "dev")
        self.assertEqual(dev["name"], "Dev")

    def test_aot_three_layer_distinct_keys_all_survive(self) -> None:
        # Each layer contributes a distinct id-keyed item — no key collisions.
        # Keyed-merge semantics still apply (every item has `id`), so all 3
        # survive in deterministic order.
        base = {"steps": [{"id": "a", "label": "A"}]}
        team = {"steps": [{"id": "b", "label": "B"}]}
        user = {"steps": [{"id": "c", "label": "C"}]}
        result = merge_layers(base, team, user)["steps"]
        self.assertEqual(len(result), 3)
        self.assertEqual([s["id"] for s in result], ["a", "b", "c"])

    def test_aot_mixed_key_fallback_plain_append(self) -> None:
        # Mixed: one item has `id`, one has `code`, one has neither.
        # _keyed_field returns None → plain append.
        base = {"items": [
            {"id": "x", "label": "X"},
            {"name": "no-key"},
        ]}
        override = {"items": [
            {"code": "y", "label": "Y"},
        ]}
        result = merge_layers(base, override)["items"]
        # Plain append: 2 + 1 = 3 items, no merging by id/code.
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], {"id": "x", "label": "X"})
        self.assertEqual(result[1], {"name": "no-key"})
        self.assertEqual(result[2], {"code": "y", "label": "Y"})


class TestLoadTomlFile(unittest.TestCase):
    def test_load_toml_file_returns_empty_for_missing(self) -> None:
        result = load_toml_file("/nonexistent/path/to/file.toml")
        self.assertEqual(result, {})

    def test_load_toml_file_parses_real_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "test.toml")
            io.write_text(path, '[agent]\nname = "PM Agent"\n')
            result = load_toml_file(path)
            self.assertEqual(result, {"agent": {"name": "PM Agent"}})

    def test_load_toml_file_returns_empty_dict_for_empty_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "empty.toml")
            io.write_text(path, "")
            result = load_toml_file(path)
            self.assertEqual(result, {})

    def test_parse_error_includes_line_number(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "bad.toml")
            # Two valid lines then an invalid value at line 3
            io.write_text(path, 'a = 1\nb = 2\nbad_value = [no close\n')
            from src.scripts.bmad_compile.errors import UnknownDirectiveError
            with self.assertRaises(UnknownDirectiveError) as cm:
                load_toml_file(path)
            self.assertEqual(cm.exception.line, 3)


if __name__ == "__main__":
    unittest.main()
