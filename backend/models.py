from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float
from sqlalchemy.sql import func
from database import Base


class HazirYanit(Base):
    __tablename__ = "hazir_yanitlar"

    id        = Column(Integer, primary_key=True, index=True)
    title     = Column(String(200), nullable=False)
    content   = Column(Text, nullable=False)
    category  = Column(String(100), nullable=False, index=True)
    is_pinned = Column(Boolean, default=False, nullable=False)
    use_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class HazirYanitKategori(Base):
    __tablename__ = "hazir_yanit_kategoriler"

    id    = Column(Integer, primary_key=True, index=True)
    name  = Column(String(100), unique=True, nullable=False)
    color = Column(String(20), nullable=False, default='#6b7388')


class SiteHiziOlcum(Base):
    """Bir site hızı ölçümünün özeti — geçmiş ve karşılaştırma için.

    Tam sonuç `ozet_json`'da saklanır; sütunlar yalnızca trend grafiği ve
    karşılaştırma sorgularının indeksten okuyabilmesi için ayrıştırılmıştır.
    Domain başına son N kayıt tutulur (bkz. `site_speed.store.buda`) — aksi
    hâlde tablo sınırsız büyür.
    """
    __tablename__ = "site_hizi_olcumleri"

    id         = Column(Integer, primary_key=True, index=True)
    domain     = Column(String(253), nullable=False, index=True)
    strategy   = Column(String(10), nullable=False)      # mobile | desktop
    motor      = Column(String(10), nullable=False, default="yerel")  # yerel | psi
    score      = Column(Integer, nullable=False)
    fcp_ms     = Column(Integer)
    lcp_ms     = Column(Integer)
    tbt_ms     = Column(Integer)
    ttfb_ms    = Column(Integer)
    cls        = Column(Float)
    toplam_bayt   = Column(Integer)
    istek_sayisi  = Column(Integer)
    ozet_json  = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
