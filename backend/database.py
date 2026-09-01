import os

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Yol CWD'ye görelidir; systemd `WorkingDirectory=/opt/hostcheck/backend` ile
# sabitler. Ortam değişkeni kancası testler için: `tests/conftest.py` burayı
# geçici bir dosyaya yönlendirir, yoksa test koşusu geliştirme veritabanına
# kullanıcı/oturum satırları yazardı.
SQLALCHEMY_DATABASE_URL = os.getenv("HOSTCHECK_DB_URL", "sqlite:///./hostcheck.db")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        # Varsayılan 5 sn. Üyelik geldiğinden beri her giriş/CRUD bir yazma
        # işlemi; eşzamanlı bir okuma kilide takılırsa 5 sn'de vazgeçip
        # "database is locked" hatası veriyordu.
        "timeout": 30,
    },
)


@event.listens_for(engine, "connect")
def _sqlite_pragmalar(dbapi_conn, _kayit):
    """Her bağlantıda WAL + makul bekleme.

    `delete` journal modunda HER commit tüm okuyucuları bloklar. Panel
    bugüne kadar neredeyse hiç yazmıyordu, o yüzden fark edilmemişti; üyelik
    ile birlikte giriş, denetim kaydı ve kullanım sayacı düzenli yazma
    getiriyor. WAL'da okuyucular yazarı beklemez.

    `foreign_keys=ON` da burada: SQLite kısıtı VARSAYILAN OLARAK KAPALIDIR,
    yani `ondelete="CASCADE"` bu pragma olmadan hiç çalışmaz ve kullanıcı
    silindiğinde oturum/token satırları öksüz kalırdı.
    """
    cur = dbapi_conn.cursor()
    try:
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.execute("PRAGMA foreign_keys=ON")
    finally:
        cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
