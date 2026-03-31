from typing import Dict,Any,Optional
import logging
import difflib
import re
from pathlib import Path
from ..base import BaseTool
from ..schemes import ToolResult,ToolSuccessResult,ToolErrorResult


def _trim_diff(diff: str) -> str:
    lines = diff.split("\n")
    content_lines = [
        ln for ln in lines
        if (ln.startswith("+") or ln.startswith("-") or ln.startswith(" "))
        and not ln.startswith("---")
        and not ln.startswith("+++")
    ]
    if not content_lines:
        return diff

    # 找到最小的缩进
    min_indent = None
    for ln in content_lines:
        content = ln[1:]
        if content.strip():
            m = re.match(r"^(\s*)", content)
            lead = len(m.group(1)) if m else 0
            min_indent = lead if min_indent is None else min(min_indent, lead)
    if not min_indent:
        return diff

    # 去除缩进
    out = []
    for ln in lines:
        if (ln.startswith("+") or ln.startswith("-") or ln.startswith(" ")) and not ln.startswith("---") and not ln.startswith("+++"):
            out.append(ln[0] + ln[1 + min_indent:])
        else:
            out.append(ln)
    return "\n".join(out)


def _two_files_patch(old_path: str, new_path: str, old_content: str, new_content: str) -> str:
    a = old_content.splitlines()
    b = new_content.splitlines()
    lines = list(difflib.unified_diff(a, b, fromfile=old_path, tofile=new_path, lineterm=""))
    return "\n".join(lines) + ("\n" if lines else "")


class WriteFileTool(BaseTool):
    """Write content to a file."""
    @property
    def name(self) -> str:
        return "write_file"   

    @property
    def description(self) -> str:
        return """Writes content to a file on the local filesystem.

Usage:
- Provide the target file with `path`.
- `mode='w'` overwrites the file (or creates it if missing); `mode='a'` appends content for chunked writes.
- Parent directories are created automatically if needed.
- If this is an existing file, read it first before writing to avoid accidental loss.
- Prefer editing existing files; do not create new files unless required by the task.
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked.
"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The full path to the file to write to."
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file. Prefer to keep each write chunk small to avoid tool call truncation.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["w","a"],
                    "description": "w=overwrite (first chunk), a=append (subsequent chunks). Default is w."
                }
            },
            "required": ["path", "content"]
        }  

    async def execute(self, path: str, content: str, mode: str = "w", **kwargs) -> ToolResult:
        try:
            if not path or not path.strip() or content is None:
                logging.error("Invalid parameters: path=%r, content=%r", path, content)
                return ToolErrorResult("Missing path or content parameter")     

            open_mode = "a" if mode == "a" else "w"

            file_path = Path(path).expanduser().resolve()
            existed = file_path.exists()
            if existed and not file_path.is_file():
                logging.error("Not a file: path=%s", file_path)
                return ToolErrorResult(f"Not a file: {path}")
            old_content = ""
            if existed and file_path.is_file():
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    old_content = f.read()

            file_path.parent.mkdir(parents=True, exist_ok=True)
                  
            with open(file_path, open_mode, encoding="utf-8") as f:
                f.write(content)

            new_content = ""
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                new_content = f.read()

            diff = _trim_diff(
                _two_files_patch(str(file_path), str(file_path), old_content, new_content)
            )

            action = "appended" if open_mode == "a" else "written"
            output = "\n".join([
                f"<path>{file_path}</path>",
                "<content>",
                f"Successfully {action} {len(content)} bytes to {path} (mode={open_mode})",
                "</content>",
                f"<exists>{str(existed).lower()}</exists>",
                f"<mode>{open_mode}</mode>",
                "<diff>",
                diff,
                "</diff>",
            ])
            return ToolSuccessResult(output)
            
        except Exception as e:
            logging.error("Failed to write file: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to write file: {str(e)}") 

class ReplaceFileTextTool(BaseTool):
    """Replace text in a file."""
    @property
    def name(self) -> str:
        return "replace_file_text"
    
    @property
    def description(self) -> str:
        return """Performs exact string replacements in files.

