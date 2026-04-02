import json
from pathlib import Path
from typing import Any,Dict,List
from app.agents.tools.base import BaseTool
from app.agents.tools.schemes import ToolErrorResult,ToolResult,ToolSuccessResult
from app.domains.code_analysis.services.lsp.lsp_service import CodeLSPService

_OPERATIONS={
    "goToDefinition",
    "findReferences",
    "hover",
    "documentSymbol",
    "workspaceSymbol",
    "goToImplementation",
    "prepareCallHierarchy",
    "incomingCalls",
    "outgoingCalls",
}


class LspTool(BaseTool):
    def __init__(self,repo_id:str="",**kwargs:Any):
        self._repo_id=(repo_id or "").strip()

    @property
    def name(self)->str:
        return "lsp"

    @property
    def description(self)->str:
        return """Interact with Language Server Protocol (LSP) servers to get code intelligence features.

Supported operations:
- goToDefinition: Find where a symbol is defined
- findReferences: Find all references to a symbol
- hover: Get hover information (documentation, type info) for a symbol
- documentSymbol: Get all symbols (functions, classes, variables) in a document
- workspaceSymbol: Search for symbols across the entire workspace
- goToImplementation: Find implementations of an interface or abstract method
- prepareCallHierarchy: Get call hierarchy item at a position (functions/methods)
- incomingCalls: Find all functions/methods that call the function at a position
- outgoingCalls: Find all functions/methods called by the function at a position

Use this tool when:
- You need symbol-level navigation instead of text search.
- You need precise references/definitions/implementations for a code element.
- You need structural code understanding via symbols or call hierarchy.

Note:
- LSP servers must be configured for the file type.
- If no server is available, an error is returned."""

    @property
    def parameters(self)->Dict[str,Any]:
        return {
            "type":"object",
            "properties":{
                "operation":{
                    "type":"string",
                    "enum":sorted(_OPERATIONS),
                    "description":"The LSP operation to perform",
                },
                "filePath":{
                    "type":"string",
                    "description":"Absolute path to the file",
                },
                "line":{
                    "type":"integer",
                    "minimum":1,
                    "description":"1-based line number",
                },
                "character":{
                    "type":"integer",
                    "minimum":1,
                    "description":"1-based character offset",
                },
                "query":{
                    "type":"string",
                    "description":"Optional query for workspaceSymbol, default empty string",
                },
            },
            "required":["operation","filePath"],
        }

    def _resolve_file_path(self,file_path:str)->Path:
        p=Path(file_path).expanduser()
        if not p.is_absolute():
            raise ValueError("filePath must be an absolute path")
        return p.resolve()

    def _require_position(self,line:Any,character:Any)->tuple[int,int] | None:
        if line is None or character is None:
            return None
        l=int(line)
        c=int(character)
        if l<1 or c<1:
            raise ValueError("line and character must be >= 1")
        return l,c

    async def _call_operation(
        self,
        operation:str,
        file_path:str,
        line:int|None,
        character:int|None,
        query:str,
    )->List[Any]:
        if operation=="goToDefinition":
            if line is None or character is None:
                raise ValueError("line and character are required for goToDefinition")
            return await CodeLSPService.definition(file_path,line,character,repo_id=self._repo_id)
        if operation=="findReferences":
            if line is None or character is None:
                raise ValueError("line and character are required for findReferences")
            return await CodeLSPService.references(file_path,line,character,repo_id=self._repo_id)
        if operation=="hover":
            if line is None or character is None:
                raise ValueError("line and character are required for hover")
            return await CodeLSPService.hover(file_path,line,character,repo_id=self._repo_id)
        if operation=="documentSymbol":
            return await CodeLSPService.document_symbol(file_path,repo_id=self._repo_id)
        if operation=="workspaceSymbol":
            return await CodeLSPService.workspace_symbol(query or "",repo_id=self._repo_id)
        if operation=="goToImplementation":
            if line is None or character is None:
                raise ValueError("line and character are required for goToImplementation")
            return await CodeLSPService.implementation(file_path,line,character,repo_id=self._repo_id)
        if operation=="prepareCallHierarchy":
            if line is None or character is None:
                raise ValueError("line and character are required for prepareCallHierarchy")
            return await CodeLSPService.prepare_call_hierarchy(file_path,line,character,repo_id=self._repo_id)
        if operation=="incomingCalls":
            if line is None or character is None:
                raise ValueError("line and character are required for incomingCalls")
            return await CodeLSPService.incoming_calls(file_path,line,character,repo_id=self._repo_id)
        if operation=="outgoingCalls":
            if line is None or character is None:
                raise ValueError("line and character are required for outgoingCalls")
            return await CodeLSPService.outgoing_calls(file_path,line,character,repo_id=self._repo_id)
        raise ValueError(f"unsupported operation: {operation}")

    async def execute(
        self,
        operation:str,
        filePath:str,
        line:int|None=None,
        character:int|None=None,
        query:str="",
        **kwargs:Any,
    )->ToolResult:
        try:
            op=(operation or "").strip()
            if op not in _OPERATIONS:
                return ToolErrorResult(f"operation must be one of: {', '.join(sorted(_OPERATIONS))}")
            if not self._repo_id:
                return ToolErrorResult("repo_id is required for lsp tool")
            target=self._resolve_file_path(filePath)
            if not target.is_file():
                return ToolErrorResult(f"File not found: {target}")
            available=await CodeLSPService.has_clients(str(target),repo_id=self._repo_id)
            if not available:
                return ToolErrorResult("No LSP server available for this file type.")
            
            pos=self._require_position(line,character)
            line_num=pos[0] if pos else None
            char_num=pos[1] if pos else None
            await CodeLSPService.touch_file(str(target),wait_for_diagnostics=True,repo_id=self._repo_id)
            result=await self._call_operation(
                operation=op,
                file_path=str(target),
                line=line_num,
                character=char_num,
                query=(query or "").strip(),
            )
            output="No results found for "+op if not result else json.dumps(result,ensure_ascii=False,indent=2)
            return ToolSuccessResult(output)
        except ValueError as e:
            return ToolErrorResult(str(e))
        except Exception as e:
            return ToolErrorResult(f"lsp failed: {str(e)}")

