# Tool Usage Notes (CodeAnalysis)

Use tools to collect reliable evidence, not to maximize tool count.

## Search and Inspection

- Use `glob_search` to locate candidate files quickly.
- Use `grep_search` for keywords, patterns, and call chains.
- Use `read_file`/`read_dir` for focused context reads.

## Code-Aware Analysis

- Prefer `list_code_files` and `code_*` tools to understand related files and dependencies.
- Use `lsp` for diagnostics, references, definitions, and symbol-level validation.

## Shell Verification

- Use `exec`/`code_shell` for read-only checks, diagnostics, and reproducible evidence.
- Avoid destructive or environment-changing commands unless explicitly requested.

## Writing Tools

- Writing is not the default behavior for this agent.
- Only use write/edit/patch tools when the user explicitly asks for code changes.

## Delegation

- Use `spawn` for large, independent analysis subtasks.
- Ask subagents for concise findings and merge results into one coherent conclusion.