Usage:
- Provide the target file with `path`.
- You should read the file before editing to avoid accidental mismatches.
- Match `old_text` exactly as it appears in file content (including spaces/indentation).
- Prefer editing existing files. Do not create new files unless required.
- Only use emojis if the user explicitly requests it.
- The edit fails if `old_text` is not found in the file.
- By default, this tool replaces a single unique match.
- The edit fails if `old_text` appears multiple times and `replaceAll` is not true.
- When multiple matches exist, either provide more surrounding context in `old_text` or set `replaceAll=true`.
- Use `replaceAll` for file-wide renaming/replacement operations.
- Use `write_file` for full-file overwrite; `old_text` must not be empty in this tool."""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace"
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace with"
                },
                "replaceAll": {
                    "type": "boolean",
                    "description": "Replace all occurrences of old_text (default false)"
                }
            },
            "required": ["path", "old_text", "new_text"]
        }
    
    async def execute(
        self,
        path: str,
        old_text: str,
        new_text: str,
        replaceAll: Optional[bool] = None,
        **kwargs: Any
    ) -> ToolResult:
        try:
            if not path or not path.strip() or old_text is None or new_text is None:
                logging.error("Invalid parameters: path=%r, old_text=%r, new_text=%r", path, old_text, new_text)
                return ToolErrorResult("Missing path, old_text or new_text parameter")
            if old_text == "":
                return ToolErrorResult("old_text must not be empty. Use write_file for full overwrite.")
            if old_text == new_text:
                return ToolErrorResult("No changes to apply: old_text and new_text are identical.")

            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                logging.warning("File not found: path=%s", file_path)
                return ToolErrorResult(f"File not found: {path}")

            if not file_path.is_file():
                logging.warning("Not a file: path=%s", file_path)
                return ToolErrorResult(f"Not a file: {path}")

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            if old_text not in content:
                logging.warning(
                    "old_text not found in content: old_text=%r, path=%s",
                    old_text,
                    file_path,
                )
                return ToolErrorResult(self._not_found_message(old_text, content, path))
            
            count = content.count(old_text)
            if count > 1 and not replaceAll:
                logging.warning(
                    "old_text appears %d times in %s. Please provide more context.",
                    count,
                    file_path,
                )
                return ToolErrorResult(
                    f"old_text appears {count} times. Please provide more context to make it unique or set replaceAll=true."
                )

            if replaceAll:
                new_content = content.replace(old_text, new_text)
                replaced_count = count
            else:
                new_content = content.replace(old_text, new_text, 1)
                replaced_count = 1
            if new_content == content:
                return ToolErrorResult("No changes to apply.")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            diff = _trim_diff(
                _two_files_patch(str(file_path), str(file_path), content, new_content)
            )
            output = "\n".join([
                f"<path>{file_path}</path>",
                "<content>",
                f"Successfully edited {path} (replaced {replaced_count} occurrence{'s' if replaced_count != 1 else ''})",
                "</content>",
                "<diff>",
                diff,
                "</diff>",
            ])
            return ToolSuccessResult(output)
        except PermissionError as e:
            logging.error("Permission error: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Permission error: {str(e)}")
        except Exception as e:
            logging.error("Failed to edit file: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to edit file: {str(e)}")

    @staticmethod
    def _not_found_message(old_text: str, content: str, path: str) -> str:
        """Build a helpful error when old_text is not found."""
        lines = content.splitlines(keepends=True)
        old_lines = old_text.splitlines(keepends=True)
        window = len(old_lines)

        best_ratio, best_start = 0.0, 0
        for i in range(max(1, len(lines) - window + 1)):
            ratio = difflib.SequenceMatcher(None, old_lines, lines[i : i + window]).ratio()
            if ratio > best_ratio:
                best_ratio, best_start = ratio, i

        if best_ratio > 0.5:
            diff = "\n".join(difflib.unified_diff(
                old_lines, lines[best_start : best_start + window],
                fromfile="old_text (provided)", tofile=f"{path} (actual, line {best_start + 1})",
                lineterm="",
            ))
            return f"Error: old_text not found in {path}.\nBest match ({best_ratio:.0%} similar) at line {best_start + 1}:\n{diff}"
        return f"Error: old_text not found in {path}. No similar text found. Verify the file content."

class InsertFileTool(BaseTool):
    """Insert content into a file."""
    @property
    def name(self) -> str:
        return "insert_file"   
        
    @property
    def description(self) -> str:
        return """Insert content into a file at the given line position.

Usage:
- Provide the target file with `path`.
- `position` is optional; if omitted, content is inserted at the end of the file.
- If provided, `position` must be between 0 and the current line count.
- Returns a unified diff in `<diff>` to help verify the exact change."""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The full path to the file to insert content into."
                },
                "content": {
                    "type": "string",
                    "description": "The content to insert into the file."
                },
                "position": {
                    "type": "integer",
                    "description": "The line number to insert content at. If None, will insert at end of file."
                }
            },
            "required": ["path", "content"]
        }      

            
    async def execute(self, path: str, content: str, position: Optional[int] = None, **kwargs) -> ToolResult:
        try:
            if not path or not path.strip() or content is None:
                logging.error("Invalid parameters: path=%r, content=%r", path, content)
                return ToolErrorResult("Invalid parameters")     
            
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                logging.error("File not found: %s", file_path)
                return ToolErrorResult("File not found")
            
            if not file_path.is_file():
                logging.error("Not a file: %s", file_path)
                return ToolErrorResult("Not a file")

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                
            if position is None:
                position = len(lines)
            elif position < 0 or position > len(lines):
                logging.error(
                    "Invalid position: %d, file has %d lines", position, len(lines)
                )
                return ToolErrorResult(f"Invalid position: {position}, file has {len(lines)} lines")
            
            old_content = "".join(lines)
            insert_content = content if content.endswith("\n") else content + "\n"
            new_lines = lines[:position] + [insert_content] + lines[position:]
            new_content = "".join(new_lines)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            diff = _trim_diff(
                _two_files_patch(str(file_path), str(file_path), old_content, new_content)
            )
            output = "\n".join([
                f"<path>{file_path}</path>",
                "<content>",
                f"Successfully inserted {len(content)} bytes at line {position} in file {path}",
                "</content>",
                f"<position>{position}</position>",
                "<diff>",
                diff,
                "</diff>",
            ])
            return ToolSuccessResult(output)
            
        except Exception as e:
            logging.error("Failed to insert content: path=%r, error=%s", path, e)
            return ToolErrorResult(f"Failed to insert content: {str(e)}") 