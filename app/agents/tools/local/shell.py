import asyncio
import os
import re
import subprocess
import sys
import logging
from pathlib import Path
from typing import Any
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult

DENY_PATTERNS_LINUX = [
    r"\brm\s+-[rf]{1,2}\b",
    r"\bdel\s+/[fq]\b",
    r"\brmdir\s+/s\b",
    r"(?:^|[;&|]\s*)format\b",
    r"\b(mkfs|diskpart)\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd",
    r"\b(shutdown|reboot|poweroff)\b",
    r":\(\)\s*\{.*\};\s*:",
]

DENY_PATTERNS_WIN = [
    r"\bdel\s+/[fq]\b",
    r"\brmdir\s+/s",
    r"\bformat\b",
    r"\bdiskpart\b",
    r"\b(shutdown|reboot)\b",
]


def _run_shell_sync(command: str, cwd: str, timeout_sec: int) -> tuple[bytes, bytes, int]:
    """同步执行 shell 命令，不依赖 asyncio 子进程，适用于 Windows 任意事件循环。"""
    r = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        timeout=timeout_sec,
    )
    return (r.stdout or b""), (r.stderr or b""), (r.returncode or 0)


class ExecTool(BaseTool):
    """Tool to execute shell commands."""

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
    ):
        self.timeout = timeout
        self.working_dir = working_dir or os.getcwd()
        default_deny = DENY_PATTERNS_WIN if sys.platform == "win32" else DENY_PATTERNS_LINUX
        self.deny_patterns = deny_patterns or default_deny
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace

    @property
    def name(self) -> str:
        return "exec"

    @property
    def description(self) -> str:
        base = """Execute a shell command and return its output.

Usage:
- Use this tool for terminal operations.
- Do not use this tool for file read/write/search/edit when dedicated tools are available.
- Use `working_dir` to change directories. Avoid `cd <dir> && <command>` patterns.
- Always quote paths that contain spaces with double quotes.
- `timeout` is in milliseconds. If omitted, the default timeout is 120000ms.
- If running multiple commands: use parallel tool calls for independent commands, or use `&&` when order matters.
- Use `;` only when you want later commands to run even if earlier commands fail.
"""
        if sys.platform == "win32":
            base += " On Windows, use PowerShell or cmd syntax; Unix-only commands may be unavailable by default."
        return base
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute"
                },
                "working_dir": {
                    "type": "string",
                    "description": "Optional working directory for the command"
                },
                "timeout": {
                    "type": "number",
                    "description": "Optional timeout in milliseconds."
                },
                "description": {
                    "type": "string",
                    "description": "Optional short description of what this command does."
                },
            },
            "required": ["command"]
        }

    async def execute(
        self,
        command: str,
        working_dir: str | None = None,
        timeout: float | None = None,
        description: str | None = None,
        **kwargs: Any
    ) -> ToolResult:
        _ = description
        cwd = working_dir or self.working_dir or os.getcwd()
        timeout_sec = self.timeout
        if timeout is not None:
            if timeout < 0:
                return ToolErrorResult(f"Invalid timeout value: {timeout}. Timeout must be a positive number.")
            timeout_sec = max(1, int(float(timeout) / 1000))

        try:
            cwd_path = Path(cwd).expanduser().resolve()
        except Exception:
            return ToolErrorResult(f"Invalid working_dir: {cwd!r}")

        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return ToolErrorResult(guard_error)

        try:
            if sys.platform == "win32":
                loop = asyncio.get_event_loop()
                stdout, stderr, returncode = await loop.run_in_executor(
                    None,
                    _run_shell_sync,
                    command,
                    str(cwd_path),
                    timeout_sec,
                )
            else:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(cwd_path),
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=timeout_sec,
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        pass
                    return ToolErrorResult(f"Error: Command timed out after {timeout_sec} seconds")
                returncode = process.returncode or 0

            output_parts = []
            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))
            
            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")

            if returncode != 0:
                output_parts.append(f"\nExit code: {returncode}")

            result = "\n".join(output_parts) if output_parts else "(no output)"
            max_len = 10000
            if len(result) > max_len:
                result = result[:max_len] + f"\n... (truncated, {len(result) - max_len} more chars)"

            return ToolSuccessResult(result)

        except subprocess.TimeoutExpired:
            return ToolErrorResult(f"Error: Command timed out after {timeout_sec} seconds")
        except Exception as e:
            msg = str(e) or repr(e)
            logging.error("Error executing command: %s (type=%s)", msg, type(e).__name__)
            return ToolErrorResult(f"Error executing command: {msg}")

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """Best-effort safety guard for potentially destructive commands."""
        cmd = command.strip()
        lower = cmd.lower()

        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "Error: Command blocked by safety guard (dangerous pattern detected)"

        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "Error: Command blocked by safety guard (not in allowlist)"

        if self.restrict_to_workspace:
            if "..\\" in cmd or "../" in cmd:
                return "Error: Command blocked by safety guard (path traversal detected)"
            cwd_path = Path(cwd).resolve()
            win_paths = re.findall(r"[A-Za-z]:\\[^\\\"']+", cmd)
            posix_paths = re.findall(r"(?:^|[\s|>])(/[^\s\"'>]+)", cmd)
            for raw in win_paths + posix_paths:
                try:
                    p = Path(raw.strip()).resolve()
                except Exception:
                    continue
                if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
                    return "Error: Command blocked by safety guard (path outside working dir)"

        return None
