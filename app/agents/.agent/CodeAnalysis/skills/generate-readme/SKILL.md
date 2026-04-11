---
name: generate-readme
description: Generate a high-quality README from real repository files.
---

# generate-readme

## Goal

Generate a professional README for the target repository.  
Evidence-first rule: every README claim must come from actual file reads, never from assumptions.

## Structure

In this skill, **repository root** means the local repository base directory represented by `<repo_local_path>`.
Use the **repo local path from your runtime context** (the path shown as "Code repository path: ..." in your system prompt) as `<repo_local_path>`.

The primary README output path is:
- `<repo_local_path>/README.md`

## Mode Selection

Before generating content, determine README mode:

- If `<repo_local_path>/README.md` exists, use **Update README Steps**.
- If `<repo_local_path>/README.md` does not exist, use **Create README Steps**.

## Create README Steps

1. Use specified tools to collect context from `<repo_local_path>`:
   - Use `dir_read` to read top-level and key subdirectory structure.
   - Use `glob_search` to locate candidate files (main entry, config, docs, examples, license).
   - Use `grep_search` to quickly locate keywords when narrowing candidate files.
2. Use `file_read` to gather evidence from:
   - Main project file(s) in repository root
   - Configuration files (`package.json`, `setup.py`, `pyproject.toml`, `requirements.txt`, etc.)
   - Documentation files (root or `docs/`)
   - Example/usage files (`examples/`, `demo/`, sample scripts)
3. Build full README sections from evidence:
   - Project Title and Description
   - Features
   - Installation
   - Usage
   - Contributing
   - License (only if LICENSE exists)
4. Output a complete README in Markdown (not partial fragments), and overwrite `<repo_local_path>/README.md` via `file_write` with `mode="w"`.

## Update README Steps

1. Read existing `<repo_local_path>/README.md` first and preserve valid structure and manually maintained content whenever possible.
2. Identify changed code areas before updating README:
   - Prefer files changed after README last modified time
   - If change-time comparison is unavailable, use recent critical files from main/config/docs/examples as update candidates
3. Use `file_read` on affected files and map updates to README sections.
4. Update only impacted sections first, then normalize overall consistency (terminology, headings, links, examples).
5. Keep evidence traceability: each updated claim must map to readable files in the repository.
6. Persist the final README as a complete document (not partial patch) by overwriting `<repo_local_path>/README.md` via `file_write` with `mode="w"`.

## Section Requirements

- **Project Title and Description**: clear name, value proposition, badges if available
- **Features**: key capabilities with concise explanations
- **Installation**: dependencies, setup steps, platform notes when needed
- **Usage**: basic examples, common scenarios, API overview when applicable
- **Contributing**: contributor workflow, dev setup, PR expectations
- **License**: include only when LICENSE file exists

## Hard Constraints

- All README information must come from actual `file_read` results.
- Do not infer undocumented functionality, interfaces, or workflows.
- If evidence is insufficient, explicitly mark as "unknown/to be verified".
- Use clear Markdown structure (headings, lists, code blocks) for readability.

## Dependencies

- Can be called by `repo_analysis` as repository entry-document generation.
- Can run alongside `repo-scan` and `structure-analyze`, but factual claims must still be based on file-read evidence.
