"""Uygulama açılışında Alembic migration'larını çalıştırır.

`Base.metadata.create_all()` yeni tablo oluşturur ama mevcut bir tabloya
kolon eklemez — şema değiştiğinde eski hostcheck.db dosyaları sessizce
bozulurdu. Migration'lar bu boşluğu kapatır.
"""
import logging
import os

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))


def _config() -> Config:
    cfg = Config(os.path.join(_BACKEND_DIR, "alembic.ini"))
    # alembic.ini göreli yol kullanıyor; cwd farklıysa mutlak yola çevir
    cfg.set_main_option("script_location", os.path.join(_BACKEND_DIR, "migrations"))
    return cfg


def run_migrations() -> None:
    """Veritabanını en güncel şemaya yükseltir (idempotent)."""
    command.upgrade(_config(), "head")
    logger.info("Veritabanı şeması güncel.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migrations()
