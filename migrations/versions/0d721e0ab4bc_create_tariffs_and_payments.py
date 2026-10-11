"""create tariffs and payments

Revision ID: 0d721e0ab4bc
Revises:
Create Date: 2026-10-11 12:00:19.146790

Сгенерировано alembic --autogenerate и вычищено вручную:
- created_at: sa.DateTime(timezone=True) вместо app.db.UTCDateTime — автогенерация вставила
  тип приложения без импорта, а в схеме БД это обычный DATETIME (UTCDateTime — обёртка в Python);
- убраны дублирующие CHECK для enum: sa.Enum(create_constraint=True) создаёт их сам;
- индексы — обычный op.create_index вместо batch_alter_table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0d721e0ab4bc"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tariffs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=50), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.CheckConstraint("price > 0", name=op.f("ck_tariffs_price_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tariffs")),
        sa.UniqueConstraint("title", name=op.f("uq_tariffs_title")),
    )
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "succeeded",
                "failed",
                "refunded",
                name="payment_status",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("tariff_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "method",
            sa.Enum(
                "card",
                "sbp",
                "installment",
                name="payment_method",
                native_enum=False,
                create_constraint=True,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("installment_months", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("discount", sa.Integer(), nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("request_hash", sa.String(length=64), nullable=True),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_amount_positive")),
        sa.CheckConstraint("discount >= 0", name=op.f("ck_payments_discount_non_negative")),
        sa.ForeignKeyConstraint(
            ["tariff_id"], ["tariffs.id"], name=op.f("fk_payments_tariff_id_tariffs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_payments_idempotency_key")),
    )
    op.create_index(op.f("ix_payments_email"), "payments", ["email"])
    op.create_index(op.f("ix_payments_status"), "payments", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_status"), table_name="payments")
    op.drop_index(op.f("ix_payments_email"), table_name="payments")
    op.drop_table("payments")
    op.drop_table("tariffs")
