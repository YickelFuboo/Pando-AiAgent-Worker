import asyncio
import hashlib
import re
from typing import Dict,List,Optional,Tuple
from app.domains.code_analysis.constants import line_chunk_space_name,symbol_summary_space_name
from app.domains.code_analysis.models.analysis_status import RepoAnalysisType as AnalysisType
from app.domains.code_analysis.services.codeast.model import FileInfo
from app.domains.code_analysis.services.codechunk.code_chunk import LineTextChunk
from app.domains.code_analysis.services.codesummary.code_summary import CodeSummary
from app.domains.code_analysis.services.codesummary.model import ContentType
from app.infrastructure.llms import embedding_factory
from app.infrastructure.vector_store import VECTOR_STORE_CONN


_TRIVIAL_SYM_NAME = re.compile(r"^(get|set)[A-Z_][A-Za-z0-9_]*$")
_TRIVIAL_GO_ACCESSOR = re.compile(r"^(Get|Set|Is)[A-Z][A-Za-z0-9_]*$")
_TRIVIAL_JAVA_CPP_ACCESSOR = re.compile(r"^(get|set|is)[A-Z][A-Za-z0-9_]*$")
_TRIVIAL_GO_SINGLE_RETURN = re.compile(r"(?ms)^\s*return\s+.+\s*$")
_TRIVIAL_JAVA_CPP_SINGLE_RETURN = re.compile(r"(?ms)^\s*return\s+[^;]+;\s*$")
_TRIVIAL_JAVA_CPP_SINGLE_ASSIGN = re.compile(r"(?ms)^\s*(this\.)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*[^;]+;\s*$")


