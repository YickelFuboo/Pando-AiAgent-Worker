---
name: memory
description: Two-layer memory system with grep-based recall.
always: true
---

# Memory

## Structure

Memory files live under the workspace. Use the **workspace path from your runtime context** (the path in "Your workspace is at: ..." in your system prompt) as `<WORKSPACE_PATH>`:

- `<WORKSPACE_PATH>/memory/MEMORY.md` — Long-term facts (preferences, project context, relationships). Always loaded into your context.
- `<WORKSPACE_PATH>/memory/HISTORY.md` — Append-only event log. NOT loaded into context. Search it with grep.

## Search Past Events

```bash
grep -i "keyword" <WORKSPACE_PATH>/memory/HISTORY.md
```

Use the `exec` tool to run grep. Replace `<WORKSPACE_PATH>` with the workspace path from your context. Combine patterns: `grep -iE "meeting|deadline" <WORKSPACE_PATH>/memory/HISTORY.md`

## When to Update MEMORY.md

Write important facts immediately using `edit_file` or `write_file` to `<WORKSPACE_PATH>/memory/MEMORY.md`:
- User preferences ("I prefer dark mode")
- Project context ("The API uses OAuth2")
- Relationships ("Alice is the project lead")

## Auto-consolidation

Old conversations are automatically summarized and appended to `<WORKSPACE_PATH>/memory/HISTORY.md` when the session grows large. Long-term facts are extracted to `<WORKSPACE_PATH>/memory/MEMORY.md`. You don't need to manage this.
