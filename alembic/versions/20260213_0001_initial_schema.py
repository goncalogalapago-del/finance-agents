"""initial schema

Revision ID: 20260213_0001
Revises:
Create Date: 2026-02-13 14:20:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260213_0001"
down_revision = None
branch_labels = None
depends_on = None


TXN_TYPE_ENUM = sa.Enum(
    "trade",
    "deposit",
    "withdrawal",
    "fee",
    "dividend",
    "interest",
    "other",
    name="txn_type_enum",
)

TRADE_SIDE_ENUM = sa.Enum("buy", "sell", name="trade_side_enum")

PROPOSAL_STATUS_ENUM = sa.Enum(
    "PROPOSED",
    "APPROVED",
    "REJECTED",
    "EXPIRED",
    name="proposal_status_enum",
)

PROPOSAL_ACTION_ENUM = sa.Enum("BUY", "SELL", name="proposal_action_enum")

PROPOSAL_DECISION_ENUM = sa.Enum("APPROVE", "REJECT", name="proposal_decision_enum")

INSTITUTION_TYPE_ENUM = sa.Enum("BROKER", "BANK", name="institution_type_enum")

INGESTION_STATUS_ENUM = sa.Enum("SUCCESS", "DEGRADED", "FAILED", name="ingestion_status_enum")


def upgrade() -> None:
    op.create_table(
        "institutions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("type", INSTITUTION_TYPE_ENUM, nullable=False),
        sa.Column("provider_code", sa.Text(), nullable=False, unique=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("institution_id", sa.Uuid(), sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("external_account_id", sa.Text(), nullable=False),
        sa.Column("account_label", sa.Text(), nullable=False),
        sa.Column("account_type", sa.Text(), nullable=False),
        sa.Column("base_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("institution_id", "external_account_id", name="uq_account_external"),
    )

    op.create_table(
        "instruments",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("isin", sa.Text(), nullable=True),
        sa.Column("symbol", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("asset_class", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("is_allowlisted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("isin", "symbol", name="uq_instrument_isin_symbol"),
    )

    op.create_table(
        "balances",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("balance_amount", sa.Numeric(20, 6), nullable=False),
        sa.Column("available_amount", sa.Numeric(20, 6), nullable=True),
        sa.UniqueConstraint("account_id", "as_of_utc", "currency", name="uq_balance_snapshot"),
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 10), nullable=False),
        sa.Column("avg_cost", sa.Numeric(20, 6), nullable=True),
        sa.Column("market_price", sa.Numeric(20, 6), nullable=True),
        sa.Column("market_value", sa.Numeric(20, 6), nullable=True),
        sa.UniqueConstraint(
            "account_id",
            "instrument_id",
            "as_of_utc",
            name="uq_position_snapshot",
        ),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("instrument_id", sa.Uuid(), sa.ForeignKey("instruments.id"), nullable=True),
        sa.Column("external_txn_id", sa.Text(), nullable=False),
        sa.Column("txn_type", TXN_TYPE_ENUM, nullable=False),
        sa.Column("trade_side", TRADE_SIDE_ENUM, nullable=True),
        sa.Column("executed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settled_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quantity", sa.Numeric(24, 10), nullable=True),
        sa.Column("price", sa.Numeric(20, 6), nullable=True),
        sa.Column("gross_amount", sa.Numeric(20, 6), nullable=True),
        sa.Column("fee_amount", sa.Numeric(20, 6), nullable=True),
        sa.Column("tax_amount", sa.Numeric(20, 6), nullable=True),
        sa.Column("net_amount", sa.Numeric(20, 6), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("raw_category", sa.Text(), nullable=True),
        sa.UniqueConstraint("account_id", "external_txn_id", name="uq_transaction_external"),
    )

    op.create_table(
        "fx_rates",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("base_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("quote_currency", sa.CHAR(length=3), nullable=False),
        sa.Column("as_of_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rate", sa.Numeric(20, 10), nullable=False),
        sa.UniqueConstraint(
            "base_currency", "quote_currency", "as_of_utc", name="uq_fx_snapshot"
        ),
    )

    op.create_table(
        "proposals",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("period_month", sa.Date(), nullable=False),
        sa.Column("status", PROPOSAL_STATUS_ENUM, nullable=False),
        sa.Column("proposal_payload", sa.JSON(), nullable=False),
        sa.Column("narrative_payload", sa.JSON(), nullable=False),
        sa.Column("risk_checks_payload", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "proposal_actions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("proposal_id", sa.Uuid(), sa.ForeignKey("proposals.id"), nullable=False),
        sa.Column("action_type", PROPOSAL_ACTION_ENUM, nullable=False),
        sa.Column("instrument_id", sa.Uuid(), sa.ForeignKey("instruments.id"), nullable=False),
        sa.Column("suggested_amount", sa.Numeric(20, 6), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
    )

    op.create_table(
        "proposal_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("proposal_id", sa.Uuid(), sa.ForeignKey("proposals.id"), nullable=False),
        sa.Column("decision", PROPOSAL_DECISION_ENUM, nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("decided_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_nonce", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.UniqueConstraint("proposal_id", "idempotency_key", name="uq_proposal_approval_idempotency"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("event_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(length=256), nullable=True),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("entity_type", sa.String(length=128), nullable=False),
        sa.Column("entity_id", sa.String(length=256), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("prev_hash", sa.Text(), nullable=True),
        sa.Column("event_hash", sa.Text(), nullable=True),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", INGESTION_STATUS_ENUM, nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stats_payload", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_table("audit_events")
    op.drop_table("proposal_approvals")
    op.drop_table("proposal_actions")
    op.drop_table("proposals")
    op.drop_table("fx_rates")
    op.drop_table("transactions")
    op.drop_table("positions")
    op.drop_table("balances")
    op.drop_table("instruments")
    op.drop_table("accounts")
    op.drop_table("institutions")

    INGESTION_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    PROPOSAL_DECISION_ENUM.drop(op.get_bind(), checkfirst=True)
    PROPOSAL_ACTION_ENUM.drop(op.get_bind(), checkfirst=True)
    PROPOSAL_STATUS_ENUM.drop(op.get_bind(), checkfirst=True)
    TRADE_SIDE_ENUM.drop(op.get_bind(), checkfirst=True)
    TXN_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
    INSTITUTION_TYPE_ENUM.drop(op.get_bind(), checkfirst=True)
