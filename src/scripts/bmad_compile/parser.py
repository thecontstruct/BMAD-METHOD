"""Layer 3 — template parser. Pure; imports `errors` only.

Story 1.2 scope:
- Recognizes `<<include path="..." [name="value"]*>>` and emits `Include`
  AST nodes. Extra attributes (non-`path`) land on `Include.props` as a
  tuple of `(name, value)` pairs sorted alphabetically by name.
- Any other `<<...>>` form raises `UnknownDirectiveError`.

Story 1.3 scope:
- `{{var_name}}` and `{{self.dotted.path}}` tokenized as `VarCompile`.
- `{var_name}` tokenized as `VarRuntime`.
- Malformed `{{...}}` (bad name, empty, trailing dot, unterminated) raises
  `UnknownDirectiveError` with a four-construct hint.
- Single `{` that doesn't form a valid `{name}` passes through as `Text`.

Scan order: `{{` > `<<` > `{` at tie; triple-brace `{{{foo}}}` handled by
the `{{` branch emitting the leading `{` as Text and advancing by 1.

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
    raw_token: str = ""


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

# Accepts "foo_bar" or "self.agent.name" but NOT "self." or "self..foo"
# Rationale: `(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*` means zero or more `.segment`
# groups; each segment must start with `[a-zA-Z_]`, which rejects trailing
# dots and consecutive dots.
_VAR_COMPILE_RE = re.compile(
    r'\{\{(?P<name>[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\}\}'
)
_VAR_RUNTIME_RE = re.compile(r'\{(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)\}')

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


def _var_compile_hint(line: int) -> str:
    """Hint for malformed or unterminated `{{...}}` tokens."""
    return (
        f"directive '{{{{...}}}}' on line {line} is not recognized — "
        "valid constructs are:\n"
        '  <<include path="...">>  (fragment inclusion)\n'
        "  {{var_name}}            (compile-time variable, resolved before install)\n"
        "  {{self.toml.path}}      (compile-time TOML variable, e.g. {{self.agent.name}})\n"
        "  {var_name}              (runtime placeholder, passed through unchanged)"
    )


def parse(source: str, relative_path: str) -> list[AstNode]:
    """Tokenize `source` into an AST.

    Happy paths:
    - Source with no special tokens returns `[Text(content=source, line=1, col=1)]`.
    - Source with `<<include>>` tokens returns alternating `Text` / `Include` nodes.
    - `{{var_name}}` → `VarCompile`; `{var_name}` → `VarRuntime`.
    - Single `{` not forming a valid `{name}` pattern passes through as `Text`.
    - `{{{foo}}}` → `[Text("{"), VarCompile("foo"), Text("}")]`.

    Scan order at ties (same position): `{{` beats `<<` beats `{`.

    Errors:
    - Any `<<...>>` that is not a valid include raises `UnknownDirectiveError`.
    - `{{...}}` where the name is malformed (leading digit, empty, trailing dot)
      or unterminated (no `}}` before next `<<` or EOF) raises
      `UnknownDirectiveError` with a four-construct hint.
    """
    nodes: list[AstNode] = []
    pos = 0
    source_len = len(source)

    while pos < source_len:
        # Locate the next occurrence of each special opener.
        next_double = source.find("{{", pos)
        next_angle = source.find("<<", pos)
        next_single = source.find("{", pos)

        # Pick the earliest position; among ties {{ > << > {.
        best_pos = source_len  # sentinel — no more special tokens
        best_type: str | None = None
        for typ, idx in (("{{", next_double), ("<<", next_angle), ("{", next_single)):
            if idx == -1:
                continue
            if idx < best_pos:
                best_pos = idx
                best_type = typ
            elif idx == best_pos and typ == "{{":
                best_type = typ  # {{ beats << or { at the same position

        if best_type is None:
            # No more special tokens — rest of source is plain text.
            line, col = _line_col(source, pos)
            nodes.append(Text(content=source[pos:], line=line, col=col))
            break

        # Emit any plain text that precedes the token.
        if best_pos > pos:
            line, col = _line_col(source, pos)
            nodes.append(Text(content=source[pos:best_pos], line=line, col=col))

        pos = best_pos  # advance to token start

        if best_type == "{{":
            # Triple-brace guard: {{{foo}}} — the very first `{` is not part
            # of the `{{` variable token; emit it as Text and restart the scan
            # one character in.  Without this guard, `_VAR_COMPILE_RE` would
            # fail at pos 0 of `{{{foo}}}` and incorrectly raise an error.
            if source[pos + 2:pos + 3] == "{":
                line, col = _line_col(source, pos)
                nodes.append(Text(content="{", line=line, col=col))
                pos += 1
                continue

            # Attempt to tokenize a compile-time variable.
            m = _VAR_COMPILE_RE.match(source, pos)
            if m:
                line, col = _line_col(source, pos)
                nodes.append(VarCompile(name=m.group("name"), line=line, col=col))
                pos = m.end()
                continue

            # Regex failed → either malformed content or no closing `}}`.
            # Determine whether it is unterminated (no `}}` before next `<<`
            # or EOF) to pick the right token span for the error.
            close = source.find("}}", pos + 2)
            next_ang = source.find("<<", pos + 2)
            if close == -1 or (next_ang != -1 and next_ang < close):
                # Unterminated: scan to end-of-line or next `<<`.
                newline = source.find("\n", pos)
                end_of_line = newline if newline != -1 else source_len
                ang = source.find("<<", pos)
                token_end = min(end_of_line, ang if ang != -1 else source_len)
                token = source[pos:token_end] if token_end > pos else source[pos:pos + 2]
            else:
                # Malformed: has `}}` but bad name content.
                token = source[pos:close + 2]

            line, col = _line_col(source, pos)
            raise errors.UnknownDirectiveError(
                f"unknown directive '{token}'",
                file=relative_path,
                line=line,
                col=col,
                token=token,
                hint=_var_compile_hint(line),
                source=source,
            )

        elif best_type == "<<":
            match = _INCLUDE_RE.match(source, pos)
            if match is not None:
                matched = match.group(0)
                # Escape sequences aren't interpreted in v1; a literal `\"` inside
                # the matched slice is a silent-corruption risk (value truncated
                # at the first `"`). Reject explicitly so authors get a hint.
                if '\\"' in matched:
                    raise _make_unknown_error(
                        source, relative_path, pos, matched, hint=_QUOTING_HINT
                    )
                path_value = match.group("path")
                # Whitespace-only path values are rejected early — authors would
                # otherwise get a confusing MISSING_FRAGMENT with a space as the
                # leaf name rather than a clear parse error.
                if not path_value.strip():
                    raise _make_unknown_error(
                        source, relative_path, pos, matched,
                        hint="path value must be a non-empty, non-whitespace string",
                    )
                # Absolute POSIX paths (leading `/`) escape the tier-cascade
                # anchoring — reject at the parser so authors get a clear
                # diagnostic instead of a silent arbitrary-file-read.
                if path_value.startswith("/"):
                    raise _make_unknown_error(
                        source, relative_path, pos, matched,
                        hint=(
                            "absolute include paths are not allowed — use a "
                            "relative path such as 'fragments/<name>.template.md', "
                            "a './<name>' skill-local path, or a "
                            "'<moduleId>/<name>' cross-module path"
                        ),
                    )
                if "\\" in path_value:
                    raise _make_unknown_error(
                        source, relative_path, pos, matched,
                        hint=(
                            "backslash characters are not allowed in include paths — "
                            "use forward slashes ('/') as the path separator on all "
                            "platforms. Backslash is the Windows path separator and "
                            "is not portable; on POSIX filesystems it is a literal "
                            "byte in filenames, which produces confusing missing-"
                            "fragment errors when authors intended a path separator."
                        ),
                    )
                # Reject ASCII control characters in path values.
                for ch in path_value:
                    if ord(ch) < 0x20 or ord(ch) == 0x7F:
                        raise _make_unknown_error(
                            source, relative_path, pos, matched,
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
                # Reject a duplicate `path` key in the extras.
                if any(name == "path" for name, _ in extras):
                    raise _make_unknown_error(
                        source, relative_path, pos, matched,
                        hint="duplicate 'path' attribute — each attribute may appear at most once",
                    )
                # Reject duplicate attribute names.
                names = [name for name, _ in extras]
                if len(names) != len(set(names)):
                    raise _make_unknown_error(
                        source, relative_path, pos, matched,
                        hint="duplicate attribute names are not allowed in <<include>>",
                    )
                # Sort by attribute name — deterministic order.
                props = tuple(sorted(extras, key=lambda pair: pair[0]))
                line, col = _line_col(source, pos)
                nodes.append(Include(
                    src=path_value,
                    props=props,
                    line=line,
                    col=col,
                    raw_token=match.group(0),
                ))
                pos = match.end()
                continue

            # Not a valid include — recover a reasonable token for the error.
            newline = source.find("\n", pos)
            close_angle = source.find(">>", pos)
            if close_angle != -1 and (newline == -1 or close_angle < newline):
                token = source[pos:close_angle + 2]
            else:
                end = newline if newline != -1 else source_len
                token = source[pos:end]

            hint: str | None = None
            if token.startswith("<<include") and '\\"' in token:
                hint = _QUOTING_HINT
            raise _make_unknown_error(source, relative_path, pos, token, hint=hint)

        else:  # best_type == "{"
            # Single brace — try to tokenize a runtime variable {name}.
            m = _VAR_RUNTIME_RE.match(source, pos)
            if m:
                line, col = _line_col(source, pos)
                nodes.append(VarRuntime(name=m.group("name"), line=line, col=col))
                pos = m.end()
            else:
                # Single `{` not forming a valid `{name}` — emit as passthrough
                # text (e.g. `{` in code blocks, JSON literals, frontmatter).
                line, col = _line_col(source, pos)
                nodes.append(Text(content="{", line=line, col=col))
                pos += 1
            continue

    if not nodes:
        nodes.append(Text(content="", line=1, col=1))
    return nodes
