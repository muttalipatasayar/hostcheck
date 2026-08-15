"""Başlangıç şeması: hazır yanıtlar + kategoriler; eski ticket tabloları kaldırıldı

Bu revizyon idempotent yazıldı: hem sıfırdan bir veritabanında hem de
eski `Base.metadata.create_all()` ile oluşturulmuş mevcut bir
hostcheck.db üzerinde sorunsuz çalışır.

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-15

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    existing = _tables()

    if "hazir_yanitlar" not in existing:
        op.create_table(
            "hazir_yanitlar",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("category", sa.String(length=100), nullable=False),
            sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_hazir_yanitlar_id", "hazir_yanitlar", ["id"])
        op.create_index("ix_hazir_yanitlar_category", "hazir_yanitlar", ["category"])

    if "hazir_yanit_kategoriler" not in existing:
        op.create_table(
            "hazir_yanit_kategoriler",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("color", sa.String(length=20), nullable=False, server_default="#6b7388"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
        op.create_index("ix_hazir_yanit_kategoriler_id", "hazir_yanit_kategoriler", ["id"])

    # Ticket modülü kaldırıldı — eski kurulumlarda kalan tabloyu temizle
    if "tickets" in existing:
        op.drop_table("tickets")


def downgrade() -> None:
    op.drop_table("hazir_yanit_kategoriler")
    op.drop_table("hazir_yanitlar")
