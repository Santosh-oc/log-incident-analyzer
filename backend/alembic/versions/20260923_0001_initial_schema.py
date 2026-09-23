"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "log_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("minio_bucket", sa.String(), nullable=False),
        sa.Column("minio_object_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("total_lines", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("parsed_events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unparsed_lines", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unparsed_samples", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("time_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "file_id",
            sa.Uuid(),
            sa.ForeignKey("log_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("service", sa.String(), nullable=False),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column("sample_message", sa.Text(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analysis_status", sa.String(), nullable=False, server_default="NOT_ANALYZED"),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("category", sa.String(), nullable=True),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("likely_cause", sa.Text(), nullable=True),
        sa.Column("evidence_lines", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("analysis_error", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_incidents_file_id", "incidents", ["file_id"])
    op.create_table(
        "log_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "file_id",
            sa.Uuid(),
            sa.ForeignKey("log_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "incident_id",
            sa.Uuid(),
            sa.ForeignKey("incidents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("service", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.String(), nullable=True),
    )
    op.create_index("ix_log_events_file_id", "log_events", ["file_id"])
    op.create_index("ix_log_events_incident_id", "log_events", ["incident_id"])
    op.create_index("ix_log_events_timestamp", "log_events", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_log_events_timestamp", table_name="log_events")
    op.drop_index("ix_log_events_incident_id", table_name="log_events")
    op.drop_index("ix_log_events_file_id", table_name="log_events")
    op.drop_table("log_events")
    op.drop_index("ix_incidents_file_id", table_name="incidents")
    op.drop_table("incidents")
    op.drop_table("log_files")
