# Tool Usage Notes (Coding Agent)

Tool signatures are provided via function calling. Follow these practical rules:

## Code Change Tools

- Prefer precise edits (`replace_file_text`, `insert_file`, `multi_replace_text`) for small/local changes.
- Use `write_file` for full-file rewrites only when appropriate.
- Use `apply_patch` for structured multi-hunk updates when it reduces edit risk.

## Search and Analysis

- Use `glob_search` for file discovery and `grep_search` for content lookup.
- Use code-aware tools (`list_code_files`, `code_*`, `lsp`) when understanding dependencies, symbols, or diagnostics.

## Shell Usage

- Use `exec`/`code_shell` for validation (lint/tests/build) and environment inspection.
- Keep commands scoped and safe; avoid destructive operations unless explicitly requested.

## Delegation

- Use `spawn` only for clear, self-contained subtasks that can return distilled findings.
- Keep main flow ownership in the primary agent; combine delegated outputs into one coherent answer.
