import json
from typing import Any, Dict, List
from app.agents.tools.base import BaseTool
from app.agents.tools.schemes import ToolErrorResult, ToolResult, ToolSuccessResult
from app.domains.code_analysis.services.code_search_service import CodeSearchService
from app.domains.code_analysis.services.codegraph.graph_search import CodeGraphSearch


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


class CodeDependenciesSearchTool(_BaseRepoCodeSearchTool):
    @property
    def name(self) -> str:
        return "code_dependencies_search"

    @property
    def description(self) -> str:
        return """Inspect dependency relationships for a target file in the current repository.

Use this tool when:
- You want to know which files depend on a file (impact analysis before change).
- You want to know which files the target depends on (understand coupling and layering).
- You need dependency evidence for safe refactor planning.

Do not use this tool when:
- You need semantic/code-pattern similarity (use code_similar_search instead).
- You need broad keyword-based discovery (use code_related_files_search instead)."""

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Target file path"
                },
                "dependency_direction": {
                    "type": "string",
                    "enum": ["dependents", "dependencies"],
                    "description": "dependents=files that depend on file_path, dependencies=files that file_path depends on"
                }
            },
            "required": ["file_path"]
        }

    async def execute(self, file_path: str, dependency_direction: str = "dependents", **kwargs: Any) -> ToolResult:
        try:
            repo_id = self._ensure_repo_id()
            target = (file_path or "").strip()
            if not target:
                return ToolErrorResult("file_path is required")
            direction = dependency_direction or "dependents"
            if direction not in {"dependents", "dependencies"}:
                return ToolErrorResult("dependency_direction must be dependents or dependencies")
            with CodeGraphSearch() as graph:
                if direction == "dependents":
                    res = await graph.query_dependents_of_file(repo_id, target)
                else:
                    res = await graph.query_dependented_of_file(repo_id, target)
            if not res.result:
                return ToolErrorResult(res.message or "Failed to query code dependencies")
            data = {
                "repo_id": repo_id,
                "file_path": target,
                "direction": direction,
                **(res.content or {}),
            }
            return self._wrap_output(data)
        except ValueError as e:
            return ToolErrorResult(f"{self.name} failed: {str(e)}")
        except Exception as e:
            return ToolErrorResult(f"{self.name} failed: {str(e)}")
