"""Minimal JSON Schema draft-07 validator -- stdlib only.

Supports: type, required, const, properties, items, additionalProperties.
Union-type form ["string", "null"] supported for type keyword.
$ref is not supported -- raises NotImplementedError.
Unknown keywords are silently ignored (draft-07 default behavior).
Empty schema {} validates any value.
Absent additionalProperties defaults to permissive (draft-07 default true).

Stories 6.2-6.6 use harness.mock_compiler; Story 6.7 bypasses it.
This module has no third-party imports.
"""
from __future__ import annotations

from typing import Any


class ValidationError(Exception):
    """Raised when a document fails schema validation.
    Message includes the JSON-pointer path to the offending field."""


def validate(instance: object, schema: dict[str, Any], _path: str = "") -> None:
    """Validate instance against schema. Raise ValidationError on failure.
    Return None on success."""
    if not isinstance(schema, dict):
        return

    if "$ref" in schema:
        raise NotImplementedError(
            f"$ref is not supported by _jsonschema_minimal; "
            f"path: {_path or '(root)'}. "
            "If a future schema introduces $ref, implement a resolver."
        )

    if "type" in schema:
        _check_type(instance, schema["type"], _path)

    if "const" in schema:
        if instance != schema["const"]:
            raise ValidationError(
                f"{_path or '(root)'}: expected const {schema['const']!r}, "
                f"got {instance!r}"
            )

    if "required" in schema and isinstance(instance, dict):
        for key in schema["required"]:
            if key not in instance:
                raise ValidationError(
                    f"{_path or '(root)'}: missing required property {key!r}"
                )

    if "properties" in schema and isinstance(instance, dict):
        for key, sub_schema in schema["properties"].items():
            if key in instance:
                child_path = f"{_path}/{key}" if _path else f"/{key}"
                validate(instance[key], sub_schema, _path=child_path)

    if "additionalProperties" in schema and isinstance(instance, dict):
        ap = schema["additionalProperties"]
        known_props = set(schema.get("properties", {}).keys())
        for key, value in instance.items():
            if key not in known_props:
                if isinstance(ap, dict):
                    child_path = f"{_path}/{key}" if _path else f"/{key}"
                    validate(value, ap, _path=child_path)
                elif ap is False:
                    raise ValidationError(
                        f"{_path or '(root)'}: additional property {key!r} not allowed"
                    )

    if "items" in schema and isinstance(instance, list):
        item_schema = schema["items"]
        for i, item in enumerate(instance):
            item_path = f"{_path}[{i}]"
            validate(item, item_schema, _path=item_path)


def _check_type(instance: object, type_spec: object, path: str) -> None:
    """Check instance against a type specification (string or list of strings)."""
    if isinstance(type_spec, list):
        for t in type_spec:
            if _matches_type(instance, t):
                return
        raise ValidationError(
            f"{path or '(root)'}: expected type {type_spec!r}, "
            f"got {type(instance).__name__}"
        )
    elif isinstance(type_spec, str):
        if not _matches_type(instance, type_spec):
            raise ValidationError(
                f"{path or '(root)'}: expected type {type_spec!r}, "
                f"got {type(instance).__name__}"
            )


def _matches_type(instance: object, type_name: str) -> bool:
    """Return True if instance matches the JSON Schema type name."""
    if type_name == "object":
        return isinstance(instance, dict)
    if type_name == "array":
        return isinstance(instance, list)
    if type_name == "string":
        return isinstance(instance, str)
    if type_name == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if type_name == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if type_name == "boolean":
        return isinstance(instance, bool)
    if type_name == "null":
        return instance is None
    return False
