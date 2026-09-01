"""Site hızı ölçüm geçmişi tablosu

Bu revizyon da idempotent yazıldı: mevcut kurulumlarda tablo elle ya da eski
`create_all()` yoluyla oluşturulmuş olabilir; varsa dokunulmaz.

Revision ID: 0002_site_hizi
Revises: 0001_initial
Create Date: 2026-08-31

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_site_hizi"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLO = "site_hizi_olcumleri"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if _TABLO in _tables():
        return

    op.create_table(
        _TABLO,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("strategy", sa.String(length=10), nullable=False),
        sa.Column("motor", sa.String(length=10), nullable=False,
                  server_default="yerel"),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("fcp_ms", sa.Integer(), nullable=True),
        sa.Column("lcp_ms", sa.Integer(), nullable=True),
        sa.Column("tbt_ms", sa.Integer(), nullable=True),
        sa.Column("ttfb_ms", sa.Integer(), nullable=True),
        sa.Column("cls", sa.Float(), nullable=True),
        sa.Column("toplam_bayt", sa.Integer(), nullable=True),
        sa.Column("istek_sayisi", sa.Integer(), nullable=True),
        sa.Column("ozet_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f(f"ix_{_TABLO}_id"), _TABLO, ["id"], unique=False)
    op.create_index(op.f(f"ix_{_TABLO}_domain"), _TABLO, ["domain"], unique=False)
    # Geçmiş sorgusu hep "şu domain, şu strateji, en yeniden eskiye" biçiminde
    # geldiği için birleşik indeks tam sorguyu karşılar.
    op.create_index(f"ix_{_TABLO}_domain_strategy_created", _TABLO,
                    ["domain", "strategy", "created_at"], unique=False)


def downgrade() -> None:
    if _TABLO not in _tables():
        return
    op.drop_index(f"ix_{_TABLO}_domain_strategy_created", table_name=_TABLO)
    op.drop_index(op.f(f"ix_{_TABLO}_domain"), table_name=_TABLO)
    op.drop_index(op.f(f"ix_{_TABLO}_id"), table_name=_TABLO)
    op.drop_table(_TABLO)
