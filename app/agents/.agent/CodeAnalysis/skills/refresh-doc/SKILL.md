---
name: refresh-doc
description: Fully refresh existing `.Pando` docs from the current repository state.
---

# refresh-doc

## Goal

Refresh an existing `.Pando` documentation set using current repository state, while preserving stable output contracts.

## Structure

In this skill, **repository root** means the local repository base directory represented by `<repo_local_path>`.
Use the **repo local path from your runtime context** (the path shown as "Code repository path: ..." in your system prompt) as `<repo_local_path>`.

Primary refresh targets:
- `<repo_local_path>/.Pando/docs/overview.md`
- `<repo_local_path>/.Pando/docs/modules/*.md`
- `<repo_local_path>/.Pando/docs/dependencies.md`
- `<repo_local_path>/.Pando/docs/architecture.md`
- `<repo_local_path>/.Pando/docs/decisions.md`
- `<repo_local_path>/.Pando/run/latest.json`

## Inputs

- `repo_local_path`

## Outputs

- Refreshed `<repo_local_path>/.Pando/docs/*.md`
- Updated `<repo_local_path>/.Pando/run/latest.json`
- Standard return fields:
  - `updated_doc_paths`
  - `updated_docs_count`
  - `impact_module_count`
  - `refresh_finished_at`

## Refresh Priority

1. Refresh `overview.md` to keep project-level summary aligned with current repository state
2. Refresh `modules/*.md` based on current module boundaries
3. Refresh `dependencies.md` from current dependency evidence
4. Refresh `architecture.md` and `decisions.md`
5. Update `run/latest.json` refresh summary

## Mode Selection

- Use this skill when `.Pando` baseline exists and auto-detection selects refresh mode.
- If `.Pando` baseline is missing, route to `generate-doc` generation flow.

## Tooling

- Use `glob_search` / `grep_search` to narrow impacted sections quickly.
- Use `file_read` to extract current and changed evidence.
- Use `file_write` for full-file overwrite writes after section-level merge.

## Execution Steps

1. Load current `.Pando` docs and repository evidence as refresh baseline.
2. Rebuild each target doc (`overview`, `modules`, `dependencies`, `architecture`, `decisions`) from current evidence.
3. Preserve user-authored content only when explicitly marked as non-generated sections.
4. Record refresh stats and updated paths into `run/latest.json`.

## Hard Constraints

- Keep output contracts stable across refresh runs.
- Ensure refreshed docs remain fully evidence-based and traceable.
- Keep section structure stable for future traceability and Q&A reuse.

## Dependencies

- Upstream inputs: `repo-scan` and `structure-analyze`
- Alternative generation-mode counterpart: `generate-doc`