class CodeVectorService:
    """代码分析结果向量化与落库：行块向量与符号（函数/类/方法）摘要向量。"""

    @staticmethod
    async def vectorize_and_store_line_chunks(repo_id: str, rel_file_path: str, chunks: List[LineTextChunk]) -> None:
        """将行切片文本批量嵌入向量，按仓与文件路径幂等写入向量库（先删后插）。"""
        if not chunks:
            return
        texts = [c.text for c in chunks]
        vectors = await CodeVectorService._embed_texts(texts)
        if not vectors:
            raise RuntimeError("line chunk向量化失败")
            
        dim = len(vectors[0])
        vector_field = f"q_{dim}_vec"
        space_name = line_chunk_space_name(repo_id, dim)
        await VECTOR_STORE_CONN.create_space(space_name, dim)
        await VECTOR_STORE_CONN.delete_records(
            space_name,
            {
                "repo_id": repo_id,
                "file_path": rel_file_path,
                "analysis_type": AnalysisType.LINE_CHUNK_VECTOR.value,
            },
        )
        records: List[Dict[str, object]] = []
        for idx, c in enumerate(chunks):
            stable_id = CodeVectorService._build_stable_id(
                repo_id=repo_id,
                file_path=rel_file_path,
                analysis_type=AnalysisType.LINE_CHUNK_VECTOR.value,
                start_line=c.start_line,
                end_line=c.end_line,
                extra=str(idx),
            )
            records.append(
                {
                    "id": stable_id,
                    "repo_id": repo_id,
                    "file_path": rel_file_path,
                    "analysis_type": AnalysisType.LINE_CHUNK_VECTOR.value,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "chunk_index": idx,
                    "content": c.text,
                    vector_field: vectors[idx],
                }
            )
        failed_ids = await VECTOR_STORE_CONN.insert_records(space_name, records)
        if failed_ids:
            raise RuntimeError(f"line chunk写入向量失败: {len(failed_ids)}")

    @staticmethod
    async def vectorize_and_store_symbol_summaries(
        repo_id: str,
        rel_file_path: str,
        file_info: Optional[FileInfo],
    ) -> None:
        """基于 AST 文件信息抽取函数/类/方法，经 LLM 摘要后嵌入并写入符号摘要向量空间。"""
        if not file_info:
            return
        
        symbols: List[Tuple[str, str, int, int, str, ContentType]] = []
        language = CodeVectorService._normalize_language(file_info.language)
        for fn in file_info.functions or []:
            name = fn.name or ""
            src = (fn.source_code or "").strip()
            if not src:
                continue

            if CodeVectorService._should_skip_symbol(name,src,language):
                continue

            symbols.append(
                (
                    "function",
                    name,
                    fn.start_line or 1,
                    fn.end_line or max(fn.start_line or 1, 1),
                    src,
                    ContentType.FUNCTION,
                )
            )
        
        for clz in file_info.classes or []:
            src = (clz.source_code or "").strip()
            if not src:
                continue
            symbols.append(
                (
                    "class",
                    clz.name,
                    clz.start_line or 1,
                    clz.end_line or max(clz.start_line or 1, 1),
                    src,
                    ContentType.CLASS,
                )
            )
            for method in clz.methods or []:
                mname = method.name or ""
                msrc = (method.source_code or "").strip()
                if not msrc:
                    continue

                if CodeVectorService._should_skip_symbol(mname,msrc,language):
                    continue

                symbols.append(
                    (
                        "method",
                        f"{clz.name}.{mname}",
                        method.start_line or 1,
                        method.end_line or max(method.start_line or 1, 1),
                        msrc,
                        ContentType.FUNCTION,
                    )
                )
        if not symbols:
            return
        
        # 生成符号摘要
        sem = asyncio.Semaphore(4)
        async def one_summary(src: str, ct: ContentType) -> str:
            """对单个符号源码调用 LLM 摘要（受信号量限制并发）。"""
            async with sem:
                return await CodeSummary.llm_summarize(src, ct)

        summaries = await asyncio.gather(*[one_summary(src, ct) for _, _, _, _, src, ct in symbols])
        texts: List[str] = []
        for i, s in enumerate(summaries):
            t = (s or "").strip()
            if not t:
                t = CodeVectorService._fallback_summary_from_source(symbols[i][4], symbols[i][5])  
            texts.append(t)
        
        # 向量化符号摘要
        vectors = await CodeVectorService._embed_texts(texts)
        if not vectors:
            raise RuntimeError("symbol summary向量化失败")
        dim = len(vectors[0])
        vector_field = f"q_{dim}_vec"
        space_name = symbol_summary_space_name(repo_id, dim)
        await VECTOR_STORE_CONN.create_space(space_name, dim)
        await VECTOR_STORE_CONN.delete_records(
            space_name,
            {
                "repo_id": repo_id,
                "file_path": rel_file_path,
                "analysis_type": AnalysisType.SYMBOL_SUMMARY_VECTOR.value,
            },
        )
        records: List[Dict[str, object]] = []
        for idx, item in enumerate(symbols):
            symbol_kind, symbol_name, start_line, end_line, _, _ = item
            summary = texts[idx]
            stable_id = CodeVectorService._build_stable_id(
                repo_id=repo_id,
                file_path=rel_file_path,
                analysis_type=AnalysisType.SYMBOL_SUMMARY_VECTOR.value,
                start_line=start_line,
                end_line=end_line,
                extra=f"{symbol_kind}:{symbol_name}:{idx}",
            )
            records.append(
                {
                    "id": stable_id,
                    "repo_id": repo_id,
                    "file_path": rel_file_path,
                    "analysis_type": AnalysisType.SYMBOL_SUMMARY_VECTOR.value,
                    "symbol_kind": symbol_kind,
                    "symbol_name": symbol_name,
                    "start_line": start_line,
                    "end_line": end_line,
                    "summary": summary,
                    vector_field: vectors[idx],
                }
            )
        failed_ids = await VECTOR_STORE_CONN.insert_records(space_name, records)
        if failed_ids:
            raise RuntimeError(f"symbol summary写入向量失败: {len(failed_ids)}")

    @staticmethod
    def _normalize_language(language: Optional[str]) -> str:
        """归一化语言标识，避免大小写/空值影响过滤规则选择。"""
        return (language or "").strip().lower()

    @staticmethod
    def _non_comment_lines(src:str,language:str) -> List[str]:
        """提取去除空白和常见注释行后的代码行。"""
        lines = [ln for ln in src.splitlines() if ln.strip()]
        out: List[str] = []
        for ln in lines:
            s = ln.strip()
            if language == "python" and s.startswith("#"):
                continue
            if language in {"java","go","cpp","c"} and (s.startswith("//") or s.startswith("/*") or s.startswith("*") or s.startswith("*/")):
                continue
            out.append(ln)
        return out

    @staticmethod
    def _should_skip_symbol(name:str,src:str,language:str) -> bool:
        """按语言过滤低信息度符号函数（getter/setter/仅返回或仅赋值的小函数）。"""
        lines = CodeVectorService._non_comment_lines(src,language)
        if len(lines) > 8:
            return False
        body = "\n".join(lines)
        lowered = name.lower()

        if language == "python":
            if _TRIVIAL_SYM_NAME.match(name) or lowered.startswith("get_") or lowered.startswith("set_") or lowered.startswith("is_"):
                if len(lines) <= 4 and "return" in body and body.count("def ") <= 1:
                    return True
            return False

        if language == "go":
            if _TRIVIAL_GO_ACCESSOR.match(name) and len(lines) <= 5:
                non_sig = [it.strip() for it in lines if not it.strip().startswith("func ")]
                if len(non_sig) <= 2:
                    joined = " ".join(non_sig)
                    if _TRIVIAL_GO_SINGLE_RETURN.search(joined) or "=" in joined:
                        return True
            return False

        if language in {"java","cpp","c"}:
            if _TRIVIAL_JAVA_CPP_ACCESSOR.match(name) and len(lines) <= 7:
                non_sig = [it.strip() for it in lines if "(" not in it or ")" not in it]
                core = [it for it in non_sig if it not in {"{","}","};"}]
                if len(core) <= 2:
                    joined = " ".join(core)
                    if _TRIVIAL_JAVA_CPP_SINGLE_RETURN.search(joined) or _TRIVIAL_JAVA_CPP_SINGLE_ASSIGN.search(joined):
                        return True
            return False

        return False

    @staticmethod
    def _fallback_summary_from_source(source_code: str, ct: ContentType) -> str:
        """LLM 摘要为空时，用源码前几行拼成短文本作为回退描述。"""
        lines = [ln.strip() for ln in (source_code or "").splitlines() if ln.strip()]
        preview = " ".join(lines[:4])[:280]
        if ct == ContentType.CLASS:
            return f"类型摘要（回退）。内容预览: {preview}"
        return f"函数摘要（回退）。内容预览: {preview}"

    @staticmethod
    async def _embed_texts(texts: List[str]) -> List[List[float]]:
        """调用全局 embedding 模型将字符串列表编码为向量列表。"""
        model = embedding_factory.create_model()
        if not model:
            raise RuntimeError("embedding模型创建失败")
        vectors, _ = await model.encode(texts)
        if vectors is None or len(vectors) == 0:
            return []
        return [v.tolist() for v in vectors]

    @staticmethod
    def _build_stable_id(
        repo_id: str,
        file_path: str,
        analysis_type: str,
        start_line: int,
        end_line: int,
        extra: str = "",
    ) -> str:
        """用仓、路径、分析类型、行号与附加键生成 SHA1 稳定记录 ID，便于幂等更新。"""
        raw = f"{repo_id}|{file_path}|{analysis_type}|{start_line}|{end_line}|{extra}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
