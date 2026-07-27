"""Upload foundation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    status = postgresql.ENUM(
        "draft",
        "uploading",
        "uploaded",
        "queued",
        "segmenting",
        "segmentation_review",
        "failed",
        "archived",
        name="garment_processing_status",
        create_type=False,
    )
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "garments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("processing_status", status, nullable=False),
        sa.Column("processing_revision", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("original_content_type", sa.String(64), nullable=False),
        sa.Column("original_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("original_object_key", sa.Text(), nullable=False),
        sa.Column("processing_error_code", sa.String(64)),
        sa.Column("processing_error_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_garments_user_id", "garments", ["user_id"])


def downgrade():
    op.drop_table("garments")
    op.execute("DROP TYPE garment_processing_status")
