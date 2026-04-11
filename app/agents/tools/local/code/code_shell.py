import sys
from app.agents.tools.local.shell_exec import ExecTool


class CodeShellTool(ExecTool):
    @property
    def name(self) -> str:
        return "code_shell"

    @property
    def description(self) -> str:
        base = """Executes a shell command for code project workflows with optional timeout and safety checks.

All commands run in the current process directory by default. Use `working_dir` if you need a different directory.
Avoid `cd <directory> && <command>` patterns.

IMPORTANT:
- Use this tool for terminal operations like git, npm, pnpm, pip, docker, lint, build, and test.
- Do not use this tool for file read/write/edit/search when dedicated tools are available.

Before executing:
1) Directory verification
- If the command creates files/directories, verify the parent directory first.

2) Command execution
- Quote paths containing spaces with double quotes.
- Execute after quoting and capture full output.

Usage notes:
- `command` is required.
- `timeout` is in milliseconds. Default is 120000ms.
- `description` should be a clear 5-10 word summary.
- Prefer direct commands instead of pre-truncating output with head/tail.
- Prefer dedicated tools when possible:
  - file search -> glob
  - content search -> grep
  - file read -> read
  - file edit -> edit
  - file write -> write
- For multiple commands:
  - Use parallel calls for independent commands.
  - Use `&&` when sequence matters.
  - Use `;` only when earlier failures can be ignored.
  - Do not separate commands with newlines.

Git safety:
- Only commit when explicitly requested by user.
- Never modify git config.
- Avoid destructive git operations unless explicitly requested.
- Do not use interactive git flags.

GitHub/PR:
- Use `gh` for GitHub operations.
- Return PR URL after creation.
"""
        if sys.platform == "win32":
            base += " On Windows, use PowerShell/cmd-compatible syntax."
        return base
