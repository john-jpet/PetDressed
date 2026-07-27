"""Garment season suitability."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "garment_seasons",
        sa.Column(
            "garment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("garments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("season", sa.String(16), primary_key=True),
        sa.Column("suitability", sa.Integer(), nullable=False),
        sa.CheckConstraint("season IN ('spring','summer','fall','winter')"),
        sa.CheckConstraint("suitability BETWEEN 0 AND 5"),
    )


def downgrade():
    op.drop_table("garment_seasons")
