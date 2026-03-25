"""add_code_analysis_tables

Revision ID: bf405fbed468
Revises: 
Create Date: 2026-03-25 11:48:57.159517

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "bf405fbed468"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repo_analysis_tasks",
        sa.Column("repo_id", sa.String(length=36), nullable=False, comment="代码仓ID"),
        sa.Column("scan_status", sa.String(length=32), nullable=False, comment="扫描任务状态"),
        sa.Column("last_error", sa.Text(), nullable=True, comment="最近错误"),
        sa.Column("last_scan_started_at", sa.DateTime(), nullable=True, comment="最近扫描开始时间"),
        sa.Column("last_scan_finished_at", sa.DateTime(), nullable=True, comment="最近扫描结束时间"),
        sa.Column("scan_heartbeat_at", sa.DateTime(), nullable=True, comment="扫描任务心跳时间"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["git_repositories.id"]),
        sa.PrimaryKeyConstraint("repo_id"),
    )
    op.create_index("idx_repo_analysis_task_scan_status", "repo_analysis_tasks", ["scan_status"], unique=False)
    op.create_index(op.f("ix_repo_analysis_tasks_scan_status"), "repo_analysis_tasks", ["scan_status"], unique=False)
    op.create_table(
        "repo_file_analysis_state",
        sa.Column("id", sa.String(length=36), nullable=False, comment="ID"),
        sa.Column("repo_id", sa.String(length=36), nullable=False, comment="代码仓ID"),
        sa.Column("file_path", sa.String(length=500), nullable=False, comment="相对路径"),
        sa.Column("status", sa.String(length=32), nullable=False, comment="状态"),
        sa.Column("last_error", sa.Text(), nullable=True, comment="最近错误"),
        sa.Column("last_started_at", sa.DateTime(), nullable=True, comment="最近开始分析时间"),
        sa.Column("last_finished_at", sa.DateTime(), nullable=True, comment="最近结束分析时间"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["git_repositories.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("repo_id", "file_path", name="uq_repo_file"),
    )
    op.create_index("idx_repo_file_analysis_dispatch", "repo_file_analysis_state", ["repo_id", "status"], unique=False)
    op.create_index("idx_repo_file_analysis_lookup", "repo_file_analysis_state", ["repo_id", "file_path"], unique=False)
    op.create_index(op.f("ix_repo_file_analysis_state_file_path"), "repo_file_analysis_state", ["file_path"], unique=False)
    op.create_index(op.f("ix_repo_file_analysis_state_repo_id"), "repo_file_analysis_state", ["repo_id"], unique=False)
    op.create_index(op.f("ix_repo_file_analysis_state_status"), "repo_file_analysis_state", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_repo_file_analysis_state_status"), table_name="repo_file_analysis_state")
    op.drop_index(op.f("ix_repo_file_analysis_state_repo_id"), table_name="repo_file_analysis_state")
    op.drop_index(op.f("ix_repo_file_analysis_state_file_path"), table_name="repo_file_analysis_state")
    op.drop_index("idx_repo_file_analysis_lookup", table_name="repo_file_analysis_state")
    op.drop_index("idx_repo_file_analysis_dispatch", table_name="repo_file_analysis_state")
    op.drop_table("repo_file_analysis_state")
    op.drop_index(op.f("ix_repo_analysis_tasks_scan_status"), table_name="repo_analysis_tasks")
    op.drop_index("idx_repo_analysis_task_scan_status", table_name="repo_analysis_tasks")
    op.drop_table("repo_analysis_tasks")
