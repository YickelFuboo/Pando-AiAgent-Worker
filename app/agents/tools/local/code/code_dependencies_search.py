from typing import Any, Dict
from ...schemes import ToolErrorResult, ToolResult
from .code_similar_search import _BaseRepoCodeSearchTool
from app.domains.code_analysis.services.codegraph.graph_search import CodeGraphSearch


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
