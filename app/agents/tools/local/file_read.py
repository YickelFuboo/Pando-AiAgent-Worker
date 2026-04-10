import logging
from pathlib import Path
from typing import Any, Dict, Optional
from app.domains.code_analysis.services.lsp.lsp_service import CodeLSPService
from ..base import BaseTool
from ..schemes import ToolResult, ToolSuccessResult, ToolErrorResult


DEFAULT_READ_LIMIT = 2000
MAX_LINE_LENGTH = 2000
MAX_BYTES = 50 * 1024
MAX_BYTES_LABEL = f"{MAX_BYTES // 1024} KB"


def _is_probably_binary(ext: str, size: int, head: bytes) -> bool:
    ext = ext.lower()
    if ext in {
        ".zip", ".tar", ".gz", ".exe", ".dll", ".so", ".class", ".jar", ".war", ".7z",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp",
        ".bin", ".dat", ".obj", ".o", ".a", ".lib", ".wasm", ".pyc", ".pyo",
    }:
        return True
    if size == 0:
        return False
    if b"\x00" in head:
        return True
    non_printable = 0
    for b in head:
        if b < 9 or (b > 13 and b < 32):
            non_printable += 1
    return non_printable / max(1, len(head)) > 0.3


class ReadFileTool(BaseTool):
    """文件读取工具"""

    def __init__(self,**kwargs:Any):
        self.kwargs=kwargs

    async def _warm_lsp(self, file_path:Path)->None:
        if self.kwargs.get("isCodeAgent") is not True:
            return
        repo_id=str(self.kwargs.get("repo_id") or "").strip()
        if not repo_id:
            return
        try:
            target=str(file_path.resolve())
            available=await CodeLSPService.has_clients(target,repo_id=repo_id)
            if not available:
                return
            await CodeLSPService.touch_file(target, wait_for_diagnostics=False, repo_id=repo_id)
        except Exception:
            return

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return """Read a file from the local filesystem. If the path does not exist, an error is returned.

Usage:
- The path parameter should be an absolute path.
- By default, this tool returns up to 2000 lines from the start of the file.
- The offset parameter is the line number to start from (1-indexed).
- To read later sections, call this tool again with a larger offset.
- Use the grep tool to find specific content in large files or files with long lines.
- If you are unsure of the correct file path, use the glob tool to look up filenames by glob pattern.
- Contents are returned with each line prefixed by its line number as `<line>: <content>`.
- Any line longer than 2000 characters is truncated.
- Call this tool in parallel when you know there are multiple files you want to read.
- Avoid tiny repeated slices (30 line chunks). If you need more context, read a larger window."""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The full path to the file to read."
                },
                "offset": {
                    "type": "integer",
                    "description": "Optional line number to start reading from (1-indexed)."
                },
                "limit": {
                    "type": "integer",
                    "description": f"Optional maximum number of lines to read. Default is {DEFAULT_READ_LIMIT}."
                }
            },
            "required": ["path"]
        }

    async def execute(
        self,
        path: str,
        offset: Optional[int] = None,
        limit: Optional[int] = None,
        **kwargs,
    ) -> ToolResult:
        try:
            if not path or not path.strip():
                logging.error("参数错误: path=%r", path)
                return ToolErrorResult("Missing path parameter")

            if offset is not None and offset < 1:
                return ToolErrorResult("offset must be greater than or equal to 1")

            if limit is not None and limit < 1:
                return ToolErrorResult("limit must be greater than or equal to 1")

            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                logging.warning("文件不存在: path=%s", file_path)
                return ToolErrorResult(f"File not found: {path}")

            if not file_path.is_file():
                logging.warning("不是文件路径: path=%s", file_path)
                return ToolErrorResult(f"Not a file: {path}")

            # 检查是否为二进制文件
            size = file_path.stat().st_size
            with open(file_path, "rb") as f:
                head = f.read(min(4096, size or 0))
            if _is_probably_binary(file_path.suffix, size, head):
                return ToolErrorResult(f"Cannot read binary file: {path}")

            # 读取文件内容
            off = offset or 1
            lim = limit or DEFAULT_READ_LIMIT

            raw = []
            bytes_count = 0
            total_lines = 0
            has_more = False
            truncated_by_bytes = False

            with open(file_path, "r", encoding="utf-8", errors="replace", newline="") as f:
                for line in f:
                    total_lines += 1
                    if total_lines < off:
                        continue
                    
                    # 超过限制行数，标记后直接退出，避免无效继续读取
                    if len(raw) >= lim:
                        has_more = True
                        break

                    text = line.rstrip("\n\r")
                    # 超长行截断
                    if len(text) > MAX_LINE_LENGTH:
                        text = text[:MAX_LINE_LENGTH] + f"... (line truncated to {MAX_LINE_LENGTH} chars)"
                    
                    add = len(text.encode("utf-8")) + (1 if raw else 0)
                    if bytes_count + add > MAX_BYTES:
                        truncated_by_bytes = True
                        has_more = True
                        break
                    raw.append(text)
                    bytes_count += add

            if total_lines < off and not (total_lines == 0 and off == 1):
                return ToolErrorResult(f"Offset {off} is out of range for this file ({total_lines} lines)")

            numbered = [f"{i + off}: {t}" for i, t in enumerate(raw)]
            content = "\n".join(numbered)
            last_read = off + len(raw) - 1 if raw else off - 1
            next_offset = last_read + 1
            truncated = has_more or truncated_by_bytes

            if truncated_by_bytes:
                content += f"\n\n(Output capped at {MAX_BYTES_LABEL}. Showing lines {off}-{last_read}. Use offset={next_offset} to continue.)"
            elif has_more:
                content += f"\n\n(Showing lines {off}-{last_read} of {total_lines}. Use offset={next_offset} to continue.)"
            else:
                content += f"\n\n(End of file - total {total_lines} lines)"

            output = "\n".join([
                f"<path>{file_path}</path>",
                "<content>",
                content,
                "</content>",
                f"<truncated>{str(truncated).lower()}</truncated>",
                f"<next_offset>{next_offset if truncated else ''}</next_offset>",
            ])
            if self.kwargs.get("isCodeAgent") is True:
                await self._warm_lsp(file_path)
            return ToolSuccessResult(output)

        except Exception as e:
            logging.error("读取文件异常: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to read file: {str(e)}") 