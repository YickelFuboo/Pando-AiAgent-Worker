import json
from typing import Any, Dict, List
from ...base import BaseTool
from ...schemes import ToolErrorResult, ToolResult, ToolSuccessResult
from app.domains.code_analysis.services.code_search_service import CodeSearchService


class _BaseRepoCodeSearchTool(BaseTool):
    def __init__(self, repo_id: str = ""):
        self._repo_id = (repo_id or "").strip()

    def _ensure_repo_id(self) -> str:
        if not self._repo_id:
            raise ValueError("repo_id is required in tool initialization")
        return self._repo_id

    @staticmethod
    def _wrap_output(data: Dict[str, Any]) -> ToolSuccessResult:
        output = "\n".join([
            "<result>",
            json.dumps(data, ensure_ascii=False, indent=2),
            "</result>",
        ])
        return ToolSuccessResult(output)


class CodeSimilarSearchTool(_BaseRepoCodeSearchTool):
    @property
    def name(self) -> str:
        return "code_similar_search"

    @property
    def description(self) -> str:
        return """Find code snippets similar to an input code fragment in the current repository.

Use this tool when:
- You already have a concrete code snippet and want implementations with similar logic.
- You need references to existing patterns before refactor or feature extension.
- You are debugging and want to compare with other places that solve similar problems.

Do not use this tool when:
- You only have topic words (use code_related_files_search instead).
- You need dependency direction between files (use code_dependencies_search instead)."""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code_text": {
                    "type": "string",
                    "description": "Code text used for similarity retrieval"
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Max result size. Default 10"
                }
            },
            "required": ["code_text"]
        }

    async def execute(self, code_text: str, top_k: int = 10, **kwargs: Any) -> ToolResult:
        k = int(top_k) if top_k is not None else 10
        if k < 1 or k > 100:
            return ToolErrorResult("top_k must be between 1 and 100")
        try:
            repo_id = self._ensure_repo_id()
            data = await CodeSearchService.search_similar_code(
                repo_id=repo_id,
                code_text=code_text or "",
                top_k=k,
            )
            return self._wrap_output(data)
        except ValueError as e:
            return ToolErrorResult(f"{self.name} failed: {str(e)}")
        except Exception as e:
            return ToolErrorResult(f"{self.name} failed: {str(e)}")