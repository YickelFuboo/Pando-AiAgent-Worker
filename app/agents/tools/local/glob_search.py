import fnmatch
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from app.agents.tools.base import BaseTool
from app.agents.tools.schemes import ToolErrorResult, ToolResult, ToolSuccessResult

_BRACE_SEGMENT = re.compile(r"\{([^{}]+)\}")


def _expand_brace_patterns(pattern: str) -> List[str]:
    """Expand bash-style {a,b,c} segments; fnmatch does not treat braces as alternation."""
    m = _BRACE_SEGMENT.search(pattern)
    if not m:
        return [pattern]
    inner = m.group(1)
    alts = [x.strip() for x in inner.split(",") if x.strip()]
    if not alts:
        return [pattern]
    prefix, suffix = pattern[: m.start()], pattern[m.end() :]
    out: List[str] = []
    for alt in alts:
        out.extend(_expand_brace_patterns(prefix + alt + suffix))
    return out


def _effective_patterns(pattern: str) -> List[str]:
    """Brace-expand, then add tail patterns for leading `**/` so `**/*.py` also matches root `foo.py` (fnmatch quirk)."""
    raw = _expand_brace_patterns(pattern)
    seen = list(dict.fromkeys(raw))
    for pat in list(seen):
        if pat.startswith("**/") and len(pat) > 3:
            tail = pat[3:]
            if tail and tail not in seen:
                seen.append(tail)
    return seen


class GlobTool(BaseTool):
    @property
    def name(self) -> str:
        return "glob_search"

    @property
    def description(self) -> str:
        return """Fast file pattern matching tool for local projects of any type.

Matching (Python fnmatch, not full POSIX glob):
- Wildcards: * (substring), ? (one char), [abc] (one of; [!a-z] negated). Each file is checked against (1) path relative to `path`, and (2) filename only—so `*.py` matches any `.py` under the search root.
- Patterns starting with `**/` (e.g. `**/*.ts`): the tool also applies the part after `**/`, so root-level files like `foo.ts` match. Prefix-only patterns like `app/**/*.py` do not match `app/x.py` one level under `app`; use `app/*.py` for that case or set `path` to `.../app` and use `*.py`.
- Brace `{a,b,c}` is expanded (e.g. `*.{py,toml}` -> `*.py`, `*.toml`).

Limits:
- Newest first by mtime; at most 100 paths returned.

When to use:
- Find files by name/extension; narrow `path` when the tree is large. For long multi-round exploration, prefer delegation (e.g. spawn) instead.
"""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": (
                        "fnmatch-style pattern. Wildcards: *, ?, [seq]. "
                        "Tested against the file path relative to `path` and against the filename alone (so *.ext hits any depth). "
                        "Brace alternation: *.{py,toml} -> *.py and *.toml. "
                        "Leading **/: e.g. **/*.js also applies the suffix pattern (*.js) so files directly under the search root match. "
                        "For a fixed subfolder prefix (e.g. app/), combine app/*.py and app/**/*.py or set path to that folder and use *.py."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Absolute directory to search; must exist. If omitted, uses the process current working directory (not necessarily the repo root)."
                    ),
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: Optional[str] = None, **kwargs: Any) -> ToolResult:
        if not pattern:
            return ToolErrorResult("pattern is required")

        try:
            if path:
                search = Path(path).expanduser()
                if not search.is_absolute():
                    return ToolErrorResult("path must be an absolute directory path")
                search = search.resolve()
            else:
                search = Path.cwd().resolve()
            if not search.exists() or not search.is_dir():
                return ToolErrorResult(f"glob failed: directory does not exist: {search}")
        except Exception as e:
            return ToolErrorResult(f"glob failed: {e}")

        limit = 100
        patterns = _effective_patterns(pattern)
        items: List[Tuple[str, float]] = []
        try:
            for p in search.rglob("*"):
                if not p.is_file():
                    continue

                rel = str(p.relative_to(search)).replace("\\", "/")
                if any(
                    fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(p.name, pat)
                    for pat in patterns
                ):
                    try:
                        mtime = p.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                    items.append((str(p), mtime))
        except Exception as e:
            return ToolErrorResult(f"glob failed: {e}")

        items.sort(key=lambda x: x[1], reverse=True)
        truncated = len(items) > limit
        final = items[:limit]
        if not final:
            return ToolSuccessResult("No files found")

        out = "\n".join([p for p, _ in final])
        if truncated:
            out += "\n\n(Results are truncated: showing 100 newest by mtime. Narrow `path` or use a more specific pattern.)"
        return ToolSuccessResult(out)
