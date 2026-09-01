"""Üyelik: kullanıcılar, oturumlar, e-posta tokenleri, denetim kaydı

0001 ve 0002 gibi bu revizyon da IDEMPOTENT yazıldı: sahadaki bazı
`hostcheck.db` dosyaları Alembic öncesi `create_all()` yolundan geldi, tablo
zaten duruyor olabilir. Her tablo tek tek kontrol edilir — dördü birden değil,
çünkü yarım kalmış bir yükseltmeden sonra ikisi var ikisi yok olabilir.

Revision ID: 0003_uyelik
Revises: 0002_site_hizi
Create Date: 2026-08-31

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_uyelik"
down_revision: Union[str, None] = "0002_site_hizi"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    mevcut = _tables()

    if "kullanicilar" not in mevcut:
        op.create_table(
            "kullanicilar",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("email", sa.String(length=254), nullable=False),
            sa.Column("ad_soyad", sa.String(length=120), nullable=False),
            sa.Column("sifre_hash", sa.String(length=120), nullable=False),
            sa.Column("dogrulandi", sa.Boolean(), nullable=False,
                      server_default=sa.text("0")),
            sa.Column("aktif", sa.Boolean(), nullable=False,
                      server_default=sa.text("1")),
            sa.Column("rol", sa.String(length=20), nullable=False,
                      server_default="uye"),
            sa.Column("basarisiz_giris", sa.Integer(), nullable=False,
                      server_default=sa.text("0")),
            sa.Column("kilit_bitis", sa.DateTime(timezone=True), nullable=True),
            sa.Column("son_giris", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_kullanicilar_id"), "kullanicilar", ["id"])
        op.create_index(op.f("ix_kullanicilar_email"), "kullanicilar", ["email"],
                        unique=True)

    if "oturumlar" not in mevcut:
        op.create_table(
            "oturumlar",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("csrf", sa.String(length=64), nullable=False),
            sa.Column("kullanici_id", sa.Integer(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("uzun", sa.Boolean(), nullable=False,
                      server_default=sa.text("0")),
            sa.Column("ip", sa.String(length=45), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.ForeignKeyConstraint(["kullanici_id"], ["kullanicilar.id"],
                                    ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_oturumlar_id"), "oturumlar", ["id"])
        op.create_index(op.f("ix_oturumlar_token_hash"), "oturumlar",
                        ["token_hash"], unique=True)
        op.create_index(op.f("ix_oturumlar_kullanici_id"), "oturumlar",
                        ["kullanici_id"])
        op.create_index(op.f("ix_oturumlar_expires_at"), "oturumlar",
                        ["expires_at"])

    if "eposta_tokenleri" not in mevcut:
        op.create_table(
            "eposta_tokenleri",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("kullanici_id", sa.Integer(), nullable=False),
            sa.Column("amac", sa.String(length=20), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("kullanildi_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.ForeignKeyConstraint(["kullanici_id"], ["kullanicilar.id"],
                                    ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_eposta_tokenleri_id"), "eposta_tokenleri", ["id"])
        op.create_index(op.f("ix_eposta_tokenleri_token_hash"), "eposta_tokenleri",
                        ["token_hash"], unique=True)
        op.create_index(op.f("ix_eposta_tokenleri_kullanici_id"),
                        "eposta_tokenleri", ["kullanici_id"])

    if "denetim_kayitlari" not in mevcut:
        op.create_table(
            "denetim_kayitlari",
            sa.Column("id", sa.Integer(), nullable=False),
            # ForeignKey YOK: kullanıcı silinse de denetim izi kalmalı.
            sa.Column("kullanici_id", sa.Integer(), nullable=True),
            sa.Column("eposta", sa.String(length=254), nullable=True),
            sa.Column("eylem", sa.String(length=50), nullable=False),
            sa.Column("hedef", sa.String(length=200), nullable=True),
            sa.Column("detay", sa.Text(), nullable=True),
            sa.Column("ip", sa.String(length=45), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_denetim_kayitlari_id"), "denetim_kayitlari", ["id"])
        op.create_index(op.f("ix_denetim_kayitlari_kullanici_id"),
                        "denetim_kayitlari", ["kullanici_id"])
        op.create_index(op.f("ix_denetim_kayitlari_eylem"), "denetim_kayitlari",
                        ["eylem"])
        op.create_index(op.f("ix_denetim_kayitlari_created_at"),
                        "denetim_kayitlari", ["created_at"])
        op.create_index("ix_denetim_eylem_created", "denetim_kayitlari",
                        ["eylem", "created_at"])


def downgrade() -> None:
    mevcut = _tables()
    # Bağımlı tablolar önce düşer.
    for tablo in ("denetim_kayitlari", "eposta_tokenleri", "oturumlar", "kullanicilar"):
        if tablo in mevcut:
            op.drop_table(tablo)
