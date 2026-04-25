"""Layer 3 — template parser. Pure; imports `errors` only.

Story 1.2 scope:
- Recognizes `<<include path="..." [name="value"]*>>` and emits `Include`
  AST nodes. Extra attributes (non-`path`) land on `Include.props` as a
  tuple of `(name, value)` pairs sorted alphabetically by name.
- Any other `<<...>>` form raises `UnknownDirectiveError`.
- `{{var}}`, `{{self.*}}`, `{var}` tokenization remains deferred to Story 1.3;
  such tokens pass through inside `Text` nodes.

AST node dataclasses for later stories are defined here so layering is
settled and the import graph for Stories 1.3+ is stable.

Attribute-value quoting has no escape in v1: an embedded `\\"` inside a
matched include token is treated as a malformed directive and raises
`UnknownDirectiveError` with a quoting-hint — see Story 1.2 Task 1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union

from . import errors


@dataclass(frozen=True)
class Text:
    content: str
    line: int
    col: int


@dataclass(frozen=True)
class Include:
    src: str
    # Immutable props — frozen dataclass + tuple-of-pairs so shared defaults
    # cannot be mutated accidentally.
    props: tuple[tuple[str, str], ...] = ()
    line: int = 1
    col: int = 1


@dataclass(frozen=True)
class VarCompile:
    name: str
    line: int
    col: int


@dataclass(frozen=True)
class VarRuntime:
    name: str
    line: int
    col: int


AstNode = Union[Text, Include, VarCompile, VarRuntime]


# `<<include path="<val>" [name="<val>"]*>>` — path values additionally
# exclude `>` so a stray `>>` terminates scanning cleanly (AC 8). Attribute
# values exclude `"` and `\n` only. Leading underscore is valid for both
# path and attribute-name characters so authors can write `_foo="v"`.
_INCLUDE_RE = re.compile(
    r'<<include\s+path="(?P<path>[^"\n>]+)"'
    r'(?P<extras>(?:\s+[a-zA-Z_][a-zA-Z0-9_-]*="[^"\n]*")*)'
    r'\s*>>'
)
_ATTR_RE = re.compile(r'(?P<name>[a-zA-Z_][a-zA-Z0-9_-]*)="(?P<value>[^"\n]*)"')

_QUOTING_HINT = (
    "attribute-value quoting is not escapable in v1 — "
    "split the attribute or remove the embedded quote"
)


def _line_col(source: str, char_offset: int) -> tuple[int, int]:
    """Translate a character offset (e.g. `re.Match.start()` on a `str`) into
    a (1-based line, 1-based col) pair."""
    line = 1 + source.count("\n", 0, char_offset)
    last_newline = source.rfind("\n", 0, char_offset)
    col = char_offset - last_newline  # rfind returns -1 when absent, giving col=1
    return line, col


def _make_unknown_error(
    source: str,
    relative_path: str,
    start: int,
    token: str,
    hint: str | None = None,
) -> errors.UnknownDirectiveError:
    line, col = _line_col(source, start)
    default_hint = (
        f"directive '{token}' on line {line} is not recognized — "
        "did you mean '<<include>>'? "
        "Valid directives: <<include>>, {{var}}, {{self.<toml.path>}}, {var}"
    )
    return errors.UnknownDirectiveError(
        f"unknown directive '{token}'",
        file=relative_path,
        line=line,
        col=col,
        token=token,
        hint=hint or default_hint,
        source=source,
    )


def parse(source: str, relative_path: str) -> list[AstNode]:
    """Tokenize `source` into an AST.

    Happy paths:
    - Source with no `<<` returns `[Text(content=source, line=1, col=1)]`
      (single node — byte-identical passthrough for Story 1.1 fixtures).
    - Source with one or more `<<include>>` tokens returns alternating
      `Text` / `Include` nodes in authoring order; adjacent includes with
      no text between them produce consecutive `Include` nodes and no
      empty `Text` placeholder.

    Errors:
    - Any `<<...>>` token that is not a valid include raises
      `UnknownDirectiveError`. An include-shaped token containing `\\"`
      raises with a quoting-hint.
    """
    nodes: list[AstNode] = []
    pos = 0
    source_len = len(source)

    while pos < source_len:
        next_open = source.find("<<", pos)
        if next_open == -1:
            line, col = _line_col(source, pos)
            nodes.append(Text(content=source[pos:], line=line, col=col))
            break

        if next_open > pos:
            line, col = _line_col(source, pos)
            nodes.append(Text(content=source[pos:next_open], line=line, col=col))

        match = _INCLUDE_RE.match(source, next_open)
        if match is not None:
            matched = match.group(0)
            # Escape sequences aren't interpreted in v1; a literal `\"` inside
            # the matched slice is a silent-corruption risk (value truncated
            # at the first `"`). Reject explicitly so authors get a hint.
            if '\\"' in matched:
                raise _make_unknown_error(
                    source, relative_path, next_open, matched, hint=_QUOTING_HINT
                )
            path_value = match.group("path")
            # Whitespace-only path values are rejected early — authors would
            # otherwise get a confusing MISSING_FRAGMENT with a space as the
            # leaf name rather than a clear parse error.
            if not path_value.strip():
                raise _make_unknown_error(
                    source, relative_path, next_open, matched,
                    hint="path value must be a non-empty, non-whitespace string",
                )
            # Absolute POSIX paths (leading `/`) escape the tier-cascade
            # anchoring — `skill_dir / PurePosixPath("/x")` collapses to the
            # absolute path, so an include of `/etc/passwd` would bypass all
            # containment and be read verbatim by the resolver. Reject at
            # the parser so authors get a clear diagnostic instead of a
            # silent arbitrary-file-read.
            if path_value.startswith("/"):
                raise _make_unknown_error(
                    source, relative_path, next_open, matched,
                    hint=(
                        "absolute include paths are not allowed — use a "
                        "relative path such as 'fragments/<name>.template.md', "
                        "a './<name>' skill-local path, or a "
                        "'<moduleId>/<name>' cross-module path"
                    ),
                )
            # Reject ASCII control characters (`\x00`-`\x1F` and `\x7F`) in
            # path values. The `_INCLUDE_RE` char-class `[^"\n>]+` does not
            # exclude `\x00`, and CPython's filesystem layer raises
            # raw `ValueError("embedded null byte")` outside the
            # `CompilerError` taxonomy when the resolver later probes the
            # tier-5 base candidate. Other C0 controls similarly produce
            # confusing OS-level errors. Reject at parse so authors get a
            # clean `UnknownDirectiveError` with the violating directive
            # carated on the source line.
            for ch in path_value:
                if ord(ch) < 0x20 or ord(ch) == 0x7F:
                    raise _make_unknown_error(
                        source, relative_path, next_open, matched,
                        hint=(
                            "path value contains an ASCII control "
                            "character (0x00-0x1F or 0x7F) — these are "
                            "not valid in include paths and indicate the "
                            "source was authored with a binary editor or "
                            "miscoded encoding"
                        ),
                    )
            extras_str = match.group("extras") or ""
            extras = _ATTR_RE.findall(extras_str)
            # Reject a duplicate `path` key in the extras — the first `path`
            # is consumed by the named group; a second would silently leak
            # into props and shadow the real path in Story 1.3.
            if any(name == "path" for name, _ in extras):
                raise _make_unknown_error(
                    source, relative_path, next_open, matched,
                    hint="duplicate 'path' attribute — each attribute may appear at most once",
                )
            # Reject duplicate attribute names — after sort, a collision
            # would silently keep only the alphabetically-first value.
            names = [name for name, _ in extras]
            if len(names) != len(set(names)):
                raise _make_unknown_error(
                    source, relative_path, next_open, matched,
                    hint="duplicate attribute names are not allowed in <<include>>",
                )
            # Sort by attribute name — deterministic order independent of
            # authoring keystroke order. `findall` returns tuples matching
            # the named groups in definition order: (name, value).
            props = tuple(sorted(extras, key=lambda pair: pair[0]))
            line, col = _line_col(source, next_open)
            nodes.append(Include(src=path_value, props=props, line=line, col=col))
            pos = match.end()
            continue

        # Not a valid include. Recover a reasonable token for the error
        # message: the `<<...>>` outline on this line if present, else the
        # rest of the line (handles newline-inside-attr-value cases).
        newline = source.find("\n", next_open)
        close = source.find(">>", next_open)
        if close != -1 and (newline == -1 or close < newline):
            token = source[next_open:close + 2]
        else:
            end = newline if newline != -1 else source_len
            token = source[next_open:end]

        hint: str | None = None
        if token.startswith("<<include") and '\\"' in token:
            hint = _QUOTING_HINT
        raise _make_unknown_error(source, relative_path, next_open, token, hint=hint)

    if not nodes:
        nodes.append(Text(content="", line=1, col=1))
    return nodes
