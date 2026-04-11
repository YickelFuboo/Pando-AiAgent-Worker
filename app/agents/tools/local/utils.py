import difflib
import re
from pathlib import Path
from typing import Any, Dict, List
from app.domains.code_analysis.services.lsp.lsp_service import CodeLSPService
from app.config.settings import PROJECT_BASE_DIR


# 文件写操作相关
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


def _is_code_agent_enabled(kwargs:Dict[str,Any])->bool:
    return kwargs.get("isCodeAgent") is True


def _pretty_diagnostic(item:Dict[str,Any])->str:
    severity_map={1:"ERROR",2:"WARN",3:"INFO",4:"HINT"}
    severity=severity_map.get(int(item.get("severity",1)),"ERROR")
    msg=str(item.get("message") or "").strip()
    rng=item.get("range") or {}
    start=(rng.get("start") or {}) if isinstance(rng,dict) else {}
    line=int(start.get("line",0))+1
    col=int(start.get("character",0))+1
    return f"{severity} [{line}:{col}] {msg}"


def _append_lsp_diagnostics(output:str,file_path:Path,diagnostics:Dict[str,List[Dict[str,Any]]])->str:
    current=str(file_path.resolve())
    current_items=[x for x in (diagnostics.get(current) or []) if int(x.get("severity",1))==1]
    if not current_items:
        return output
    limited=current_items[:20]
    output += f"\n\nLSP errors detected in this file, please fix:\n<diagnostics file=\"{current}\">"
    for item in limited:
        output += f"\n{_pretty_diagnostic(item)}"
    if len(current_items)>20:
        output += f"\n... and {len(current_items)-20} more"
    output += "\n</diagnostics>"
    return output

def not_found_message(old_text: str, content: str, path: str) -> str:
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

async def _touch_lsp_after_write(file_path:Path,kwargs:Dict[str,Any])->Dict[str,List[Dict[str,Any]]]:
    if not _is_code_agent_enabled(kwargs):
        return {}
    repo_id=str(kwargs.get("repo_id") or "").strip()
    if not repo_id:
        return {}
    try:
        target=str(file_path.resolve())
        available=await CodeLSPService.has_clients(target,repo_id=repo_id)
        if not available:
            return {}
        await CodeLSPService.touch_file(target,wait_for_diagnostics=True,repo_id=repo_id)
        return await CodeLSPService.diagnostics(target)
    except Exception:
        return {}

# todo相关
def todo_file(session_id : str)->Path:
    root = PROJECT_BASE_DIR/"data"/"session_todo"/session_id
    root.mkdir(parents=True, exist_ok=True)
    return root/"todo.json"