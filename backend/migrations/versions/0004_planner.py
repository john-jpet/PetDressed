"""Planner persistence and feedback."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outfit_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("solver_version", sa.String(50), nullable=False),
        sa.Column("scoring_version", sa.String(50), nullable=False),
        sa.Column("weather_provider", sa.String(50)),
        sa.Column("weather_generated_at", sa.DateTime(timezone=True)),
        sa.Column("solve_time_ms", sa.Integer()),
        sa.Column("objective_value", sa.BigInteger()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_outfit_plans_user_id", "outfit_plans", ["user_id"])
    op.create_table(
        "outfit_plan_days",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outfit_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("weather_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("score_breakdown", postgresql.JSONB(), nullable=False),
        sa.Column("explanations", postgresql.JSONB(), nullable=False),
        sa.Column("relaxed_constraints", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("plan_id", "plan_date"),
    )
    op.create_table(
        "outfit_plan_garments",
        sa.Column(
            "plan_day_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outfit_plan_days.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "garment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("garments.id"),
            primary_key=True,
        ),
        sa.Column(
            "category", postgresql.ENUM(name="garment_category", create_type=False), nullable=False
        ),
        sa.Column("is_user_locked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "outfit_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outfit_plans.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "plan_day_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("outfit_plan_days.id", ondelete="SET NULL"),
        ),
        sa.Column("feedback_type", sa.String(32), nullable=False),
        sa.Column("garment_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("metadata", postgresql.JSONB()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_outfit_feedback_user_id", "outfit_feedback", ["user_id"])


def downgrade():
    op.drop_table("outfit_feedback")
    op.drop_table("outfit_plan_garments")
    op.drop_table("outfit_plan_days")
    op.drop_table("outfit_plans")
