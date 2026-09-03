"""Üyeliği kaldır: kullanıcı, oturum, e-posta tokeni ve denetim tablolarını düşür

Üyelik sistemi (0003) 3 Eylül'de geri alındı; Hazır Yanıtlar yeniden anonim
okumaya açık, yazma Nginx Basic Auth'ta. Bu revizyon o dört tabloyu düşürür.

0003 SİLİNMEDİ: sahadaki veritabanlarının `alembic_version` satırı
`0003_uyelik` diyor, revizyon dosyası ortadan kalkarsa Alembic zinciri
çözemez ve `upgrade head` "Can't locate revision" ile durur. Zincir korunup
üzerine bir düşürme revizyonu ekleniyor.

Diğerleri gibi IDEMPOTENT: tablo yoksa (üyelik hiç dağıtılmamış bir kurulum)
sessizce geçilir. `downgrade` bilerek 0003'ün `upgrade`'ini yeniden çağırır —
şema geri gelir, veri gelmez; parola hash'leri geri getirilemez.

Revision ID: 0004_uyelik_kaldir
Revises: 0003_uyelik
Create Date: 2026-09-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_uyelik_kaldir"
down_revision: Union[str, None] = "0003_uyelik"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Düşürme sırası FK yönünü izler: `oturumlar` ve `eposta_tokenleri`
# `kullanicilar`a bağlı. `foreign_keys=ON` açık (database.py), ters sırada
# düşürmek kısıt hatası verirdi.
_TABLOLAR = ("oturumlar", "eposta_tokenleri", "denetim_kayitlari", "kullanicilar")


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    mevcut = _tables()
    for tablo in _TABLOLAR:
        if tablo in mevcut:
            op.drop_table(tablo)


def downgrade() -> None:
    """Şemayı geri kur — 0003'ün kendi (idempotent) upgrade'ini kullanır.

    `versions/` bir paket değil (`__init__.py` yok), o yüzden normal import
    çalışmaz; dosya yolundan yükleniyor.
    """
    import importlib.util
    import os

    yol = os.path.join(os.path.dirname(__file__), "0003_uyelik.py")
    spec = importlib.util.spec_from_file_location("_uyelik_0003", yol)
    onceki = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(onceki)
    onceki.upgrade()
