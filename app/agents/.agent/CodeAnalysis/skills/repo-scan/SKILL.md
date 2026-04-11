---
name: repo-scan
description: Scan repository files and maintain stable index/change metadata for downstream analysis.
---

# repo-scan

## Goal

Scan the target repository, detect added/modified/deleted files, and maintain minimal JSON memory for generation/refresh workflows.

## Structure

In this skill, **repository root** means `<repo_local_path>`. Use the **repo local path from your runtime context** (the path shown as "Code repository path: ..." in your system prompt) as `<repo_local_path>`.

Primary outputs:
- `<repo_local_path>/.Pando/cache/file_index.json`
- `<repo_local_path>/.Pando/run/latest.json`

## Inputs

- `repo_local_path`

Optional advanced context (for very large repositories):
- `include_globs` (optional, only for constrained scans)
- `exclude_globs` (optional, only for constrained scans)

## Outputs

- `<repo_local_path>/.Pando/cache/file_index.json`
- `<repo_local_path>/.Pando/run/latest.json`
- Standard return fields:
  - `scan_started_at`
  - `scan_finished_at`
  - `added_count`
  - `modified_count`
  - `deleted_count`
  - `error_count`
  - `changed_file_paths`
  - `total_file_count`
  - `repo_size_tier` (`small` / `medium` / `large`)
  - `scan_strategy` (`full_scan` / `constrained_scan`)
- The standard return fields MUST be persisted into `<repo_local_path>/.Pando/run/latest.json`.

## Execution Steps

1. Ensure `<repo_local_path>/.Pando/`, `<repo_local_path>/.Pando/cache/`, and `<repo_local_path>/.Pando/run/` exist.
2. Default to full recursive scan. For very large repositories, apply constrained scan using `include_globs` / `exclude_globs`.
3. Skip noisy/system folders (e.g. `.git`, `node_modules`, `dist`, `build`, `.venv`, `__pycache__`).
4. Build minimal index fields per file: `path`, `size`, `mtime`, `sha1`, `language`.
5. Compute scan-scale metrics: `total_file_count`.
6. Classify `repo_size_tier` using shared thresholds:
   - `small`: files < 2,000
   - `medium`: files 2,000-7,999
   - `large`: files >= 8,000
7. Compare with previous `file_index.json` and compute `added`, `modified`, `deleted`.
8. Write updated `file_index.json` and update `latest.json` scan summary.

## Tooling

- Use `dir_read` for root and key subdirectory discovery.
- Use `glob_search` to collect candidate files quickly.
- Use `file_read` only when needed to enrich language/type inference.
- Use `file_write` with `mode="w"` to persist index and run summary outputs.

## Hard Constraints

- Keep JSON minimal: no large text payloads in index or run summary.
- Output path normalization must be stable across runs.
- Change-set quality must be prioritized over scan breadth.
- Do not create test files or README files.

## Dependencies

- Upstream entry: `repo_analysis`
- Downstream consumers: `structure-analyze`, `generate-doc`, `refresh-doc`, `generate-readme`
