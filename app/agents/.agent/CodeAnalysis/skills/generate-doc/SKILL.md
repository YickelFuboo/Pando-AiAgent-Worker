---
name: generate-doc
description: Generate full `.Pando` design docs from scan and structure evidence.
---

# generate-doc

## Goal

Generate complete design documentation for the repository in `<repo_local_path>/.Pando/docs` from validated evidence.

## Structure

In this skill, **repository root** means the local repository base directory represented by `<repo_local_path>`.
Use the **repo local path from your runtime context** (the path shown as "Code repository path: ..." in your system prompt) as `<repo_local_path>`.

Primary outputs:
- `<repo_local_path>/.Pando/docs/overview.md`
- `<repo_local_path>/.Pando/docs/architecture.md`
- `<repo_local_path>/.Pando/docs/decisions.md`
- `<repo_local_path>/.Pando/manifest.json`

## Inputs

- `repo_local_path`
- `analysis_context` (scan + structure outputs)
- `doc_scope` (`full` or `partial`, optional)

## Outputs

- `<repo_local_path>/.Pando/docs/architecture.md`
- `<repo_local_path>/.Pando/docs/overview.md`
- `<repo_local_path>/.Pando/docs/decisions.md`
- `<repo_local_path>/.Pando/manifest.json`
- Standard return fields:
  - `generated_doc_paths`
  - `generated_docs_count`
  - `generation_finished_at`

## Document Contract

- `overview.md`: goals, stack, runtime, directory map.
- `architecture.md`: layers, major flows, component interactions, boundaries.
- `decisions.md`: key decisions, trade-offs, assumptions, risks.

## Mode Selection

- Use this skill for full generation workflows.
- If this is a refresh workflow, use `refresh-doc` instead.

## Tooling

- Use `dir_read` / `glob_search` / `grep_search` for scoped evidence discovery.
- Use `file_read` for all factual extraction.
- Use `file_write` with `mode="w"` for final document writes.

## Execution Steps

1. Build `overview.md` from scan and structure evidence.
2. Build `architecture.md` with explicit boundaries and flow narratives.
3. Build `decisions.md` from observed constraints, implementation patterns, and risks.
4. Add a coverage declaration section in `overview.md`:
   - analyzed scope
   - excluded scope (if any)
   - repository size tier and execution strategy (`single_pass` or `layered_passes`)
5. Update `manifest.json` with generator metadata and generation timestamp.
6. Write each output as complete Markdown/JSON files (no placeholder sections).

## Hard Constraints

- Do not fabricate implementation details, APIs, or architecture conclusions.
- Use only repository-derived evidence.
- Do not leave TODO/placeholders in final docs.
- Keep `.Pando` docs structurally stable across generation/refresh runs and Q&A reuse.
- If analysis is layered, explicitly declare non-covered or deferred areas.

## Dependencies

- Upstream inputs: `repo-scan` and `structure-analyze`
- Alternative path: use `refresh-doc` instead of this skill in full refresh mode
