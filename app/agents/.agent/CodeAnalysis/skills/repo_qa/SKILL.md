---
name: repo_qa
description: Answer repository questions with evidence-first retrieval from `.Pando`, then direct source fallback when needed.
---

# repo_qa

## Goal

Provide accurate repository Q&A using existing `.Pando` artifacts first, and only read source code directly when evidence is insufficient.

## Structure

In this skill, **repository root** means the local repository base directory represented by `<repo_local_path>`.
Use the **repo local path from your runtime context** (the path shown as "Code repository path: ..." in your system prompt) as `<repo_local_path>`.

Primary evidence locations:
- `<repo_local_path>/.Pando/docs/overview.md`
- `<repo_local_path>/.Pando/docs/architecture.md`
- `<repo_local_path>/.Pando/docs/modules/*.md`
- `<repo_local_path>/.Pando/docs/dependencies.md`
- `<repo_local_path>/.Pando/docs/decisions.md`

## Inputs

- `repo_local_path`
- `question`: natural-language repository question
- `scope` (optional): module/path/component scope hints

## Outputs

- Evidence-grounded answer in Markdown
- `evidence_file_paths`
- `evidence_status` (`sufficient` / `partial` / `insufficient`)
- `followup_actions` (optional, only when additional source reads are needed)

## Mode Selection

- If `.Pando` evidence is sufficient, answer directly from `.Pando`.
- If `.Pando` evidence is partial, combine `.Pando` with targeted source reads.
- If evidence is insufficient, read relevant source files directly, then answer.

## Tooling

- Use `file_read` for `.Pando` docs and source files.
- Use `glob_search` / `grep_search` to narrow evidence files.
- Use `code_related_files_search` / `code_dependencies_search` for code-aware evidence expansion.

## Execution Steps

1. Parse the user question and infer target scope (`module`, `flow`, `spec`, `code path`).
2. Retrieve candidate evidence from `.Pando` first.
3. Validate whether existing evidence directly supports the answer.
4. If needed, run scoped source retrieval directly from repository files.
5. Produce a concise answer with explicit evidence traceability.

## Hard Constraints

- Do not fabricate behavior, interfaces, mechanisms, or architecture claims.
- If evidence is missing, explicitly say `unknown/to be verified`.
- Do not trigger `repo-scan`, `generate-doc`, or `refresh-doc` in Q&A flow.
- Do not modify `.Pando/run/latest.json` or `.Pando/cache/file_index.json` in Q&A flow.
- Keep answer traceable to concrete file paths.

## Dependencies

- This is the dedicated Q&A entry skill.
- Uses `.Pando` docs first and direct source reads as fallback.
