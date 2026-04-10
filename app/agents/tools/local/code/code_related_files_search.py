from typing import Any, Dict, List
from ...schemes import ToolErrorResult, ToolResult
from .code_similar_search import _BaseRepoCodeSearchTool
from app.domains.code_analysis.services.code_search_service import CodeSearchService
from app.domains.code_analysis.services.codegraph.graph_search import CodeGraphSearch


class CodeRelatedFilesSearchTool(_BaseRepoCodeSearchTool):
    @property
    def name(self) -> str:
        return "code_related_files_search"

    @property
    def description(self) -> str:
        return """Find related files and snippets by keywords in the current repository.

Use this tool when:
- You only know business/domain terms, API names, class names, or capability keywords.
- You need an entry-point file list before opening or editing code.
- You want broad discovery coverage around a feature area.

Do not use this tool when:
- You already have a concrete code snippet to match (use code_similar_search instead).
- You need explicit dependency paths between files (use code_dependencies_search instead)."""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords used for related files retrieval"
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Max result size. Default 10"
                }
            },
            "required": ["keywords"]
        }

    async def execute(self, keywords: List[str], top_k: int = 10, **kwargs: Any) -> ToolResult:
        k = int(top_k) if top_k is not None else 10
        if k < 1 or k > 100:
            return ToolErrorResult("top_k must be between 1 and 100")
        try:
            repo_id = self._ensure_repo_id()
            kw = [str(x).strip() for x in (keywords or []) if str(x).strip()]
            if not kw:
                return ToolErrorResult("keywords is required")
            data = await CodeSearchService.search_related_files(
                repo_id=repo_id,
                keywords=kw,
                top_k=k,
            )
            return self._wrap_output(data)
        except ValueError as e:
            return ToolErrorResult(f"{self.name} failed: {str(e)}")
        except Exception as e:
            return ToolErrorResult(f"{self.name} failed: {str(e)}")
