# Runtime Information

Information about the runtime environment and workspace to help the agent and tools locate and use memory and history files.

## Runtime
{{ runtime }}

## Workspace
Your workspace is at: {{ agent_workspace }}
- Long-term memory: {{ agent_workspace }}/memory/MEMORY.md
- History log: {{ agent_workspace }}/memory/HISTORY.md (grep-searchable)

## Memory
- Remember important facts: write to {{ agent_workspace }}/memory/MEMORY.md
- Recall past events: grep {{ agent_workspace }}/memory/HISTORY.md"""