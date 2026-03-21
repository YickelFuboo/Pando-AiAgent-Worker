import uuid
from sqlalchemy import Column,String,Text,Integer,Boolean,ForeignKey,Index,DateTime,func
from sqlalchemy.orm import relationship

from app.infrastructure.database import Base


class RepoCodeChunks(Base):
    """代码片段切片数据表"""
    __tablename__ = "repo_code_chunks"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="ID")
    repo_id = Column(String(36), ForeignKey("git_repositories.id"), nullable=False, index=True, comment="代码仓ID")
    source_code = Column(Text, nullable=False, comment="源码内容")
    file_path = Column(String(500), nullable=False, comment="所属文件路径")
    start_line = Column(Integer, nullable=False, comment="起始行号")
    end_line = Column(Integer, nullable=False, comment="结束行号")
    summary = Column(Text, nullable=True, comment="功能说明")
    is_summarized = Column(Boolean, default=False, index=True, comment="是否已生成功能说明")
    is_source_vectorized = Column(Boolean, default=False, index=True, comment="源码向量化状态")
    is_summary_vectorized = Column(Boolean, default=False, index=True, comment="功能说明向量化状态")

    created_at = Column(DateTime,nullable=False,server_default=func.now())
    updated_at = Column(DateTime,nullable=False,server_default=func.now(),onupdate=func.now())
    
    __table_args__ = (
        Index('idx_repo_id', 'repo_id'),
        Index('idx_file_path', 'file_path'),
        Index('idx_summarized', 'is_summarized'),
        Index('idx_source_vectorized', 'is_source_vectorized'),
        Index('idx_summary_vectorized', 'is_summary_vectorized'),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "source_code": self.source_code,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "summary": self.summary,
            "is_summarized": self.is_summarized,
            "is_source_vectorized": self.is_source_vectorized,
            "is_summary_vectorized": self.is_summary_vectorized,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RepoFunctions(Base):
    """函数数据表（用于存储函数、方法）"""
    __tablename__ = "repo_function_data"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="ID")
    repo_id = Column(String(36), ForeignKey("git_repositories.id"), nullable=False, index=True, comment="代码仓ID")
    source_code = Column(Text, nullable=False, comment="源码内容")
    file_path = Column(String(500), nullable=False, comment="所属文件路径")
    start_line = Column(Integer, nullable=False, comment="起始行号")
    end_line = Column(Integer, nullable=False, comment="结束行号")
    function_name = Column(String(200), nullable=True, comment="函数名")
    function_signature = Column(String(500), nullable=True, comment="函数签名")
    summary = Column(Text, nullable=True, comment="功能说明")
    is_summarized = Column(Boolean, default=False, index=True, comment="是否已生成功能说明")
    is_vectorized = Column(Boolean, default=False, index=True, comment="向量化状态")

    created_at = Column(DateTime,nullable=False,server_default=func.now())
    updated_at = Column(DateTime,nullable=False,server_default=func.now(),onupdate=func.now())
    
    __table_args__ = (
        Index('idx_repo_id', 'repo_id'),
        Index('idx_file_path', 'file_path'),
        Index('idx_function_name', 'function_name'),
        Index('idx_summarized', 'is_summarized'),
        Index('idx_vectorized', 'is_vectorized'),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "source_code": self.source_code,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "function_name": self.function_name,
            "function_signature": self.function_signature,
            "summary": self.summary,
            "is_summarized": self.is_summarized,
            "is_vectorized": self.is_vectorized,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RepoClasses(Base):
    """类数据表（用于存储类、结构）"""
    __tablename__ = "repo_class_data"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="ID")
    repo_id = Column(String(36), ForeignKey("git_repositories.id"), nullable=False, index=True, comment="代码仓ID")
    source_code = Column(Text, nullable=False, comment="源码内容")
    file_path = Column(String(500), nullable=False, comment="所属文件路径")
    start_line = Column(Integer, nullable=False, comment="起始行号")
    end_line = Column(Integer, nullable=False, comment="结束行号")
    class_name = Column(String(200), nullable=True, comment="类名")
    class_type = Column(String(50), nullable=True, comment="类类型（class/struct/interface）")
    summary = Column(Text, nullable=True, comment="功能说明")
    is_summarized = Column(Boolean, default=False, index=True, comment="是否已生成功能说明")
    is_vectorized = Column(Boolean, default=False, index=True, comment="向量化状态")

    created_at = Column(DateTime,nullable=False,server_default=func.now())
    updated_at = Column(DateTime,nullable=False,server_default=func.now(),onupdate=func.now())
    
    __table_args__ = (
        Index('idx_repo_id', 'repo_id'),
        Index('idx_file_path', 'file_path'),
        Index('idx_class_name', 'class_name'),
        Index('idx_summarized', 'is_summarized'),
        Index('idx_vectorized', 'is_vectorized'),
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "source_code": self.source_code,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "class_name": self.class_name,
            "class_type": self.class_type,
            "summary": self.summary,
            "is_summarized": self.is_summarized,
            "is_vectorized": self.is_vectorized,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

