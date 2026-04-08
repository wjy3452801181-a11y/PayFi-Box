"""step2 core schema

Revision ID: 20260329_000001
Revises:
Create Date: 2026-03-29 00:00:01.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260329_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_organizations_created_at"),
        "organizations",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_created_at"), "users", ["created_at"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "beneficiaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("wallet_address", sa.String(length=128), nullable=True),
        sa.Column("bank_account_mock", sa.String(length=128), nullable=True),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("is_blacklisted", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_beneficiaries_created_at"),
        "beneficiaries",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "conversation_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_conversation_sessions_created_at"),
        "conversation_sessions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_sessions_user_id"),
        "conversation_sessions",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "command_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("parsed_intent_json", sa.JSON(), nullable=True),
        sa.Column("tool_calls_json", sa.JSON(), nullable=True),
        sa.Column("final_status", sa.String(length=16), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_command_executions_created_at"),
        "command_executions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_command_executions_final_status"),
        "command_executions",
        ["final_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_command_executions_session_id"),
        "command_executions",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_command_executions_trace_id"),
        "command_executions",
        ["trace_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_command_executions_user_id"),
        "command_executions",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "payment_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("beneficiary_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_command_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("intent_source_text", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("execution_mode", sa.String(length=16), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["beneficiary_id"], ["beneficiaries.id"]),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["source_command_id"], ["command_executions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_payment_orders_created_at"),
        "payment_orders",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_orders_status"),
        "payment_orders",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_orders_beneficiary_id"),
        "payment_orders",
        ["beneficiary_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_orders_organization_id"),
        "payment_orders",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_orders_reference"),
        "payment_orders",
        ["reference"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_orders_source_command_id"),
        "payment_orders",
        ["source_command_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_orders_user_id"),
        "payment_orders",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_json", sa.JSON(), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_audit_logs_actor_user_id"),
        "audit_logs",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(op.f("ix_audit_logs_trace_id"), "audit_logs", ["trace_id"], unique=False)

    op.create_table(
        "payment_quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fee", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("fx_rate", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("route", sa.String(length=128), nullable=False),
        sa.Column("eta_text", sa.String(length=128), nullable=True),
        sa.Column("eta_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_payment_quotes_created_at"),
        "payment_quotes",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_quotes_payment_order_id"),
        "payment_quotes",
        ["payment_order_id"],
        unique=False,
    )

    op.create_table(
        "payment_splits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_order_id", "sequence"),
    )
    op.create_index(
        op.f("ix_payment_splits_created_at"),
        "payment_splits",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_splits_payment_order_id"),
        "payment_splits",
        ["payment_order_id"],
        unique=False,
    )

    op.create_table(
        "report_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_report_jobs_created_at"),
        "report_jobs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_report_jobs_status"),
        "report_jobs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_report_jobs_user_id"), "report_jobs", ["user_id"], unique=False
    )

    op.create_table(
        "risk_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("check_type", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("reason_codes_json", sa.JSON(), nullable=True),
        sa.Column("raw_payload_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_risk_checks_created_at"),
        "risk_checks",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_risk_checks_payment_order_id"),
        "risk_checks",
        ["payment_order_id"],
        unique=False,
    )
    op.create_index(op.f("ix_risk_checks_result"), "risk_checks", ["result"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_risk_checks_result"), table_name="risk_checks")
    op.drop_index(op.f("ix_risk_checks_created_at"), table_name="risk_checks")
    op.drop_index(op.f("ix_risk_checks_payment_order_id"), table_name="risk_checks")
    op.drop_table("risk_checks")

    op.drop_index(op.f("ix_report_jobs_status"), table_name="report_jobs")
    op.drop_index(op.f("ix_report_jobs_created_at"), table_name="report_jobs")
    op.drop_index(op.f("ix_report_jobs_user_id"), table_name="report_jobs")
    op.drop_table("report_jobs")

    op.drop_index(op.f("ix_payment_splits_created_at"), table_name="payment_splits")
    op.drop_index(op.f("ix_payment_splits_payment_order_id"), table_name="payment_splits")
    op.drop_table("payment_splits")

    op.drop_index(op.f("ix_payment_quotes_created_at"), table_name="payment_quotes")
    op.drop_index(op.f("ix_payment_quotes_payment_order_id"), table_name="payment_quotes")
    op.drop_table("payment_quotes")

    op.drop_index(op.f("ix_audit_logs_trace_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_user_id"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_payment_orders_status"), table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_created_at"), table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_user_id"), table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_source_command_id"), table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_reference"), table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_organization_id"), table_name="payment_orders")
    op.drop_index(op.f("ix_payment_orders_beneficiary_id"), table_name="payment_orders")
    op.drop_table("payment_orders")

    op.drop_index(
        op.f("ix_command_executions_final_status"), table_name="command_executions"
    )
    op.drop_index(op.f("ix_command_executions_created_at"), table_name="command_executions")
    op.drop_index(op.f("ix_command_executions_user_id"), table_name="command_executions")
    op.drop_index(op.f("ix_command_executions_trace_id"), table_name="command_executions")
    op.drop_index(op.f("ix_command_executions_session_id"), table_name="command_executions")
    op.drop_table("command_executions")

    op.drop_index(
        op.f("ix_conversation_sessions_created_at"), table_name="conversation_sessions"
    )
    op.drop_index(
        op.f("ix_conversation_sessions_user_id"), table_name="conversation_sessions"
    )
    op.drop_table("conversation_sessions")

    op.drop_index(op.f("ix_beneficiaries_created_at"), table_name="beneficiaries")
    op.drop_table("beneficiaries")

    op.drop_index(op.f("ix_users_created_at"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_organizations_created_at"), table_name="organizations")
    op.drop_table("organizations")
