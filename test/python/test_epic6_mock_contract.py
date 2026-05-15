"""Story 6.1: Schema-fixture contract tests, MockCompiler harness unit tests,
fixture determinism tests, and vendored validator unit tests for Epic 6.

Covers AC-1, AC-2, AC-3, AC-5, AC-6, and Task 5 obligations.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Process-global sys.path mutation — acceptable for current single-process unittest runner.
# The idempotency guards (`if ... not in sys.path`) prevent double-insertion on re-import
# but do not undo the mutation on teardown. If the project ever adopts parallel/isolated
# test execution (e.g. pytest-xdist), convert to importlib-based imports or a conftest.py
# sys.path fixture.  # noqa: sys.path-global
# Add test/ directory to path so `from harness.X import ...` resolves.
_TEST_DIR = Path(__file__).resolve().parent.parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

# (same isolation constraint as above)
# Add src/scripts to path for schema directory constant (mirrors test_upgrade_dry_run.py).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from harness._jsonschema_minimal import ValidationError, validate
from harness.mock_compiler import MockCompiler

_SCHEMAS_DIR = _SCRIPTS_DIR / "bmad_compile" / "schemas"
_FIXTURES_ROOT = _TEST_DIR / "fixtures" / "customize-mocks"

_EXPLAIN_SCHEMA_PATH = _SCHEMAS_DIR / "explain-v1.json"
_DRY_RUN_SCHEMA_PATH = _SCHEMAS_DIR / "dry-run-v1.json"


def _load_schema(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _infer_schema(filename: str) -> dict:
    """Infer schema from fixture filename prefix."""
    if filename.startswith("explain-"):
        return _load_schema(_EXPLAIN_SCHEMA_PATH)
    if filename.startswith("dry-run-"):
        return _load_schema(_DRY_RUN_SCHEMA_PATH)
    raise ValueError(f"Unrecognized fixture prefix: {filename!r}")


# ---------------------------------------------------------------------------
# AC-1, AC-3: Schema-fixture contract
# ---------------------------------------------------------------------------

class TestSchemaFixtureContract(unittest.TestCase):
    """Contract tests: every fixture validates against its frozen v1 schema."""

    def test_fixture_count_is_exactly_15(self) -> None:
        """Exactly 15 .json fixtures exist under customize-mocks/ (AC-1 invariant)."""
        fixtures = sorted(_FIXTURES_ROOT.glob("*.json"))
        self.assertEqual(
            len(fixtures),
            15,
            f"Expected exactly 15 fixtures, found {len(fixtures)}: "
            + ", ".join(f.name for f in fixtures),
        )  # Story 6.7c added dry-run-bmad-customize-self.json (14 → 15).

    def test_all_fixtures_declare_schema_version_1(self) -> None:
        """Every fixture has schema_version == 1 (integer)."""
        failures: list[str] = []
        for fixture_path in sorted(_FIXTURES_ROOT.glob("*.json")):
            try:
                data = json.loads(fixture_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                failures.append(f"{fixture_path.name}: JSON parse error — {exc}")
                continue
            sv = data.get("schema_version")
            if not isinstance(sv, int) or isinstance(sv, bool) or sv != 1:
                failures.append(
                    f"{fixture_path.name}: schema_version is {sv!r}, expected integer 1"
                )
        if failures:
            self.fail(
                f"{len(failures)} fixture(s) failed schema_version check:\n"
                + "\n".join(failures)
            )

    def test_all_fixtures_validate_against_current_schema(self) -> None:
        """Every fixture validates against its inferred v1 schema (AC-3 gate)."""
        failures: list[str] = []
        for fixture_path in sorted(_FIXTURES_ROOT.glob("*.json")):
            try:
                data = json.loads(fixture_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                failures.append(f"{fixture_path.name}: JSON parse error — {exc}")
                continue
            try:
                schema = _infer_schema(fixture_path.name)
            except ValueError as exc:
                self.fail(str(exc))
            schema_name = (
                "explain-v1.json" if fixture_path.name.startswith("explain-")
                else "dry-run-v1.json"
            )
            try:
                validate(data, schema)
            except ValidationError as exc:
                failures.append(
                    f"{fixture_path.name} (schema {schema_name}): {exc}"
                )
            except Exception as exc:
                self.fail(
                    f"Unexpected error validating {fixture_path.name} against "
                    f"{schema_name}: {exc!r}"
                )
        if failures:
            self.fail(
                f"{len(failures)} fixture(s) failed schema validation:\n"
                + "\n".join(failures)
            )

    def test_synthetic_additive_field_validates(self) -> None:
        """Additive-tolerance: fixture with an extra optional field still validates (AC-5)."""
        base = json.loads(
            (_FIXTURES_ROOT / "dry-run-no-drift.json").read_text(encoding="utf-8")
        )
        # Inject a synthetic new optional field (simulates a future additive schema amendment).
        base["future_optional_field"] = "synthetic"
        schema = _load_schema(_DRY_RUN_SCHEMA_PATH)
        # Must not raise — additive fields are tolerated by schema (no additionalProperties
        # restriction at root).
        try:
            validate(base, schema)
        except ValidationError as exc:
            self.fail(
                f"Additive-tolerance broken: synthetic field rejected by validator — {exc}"
            )


# ---------------------------------------------------------------------------
# AC-2: MockCompiler harness unit tests
# ---------------------------------------------------------------------------

class TestMockCompilerHarness(unittest.TestCase):
    """Unit tests for MockCompiler per AC-2 enumerated coverage."""

    def _make_mock(self) -> MockCompiler:
        return MockCompiler(fixtures_root=_FIXTURES_ROOT)

    def test_register_then_intercept_returns_fixture(self) -> None:
        """Happy path: register + intercept returns fixture JSON string."""
        mock = self._make_mock()
        mock.register("compile --explain --json", "explain-pristine.json")
        result = mock.intercept("compile --explain --json --skill mock/skill-a")
        data = json.loads(result)
        self.assertEqual(data["schema_version"], 1)
        self.assertIn("fragments", data)

    def test_intercept_unregistered_raises_keyerror(self) -> None:
        """intercept() raises KeyError with directed message for unregistered pattern."""
        mock = self._make_mock()
        mock.register("compile --explain --json", "explain-pristine.json")
        with self.assertRaises(KeyError) as ctx:
            mock.intercept("upgrade --dry-run --json")
        self.assertIn("no registered pattern", str(ctx.exception))

    def test_multiple_patterns_one_fixture(self) -> None:
        """Multiple patterns can map to the same fixture."""
        mock = self._make_mock()
        mock.register("compile --explain --json", "explain-pristine.json")
        mock.register("explain --json", "explain-pristine.json")
        r1 = mock.intercept("compile --explain --json")
        r2 = mock.intercept("explain --json --skill x")
        self.assertEqual(r1, r2)

    def test_last_registration_wins_on_collision(self) -> None:
        """Last register() call wins when same pattern is registered twice."""
        mock = self._make_mock()
        mock.register("compile --explain --json", "explain-pristine.json")
        mock.register("compile --explain --json", "explain-with-toml-override.json")
        result = json.loads(mock.intercept("compile --explain --json"))
        # explain-with-toml-override has a 'user' layer; explain-pristine does not.
        toml_fields = result.get("toml_fields", [])
        has_user_layer = any("user" in tf.get("layers", {}) for tf in toml_fields)
        self.assertTrue(has_user_layer, "Expected explain-with-toml-override fixture (has user layer)")

    def test_calls_records_each_intercept(self) -> None:
        """Each intercept call is recorded in mock.calls with correct pattern + fixture."""
        mock = self._make_mock()
        mock.register("compile --explain --json", "explain-pristine.json")
        mock.register("upgrade --dry-run --json", "dry-run-no-drift.json")
        mock.intercept("compile --explain --json")
        mock.intercept("upgrade --dry-run --json")
        calls = mock.calls
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["pattern"], "compile --explain --json")
        self.assertEqual(calls[0]["fixture"], "explain-pristine.json")
        self.assertIn("timestamp_ns", calls[0])
        self.assertIsInstance(calls[0]["timestamp_ns"], int)
        self.assertEqual(calls[1]["pattern"], "upgrade --dry-run --json")
        self.assertEqual(calls[1]["fixture"], "dry-run-no-drift.json")

    def test_reset_clears_calls_preserves_registrations(self) -> None:
        """reset() clears calls but keeps registrations intact."""
        mock = self._make_mock()
        mock.register("compile --explain --json", "explain-pristine.json")
        mock.intercept("compile --explain --json")
        self.assertEqual(len(mock.calls), 1)
        mock.reset()
        self.assertEqual(len(mock.calls), 0)
        # Registration should still work after reset.
        mock.intercept("compile --explain --json")
        self.assertEqual(len(mock.calls), 1)

    def test_fixture_reread_on_each_intercept(self) -> None:
        """Fixture content is re-read from disk on each call (mutate-test pattern)."""
        mock = self._make_mock()
        mock.register("compile --explain --json", "dry-run-no-drift.json")
        content1 = mock.intercept("compile --explain --json")

        fixture_path = _FIXTURES_ROOT / "dry-run-no-drift.json"
        original = fixture_path.read_bytes()
        fixture_path.write_bytes(b'{"mutated":true}\n')
        try:
            content2 = mock.intercept("compile --explain --json")
        finally:
            fixture_path.write_bytes(original)

        self.assertNotEqual(content1, content2)
        self.assertEqual(json.loads(content2), {"mutated": True})

    def test_intercept_registered_but_missing_file_raises_filenotfounderror(self) -> None:
        """Registered pattern with nonexistent fixture raises FileNotFoundError."""
        mock = self._make_mock()
        mock.register("compile --explain --json", "nonexistent-fixture.json")
        with self.assertRaises(FileNotFoundError):
            mock.intercept("compile --explain --json")

    def test_empty_calls_after_invocation_fails_loudly(self) -> None:
        """Guard: empty calls list after expected invocations must fail loudly.

        Covers two scenarios Stories 6.2–6.6 scaffolding must guard against:

        (a) Zero-invocation: skill never called subprocess at all — calls is empty.
        (b) Mismatched-pattern: skill called subprocess but for a different operation
            than expected — the filtered call list for the expected pattern is empty.
        """
        # --- Scenario (a): zero-invocation ---
        mock = self._make_mock()
        mock.register("compile --explain --json", "explain-pristine.json")
        # Simulate: skill was invoked but didn't route through MockCompiler at all.
        with self.assertRaises(AssertionError) as ctx:
            if not mock.calls:
                self.fail(
                    "MockCompiler.calls is empty after skill invocation — "
                    "orchestration wiring appears to be missing; "
                    "ensure the skill's compiler-primitive calls route through "
                    "MockCompiler.intercept()"
                )
        self.assertIn("MockCompiler.calls is empty", str(ctx.exception))

        # --- Scenario (b): mismatched-pattern ---
        # Skill called subprocess (explain), but orchestration expected dry-run.
        mock2 = self._make_mock()
        mock2.register("compile --explain --json", "explain-pristine.json")
        mock2.intercept("compile --explain --json")  # explain was called, not dry-run
        expected_dry_run_calls = [
            c for c in mock2.calls if "upgrade --dry-run" in c["pattern"]
        ]
        with self.assertRaises(AssertionError) as ctx2:
            if not expected_dry_run_calls:
                self.fail(
                    "MockCompiler.calls contains no 'upgrade --dry-run' intercepts "
                    "after skill invocation — orchestration called 'compile --explain' "
                    "instead of 'upgrade --dry-run'"
                )
        self.assertIn("no 'upgrade --dry-run' intercepts", str(ctx2.exception))

    def test_calls_returns_copy_not_internal_list(self) -> None:
        """mock.calls returns a copy — external mutation does not affect internal state."""
        mock = self._make_mock()
        mock.register("compile --explain --json", "explain-pristine.json")
        mock.intercept("compile --explain --json")
        external = mock.calls
        external.clear()
        self.assertEqual(len(mock.calls), 1)


# ---------------------------------------------------------------------------
# AC-6: Fixture determinism
# ---------------------------------------------------------------------------

class TestFixtureDeterminism(unittest.TestCase):
    """Fixtures are serialized deterministically (sorted keys, 2-space indent, LF + trailing NL)."""

    def test_fixtures_are_deterministically_serialized(self) -> None:
        """Round-trip: reload fixture, re-serialize, assert byte identity."""
        failures: list[str] = []
        for fixture_path in sorted(_FIXTURES_ROOT.glob("*.json")):
            raw = fixture_path.read_text(encoding="utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                failures.append(f"{fixture_path.name}: JSON parse error — {exc}")
                continue
            reserialized = json.dumps(data, sort_keys=True, indent=2) + "\n"
            if raw != reserialized:
                failures.append(
                    f"{fixture_path.name}: not deterministically serialized "
                    f"(byte mismatch: on-disk {len(raw)} bytes vs re-serialized {len(reserialized)} bytes)"
                )
        if failures:
            self.fail(
                f"{len(failures)} fixture(s) failed determinism check:\n"
                + "\n".join(failures)
            )

    def test_no_timestamp_or_random_fields(self) -> None:
        """No fixture contains timestamp or randomly-varying fields."""
        forbidden_keys = {
            "generated_at", "compile_time", "timestamp", "created_at",
            "updated_at", "random_id", "run_id",
        }
        failures: list[str] = []
        for fixture_path in sorted(_FIXTURES_ROOT.glob("*.json")):
            try:
                data = json.loads(fixture_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            found = _find_forbidden_keys(data, forbidden_keys)
            if found:
                failures.append(f"{fixture_path.name}: forbidden keys {found!r}")
        if failures:
            self.fail(
                f"{len(failures)} fixture(s) contain timestamp/random fields:\n"
                + "\n".join(failures)
            )


def _find_forbidden_keys(obj: object, forbidden: set[str]) -> list[str]:
    """Recursively collect any forbidden keys present in a JSON structure."""
    found: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in forbidden:
                found.append(k)
            found.extend(_find_forbidden_keys(v, forbidden))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_forbidden_keys(item, forbidden))
    return found


# ---------------------------------------------------------------------------
# Task 5: Vendored validator unit tests (TestJsonSchemaMinimal)
# ---------------------------------------------------------------------------

class TestJsonSchemaMinimal(unittest.TestCase):
    """Unit tests for _jsonschema_minimal.validate() — 1 happy + 1 failure per keyword."""

    # ---- type ----

    def test_type_string_passes(self) -> None:
        validate("hello", {"type": "string"})

    def test_type_string_fails_on_integer(self) -> None:
        with self.assertRaises(ValidationError):
            validate(42, {"type": "string"})

    def test_type_integer_passes(self) -> None:
        validate(1, {"type": "integer"})

    def test_type_integer_rejects_bool(self) -> None:
        with self.assertRaises(ValidationError):
            validate(True, {"type": "integer"})

    def test_type_object_passes(self) -> None:
        validate({}, {"type": "object"})

    def test_type_object_fails_on_list(self) -> None:
        with self.assertRaises(ValidationError):
            validate([], {"type": "object"})

    def test_type_array_passes(self) -> None:
        validate([], {"type": "array"})

    def test_type_array_fails_on_dict(self) -> None:
        with self.assertRaises(ValidationError):
            validate({}, {"type": "array"})

    def test_type_null_passes(self) -> None:
        validate(None, {"type": "null"})

    def test_type_null_fails_on_string(self) -> None:
        with self.assertRaises(ValidationError):
            validate("x", {"type": "null"})

    # ---- required ----

    def test_required_present_passes(self) -> None:
        validate({"a": 1, "b": 2}, {"type": "object", "required": ["a", "b"]})

    def test_required_missing_fails(self) -> None:
        with self.assertRaises(ValidationError) as ctx:
            validate({"a": 1}, {"type": "object", "required": ["a", "b"]})
        self.assertIn("b", str(ctx.exception))

    # ---- const ----

    def test_const_matches_passes(self) -> None:
        validate(1, {"type": "integer", "const": 1})

    def test_const_mismatch_fails(self) -> None:
        with self.assertRaises(ValidationError):
            validate(2, {"type": "integer", "const": 1})

    def test_const_string_matches(self) -> None:
        validate("compile-time", {"type": "string", "const": "compile-time"})

    def test_const_string_mismatch_fails(self) -> None:
        with self.assertRaises(ValidationError):
            validate("runtime", {"type": "string", "const": "compile-time"})

    # ---- properties ----

    def test_properties_valid_passes(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
        }
        validate({"name": "foo", "count": 3}, schema)

    def test_properties_invalid_fails(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
        with self.assertRaises(ValidationError):
            validate({"name": 123}, schema)

    # ---- items ----

    def test_items_valid_passes(self) -> None:
        validate(["a", "b", "c"], {"type": "array", "items": {"type": "string"}})

    def test_items_invalid_fails(self) -> None:
        with self.assertRaises(ValidationError):
            validate(["a", 1, "c"], {"type": "array", "items": {"type": "string"}})

    # ---- additionalProperties ----

    def test_additional_properties_schema_passes(self) -> None:
        schema = {
            "type": "object",
            "properties": {"known": {"type": "string"}},
            "additionalProperties": {"type": "integer"},
        }
        validate({"known": "x", "extra": 42}, schema)

    def test_additional_properties_schema_fails(self) -> None:
        schema = {
            "type": "object",
            "properties": {"known": {"type": "string"}},
            "additionalProperties": {"type": "integer"},
        }
        with self.assertRaises(ValidationError):
            validate({"known": "x", "extra": "not-an-integer"}, schema)

    def test_additional_properties_false_rejects_extras(self) -> None:
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "additionalProperties": False,
        }
        with self.assertRaises(ValidationError):
            validate({"a": "ok", "b": "extra"}, schema)

    # ---- $ref raises NotImplementedError ----

    def test_ref_raises_not_implemented(self) -> None:
        with self.assertRaises(NotImplementedError) as ctx:
            validate({"foo": 1}, {"$ref": "#/definitions/Foo"})
        self.assertIn("$ref", str(ctx.exception))

    # ---- union type ["string", "null"] ----

    def test_union_type_string_passes(self) -> None:
        validate("hello", {"type": ["string", "null"]})

    def test_union_type_null_passes(self) -> None:
        validate(None, {"type": ["string", "null"]})

    def test_union_type_integer_fails(self) -> None:
        with self.assertRaises(ValidationError):
            validate(42, {"type": ["string", "null"]})

    # ---- unknown keywords are ignored ----

    def test_unknown_keywords_are_ignored(self) -> None:
        """Metadata keywords ($schema, $id, title, description) are silently ignored."""
        schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "$id": "some-id",
            "title": "Test Schema",
            "description": "Should be ignored",
            "type": "object",
            "required": ["x"],
            "properties": {"x": {"type": "string"}},
        }
        validate({"x": "hello"}, schema)

    # ---- empty schema accepts any value ----

    def test_empty_schema_accepts_any_value(self) -> None:
        """Empty schema {} must accept any value (load-bearing for explain-v1.json)."""
        for value in [None, "string", 42, True, [], {}, {"nested": "obj"}]:
            validate(value, {})

    # ---- absent additionalProperties is permissive ----

    def test_absent_additional_properties_is_permissive(self) -> None:
        """No additionalProperties declaration → extra properties are allowed."""
        schema = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
        }
        # Extra keys must not raise.
        validate({"x": "hi", "extra": 42, "another": None}, schema)

    # ---- nested validation path in error messages ----

    def test_error_message_includes_path(self) -> None:
        """ValidationError message includes the JSON-pointer path."""
        schema = {
            "type": "object",
            "properties": {"inner": {"type": "string"}},
        }
        with self.assertRaises(ValidationError) as ctx:
            validate({"inner": 99}, schema)
        self.assertIn("inner", str(ctx.exception))

    # ---- real schema smoke test: explain-v1 ----

    def test_explain_v1_schema_validates_pristine_fixture(self) -> None:
        """End-to-end: explain-pristine.json validates against explain-v1.json."""
        schema = _load_schema(_EXPLAIN_SCHEMA_PATH)
        data = json.loads(
            (_FIXTURES_ROOT / "explain-pristine.json").read_text(encoding="utf-8")
        )
        validate(data, schema)

    # ---- real schema smoke test: dry-run-v1 ----

    def test_dry_run_v1_schema_validates_no_drift_fixture(self) -> None:
        """End-to-end: dry-run-no-drift.json validates against dry-run-v1.json."""
        schema = _load_schema(_DRY_RUN_SCHEMA_PATH)
        data = json.loads(
            (_FIXTURES_ROOT / "dry-run-no-drift.json").read_text(encoding="utf-8")
        )
        validate(data, schema)


# ---------------------------------------------------------------------------
# Bonus: schema well-formedness (OQ-4 resolution — lightweight, ~10 lines)
# ---------------------------------------------------------------------------

class TestSchemasWellFormed(unittest.TestCase):
    """OQ-4: schemas are well-formed JSON with expected structure."""

    def _check_schema(self, path: Path) -> None:
        self.assertTrue(path.exists(), f"Schema not found: {path}")
        schema = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(schema, dict, f"Schema must be a JSON object: {path.name}")
        self.assertIn("$schema", schema)
        self.assertIn("type", schema)
        self.assertIn("properties", schema)
        self.assertIn("required", schema)
        sv_schema = schema["properties"]["schema_version"]
        self.assertEqual(sv_schema.get("type"), "integer")
        self.assertEqual(sv_schema.get("const"), 1)

    def test_explain_v1_is_well_formed(self) -> None:
        self._check_schema(_EXPLAIN_SCHEMA_PATH)

    def test_dry_run_v1_is_well_formed(self) -> None:
        self._check_schema(_DRY_RUN_SCHEMA_PATH)


if __name__ == "__main__":
    unittest.main()
