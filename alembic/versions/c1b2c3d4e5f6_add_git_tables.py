"""add_git_tables

Revision ID: c1b2c3d4e5f6
Revises: bf405fbed468
Create Date: 2026-03-25 00:00:00.000000
"""
from typing import Sequence,Union

from alembic import op
import sqlalchemy as sa


revision: str="c1b2c3d4e5f6"
down_revision: Union[str,None]="bf405fbed468"
branch_labels: Union[str,Sequence[str],None]=None
depends_on: Union[str,Sequence[str],None]=None


def upgrade() -> None:
    op.create_table(
        "git_repositories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("git_provider", sa.String(), nullable=False),
        sa.Column("repository_url", sa.String(), nullable=False),
        sa.Column("organization", sa.String(), nullable=False),
        sa.Column("repository_name", sa.String(), nullable=False),
        sa.Column("branch", sa.String(), server_default=sa.text("'main'"), nullable=True),
        sa.Column("description", sa.Text(), server_default=sa.text("''"), nullable=True),
        sa.Column("local_path", sa.String(), nullable=True),
        sa.Column("is_cloned", sa.Boolean(), server_default=sa.text("0"), nullable=True),
        sa.Column("last_sync_time", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )

    op.create_table(
        "git_authorities",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("access_token", sa.String(length=500), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
    )
    op.create_index("idx_user_provider","git_authorities",["user_id","provider"],unique=False)


def downgrade() -> None:
    op.drop_index("idx_user_provider",table_name="git_authorities")
    op.drop_table("git_authorities")
    op.drop_table("git_repositories")
