---
name: structure-analyze
description: Analyze module boundaries and dependencies from repository structure and source evidence.
---

# structure-analyze

## Goal

Extract module responsibilities and dependency relations from repository structure and code references.

## Structure

In this skill, **repository root** means the local repository base directory represented by `<repo_local_path>`.
Use the **repo local path from your runtime context** (the path shown as "Code repository path: ..." in your system prompt) as `<repo_local_path>`.

Primary outputs:
- `<repo_local_path>/.Pando/docs/modules/<module>.md`
- `<repo_local_path>/.Pando/docs/dependencies.md`

## Inputs

- `repo_local_path`
- `changed_files` (optional)
- `focus_paths` (optional)

## Outputs

- `<repo_local_path>/.Pando/docs/modules/<module>.md`
- `<repo_local_path>/.Pando/docs/dependencies.md`
- Standard return fields:
  - `module_count`
  - `dependency_edge_count`
  - `updated_module_paths`
  - `analysis_finished_at`

## Mode Selection

- Use full mode when there is no prior module/dependency documentation.
- Use scoped mode when `changed_files` or `focus_paths` is provided (for constrained analysis in very large repositories).

## Tooling

- Use `glob_search` / `grep_search` for module and dependency candidate discovery.
- Use `code_dependencies_search` and `code_related_files_search` for code-aware dependency evidence.
- Use `file_read` for evidence grounding and `file_write` for final outputs.

## Execution Steps

1. Define module boundaries using top-level and second-level business directories first.
2. Identify each module's role, key entry points, and major interfaces.
3. Extract static dependency evidence (`import`, reference, call-chain clues).
4. Build module-level and file-level dependency summaries.
5. Generate module docs and dependency docs with optional Mermaid graphs where helpful.

## Hard Constraints

- Do not fabricate modules, capabilities, or dependency directions.
- Keep naming and terminology consistent between `modules/*.md` and `dependencies.md`.
- Mark uncertain relationships as `unknown/to be verified`.
- Prioritize maintainability signal over exhaustive low-value detail.

## Dependencies

- Upstream input: `repo-scan` index and change set
- Downstream consumers: `generate-doc`, `refresh-doc`
