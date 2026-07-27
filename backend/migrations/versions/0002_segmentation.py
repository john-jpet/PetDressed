"""Segmentation artifacts and review state."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("garments", sa.Column("processed_object_key", sa.Text()))
    op.add_column("garments", sa.Column("preview_object_key", sa.Text()))
    op.add_column("garments", sa.Column("mask_object_key", sa.Text()))
    op.add_column("garments", sa.Column("mask_area_ratio", sa.Float()))
    op.add_column("garments", sa.Column("segmentation_confidence", sa.Float()))
    op.add_column("garments", sa.Column("segmentation_bbox", postgresql.JSONB()))
    op.add_column("garments", sa.Column("segmentation_model", sa.String(100)))
    op.add_column("garments", sa.Column("segmentation_model_version", sa.String(100)))
    op.add_column("garments", sa.Column("segmentation_accepted_at", sa.DateTime(timezone=True)))


def downgrade():
    for column in [
        "segmentation_accepted_at",
        "segmentation_model_version",
        "segmentation_model",
        "segmentation_bbox",
        "segmentation_confidence",
        "mask_area_ratio",
        "mask_object_key",
        "preview_object_key",
        "processed_object_key",
    ]:
        op.drop_column("garments", column)
