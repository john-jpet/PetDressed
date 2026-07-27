"""User planning and location settings."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_settings",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("city", sa.String(100)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("active_start_hour", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("active_end_hour", sa.Integer(), nullable=False, server_default="18"),
        sa.Column("repetition_tolerance", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("preferred_formality", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("accessory_usage", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("weather_strictness", sa.Integer(), nullable=False, server_default="2"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade():
    op.drop_table("user_settings")
