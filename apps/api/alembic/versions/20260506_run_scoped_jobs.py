"""run scoped jobs

Revision ID: 20260506_run_scoped_jobs
Revises: f287d18c4a3f
Create Date: 2026-05-06 02:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260506_run_scoped_jobs"
down_revision: Union[str, None] = "f287d18c4a3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("scrape_run_jobs"):
        return
    op.create_table(
        "scrape_run_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("is_new", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["scrape_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "job_id", name="uq_scrape_run_job"),
    )
    with op.batch_alter_table("scrape_run_jobs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_scrape_run_jobs_job_id"), ["job_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_scrape_run_jobs_run_id"), ["run_id"], unique=False)
        batch_op.create_index("ix_scrape_run_jobs_run_id_job_id", ["run_id", "job_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("scrape_run_jobs", schema=None) as batch_op:
        batch_op.drop_index("ix_scrape_run_jobs_run_id_job_id")
        batch_op.drop_index(batch_op.f("ix_scrape_run_jobs_run_id"))
        batch_op.drop_index(batch_op.f("ix_scrape_run_jobs_job_id"))
    op.drop_table("scrape_run_jobs")