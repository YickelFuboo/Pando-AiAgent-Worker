---
name: repo_analysis
description: Orchestrate repository analysis and documentation generation workflows for `.Pando` artifacts.
---

# repo_analysis

## Goal

Provide a single entry point for repository analysis and document generation tasks, and route them into stable, evidence-based `.Pando` outputs.

## Structure

In this skill, **repository root** means the local repository base directory represented by `<repo_local_path>`.
Use the **repo local path from your runtime context** (the path shown as "Code repository path: ..." in your system prompt) as `<repo_local_path>`.
All downstream skills must read from and write to `<repo_local_path>/.Pando`.

The minimum required `.Pando` artifacts are:
- `<repo_local_path>/.Pando/docs/overview.md`
- `<repo_local_path>/.Pando/docs/architecture.md`
- `<repo_local_path>/.Pando/docs/modules/<module>.md`
- `<repo_local_path>/.Pando/docs/dependencies.md`
- `<repo_local_path>/.Pando/docs/decisions.md`
- `<repo_local_path>/.Pando/cache/file_index.json`
- `<repo_local_path>/.Pando/run/latest.json`
- `<repo_local_path>/.Pando/manifest.json`

## Inputs

- `repo_local_path`

## Outputs

- Routing decision (`selected_workflow`, `selected_skills`)
- Scale decision (`repo_size_tier`, `execution_strategy`)
- Execution summary from downstream skills
- Final artifact status for `<repo_local_path>/.Pando`

## Skill Graph

Downstream skills:
1. `repo-scan`
2. `structure-analyze`
3. `generate-doc`
4. `refresh-doc`

## Routing Rules

Auto-detect mode before execution:
- If `<repo_local_path>/.Pando` does not exist, or required artifacts are missing, select **generate** mode.
- If `<repo_local_path>/.Pando` exists and required artifacts are present, select **refresh** mode.

Required artifacts for refresh detection:
- `<repo_local_path>/.Pando/docs/overview.md`
- `<repo_local_path>/.Pando/docs/architecture.md`
- `<repo_local_path>/.Pando/docs/dependencies.md`
- `<repo_local_path>/.Pando/docs/decisions.md`
- `<repo_local_path>/.Pando/cache/file_index.json`
- `<repo_local_path>/.Pando/run/latest.json`
- `<repo_local_path>/.Pando/manifest.json`

## Scale Assessment

Determine repository size after initial scan metrics are available from `repo-scan`:
- **small**: `total_file_count < 2,000`
- **medium**: `2,000 <= total_file_count < 8,000`
- **large**: `total_file_count >= 8,000`

## Execution Strategy

- **single_pass** (small): run full repository analysis in one pass.
- **layered_passes** (medium/large): run multiple passes by business domains or service groups.
  - Pass 1: core/runtime-critical directories
  - Pass 2: major feature modules
  - Pass 3+: remaining modules and long-tail areas

Execution chain by mode:
- **generate + single_pass**: `repo-scan -> structure-analyze -> generate-doc`
- **generate + layered_passes**: repeat `repo-scan(constrained) -> structure-analyze(constrained)` by layer, then run `generate-doc`
- **refresh + single_pass**: `repo-scan -> structure-analyze -> refresh-doc`
- **refresh + layered_passes**: repeat constrained `repo-scan -> structure-analyze` by layer, then run `refresh-doc`

## Ownership Rules

- `generate-doc` owns `overview.md`, `architecture.md`, `decisions.md`, and `manifest.json`.

## Execution Rules

- Use `snake_case` for all output fields.
- Time fields use `*_at`; count fields use `*_count`; path lists use `*_paths`.
- Prefer Markdown outputs; keep JSON minimal and operational.
- Do not create tests or extra README files unless explicitly requested.
- Keep evidence-first behavior across all downstream skills.
- For layered passes, each pass must append/update stable scan summaries before next pass starts.
- For layered passes, avoid cross-layer terminology drift (module names and dependency labels must stay consistent).

## Hard Constraints

- Do not fabricate functionality, interfaces, architecture conclusions, or process claims.
- Do not bypass `.Pando` contracts or produce ad-hoc artifacts.
- Do not handle repository Q&A in this skill; route Q&A to `repo_qa`.
- Do not skip coverage declaration when layered_passes are used.

## Dependencies

- This is the top-level entry skill.
- All other repository-analysis skills are downstream dependencies of this skill.
