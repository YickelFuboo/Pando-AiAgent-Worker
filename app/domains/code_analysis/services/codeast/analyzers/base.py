from abc import ABC, abstractmethod
from typing import Optional
from ..model import FileInfo


class LanguageAnalyzer(ABC):
    def __init__(self, base_path: str, file_path: str):
        """初始化基类"""
        self.base_path = base_path
        self.file_path = file_path
 
    @abstractmethod
    async def analyze_file(self) -> Optional[FileInfo]:
        """具体的文件分析逻辑"""
        pass