"""Metadata extraction and wardrobe."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TYPE garment_processing_status ADD VALUE IF NOT EXISTS 'extracting_metadata'")
    op.execute("ALTER TYPE garment_processing_status ADD VALUE IF NOT EXISTS 'metadata_review'")
    op.execute("ALTER TYPE garment_processing_status ADD VALUE IF NOT EXISTS 'ready'")
    availability = postgresql.ENUM(
        "available",
        "laundry",
        "unavailable",
        "packed",
        "archived",
        name="garment_availability",
        create_type=False,
    )
    category = postgresql.ENUM(
        "top",
        "bottom",
        "one_piece",
        "outerwear",
        "shoes",
        "accessory",
        name="garment_category",
        create_type=False,
    )
    source = postgresql.ENUM("model", "user", "default", name="metadata_source", create_type=False)
    availability.create(op.get_bind(), checkfirst=True)
    category.create(op.get_bind(), checkfirst=True)
    source.create(op.get_bind(), checkfirst=True)
    columns = [
        sa.Column("display_name", sa.String(100)),
        sa.Column("availability", availability, nullable=False, server_default="available"),
        sa.Column("planner_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("category", category),
        sa.Column("predicted_category", category),
        sa.Column("category_confidence", sa.Float()),
        sa.Column("category_source", source),
        sa.Column("subcategory", sa.String(64)),
        sa.Column("predicted_subcategory", sa.String(64)),
        sa.Column("formality", sa.Integer()),
        sa.Column("warmth", sa.Integer()),
        sa.Column("breathability", sa.Integer()),
        sa.Column("water_resistance", sa.Integer()),
        sa.Column("pattern", sa.String(32)),
        sa.Column("embedding", Vector(512)),
        sa.Column("embedding_model", sa.String(100)),
        sa.Column("embedding_model_version", sa.String(100)),
        sa.Column("prompt_set_version", sa.String(50)),
        sa.Column("metadata_confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("wear_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_worn_at", sa.DateTime(timezone=True)),
    ]
    for column in columns:
        op.add_column("garments", column)
    op.create_index("ix_garments_user_category", "garments", ["user_id", "category"])
    op.create_index("ix_garments_user_availability", "garments", ["user_id", "availability"])
    op.create_table(
        "garment_colors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "garment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("garments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("hex_value", sa.String(7), nullable=False),
        sa.Column("lab_l", sa.Float(), nullable=False),
        sa.Column("lab_a", sa.Float(), nullable=False),
        sa.Column("lab_b", sa.Float(), nullable=False),
        sa.Column("proportion", sa.Float(), nullable=False),
        sa.UniqueConstraint("garment_id", "rank"),
    )
    op.create_index("ix_garment_colors_garment_id", "garment_colors", ["garment_id"])
    op.create_table(
        "garment_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "garment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("garments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attribute_name", sa.String(64), nullable=False),
        sa.Column("predicted_value", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(100)),
        sa.Column("prompt_set_version", sa.String(50)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_garment_predictions_garment_id", "garment_predictions", ["garment_id"])


def downgrade():
    op.drop_table("garment_predictions")
    op.drop_table("garment_colors")
    for column in [
        "last_worn_at",
        "wear_count",
        "metadata_confirmed_at",
        "prompt_set_version",
        "embedding_model_version",
        "embedding_model",
        "embedding",
        "pattern",
        "water_resistance",
        "breathability",
        "warmth",
        "formality",
        "predicted_subcategory",
        "subcategory",
        "category_source",
        "category_confidence",
        "predicted_category",
        "category",
        "planner_enabled",
        "availability",
        "display_name",
    ]:
        op.drop_column("garments", column)
    op.execute("DROP TYPE metadata_source")
    op.execute("DROP TYPE garment_category")
    op.execute("DROP TYPE garment_availability")
