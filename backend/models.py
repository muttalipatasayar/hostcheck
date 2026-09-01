from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey, Index,
)
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


# ── Üyelik ───────────────────────────────────────────────────────────────────
#
# Panel 22 Ağustos'a kadar kimlik doğrulamasızdı; yazma uçları tek bir
# paylaşılan Nginx Basic Auth parolasına bağlıydı, yani "kim değiştirdi"
# sorusunun cevabı yoktu. Bu dört tablo o boşluğu kapatıyor.


class Kullanici(Base):
    """Panel üyesi. E-posta alan adı `auth_core.IZINLI_ALANLAR` ile sınırlı.

    `email` DAİMA normalize edilmiş (küçük harf, ASCII) hâliyle saklanır —
    normalizasyon `auth_core.eposta_normalize()` içinde tek bir yerde yapılır;
    aksi hâlde `A@natro.com` ve `a@natro.com` iki ayrı hesap olurdu.
    """
    __tablename__ = "kullanicilar"

    id          = Column(Integer, primary_key=True, index=True)
    email       = Column(String(254), unique=True, nullable=False, index=True)
    ad_soyad    = Column(String(120), nullable=False)
    sifre_hash  = Column(String(120), nullable=False)
    dogrulandi  = Column(Boolean, default=False, nullable=False)
    # Yönetici hesabı askıya alabilir. `aktif=False` olan kullanıcının açık
    # oturumları da düşer — kontrol her istekte `oturum_coz()` içinde yapılır.
    aktif       = Column(Boolean, default=True, nullable=False)
    rol         = Column(String(20), default="uye", nullable=False)   # uye | admin
    # Kaba kuvvet kelepçesi. IP tabanlı rate limit tek başına yetmez: saldırgan
    # IP değiştirebilir ama hedef hesap sabittir.
    basarisiz_giris = Column(Integer, default=0, nullable=False)
    kilit_bitis = Column(DateTime(timezone=True))
    son_giris   = Column(DateTime(timezone=True))
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())


class Oturum(Base):
    """Sunucu tarafında tutulan oturum. JWT DEĞİL — bilerek.

    JWT iptal edilemez: yöneticinin bir hesabı askıya alması, parola
    değişikliğinin diğer cihazları düşürmesi ve "oturumlarımı kapat" düğmesi
    ancak sunucuda satır olduğunda çalışır.

    `token_hash` ham tokenin sha256'sıdır; veritabanı sızsa bile satırlardan
    kullanılabilir bir çerez üretilemez.
    """
    __tablename__ = "oturumlar"

    id           = Column(Integer, primary_key=True, index=True)
    token_hash   = Column(String(64), unique=True, nullable=False, index=True)
    # Çift-gönderim CSRF jetonu: HttpOnly OLMAYAN çerezle tarayıcıya verilir,
    # durum değiştiren isteklerde `X-CSRF-Token` başlığında geri beklenir.
    csrf         = Column(String(64), nullable=False)
    kullanici_id = Column(Integer, ForeignKey("kullanicilar.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    expires_at   = Column(DateTime(timezone=True), nullable=False, index=True)
    # "Beni hatırla" işaretlendi mi. Kayan yenilemenin oturumu hangi süreyle
    # uzatacağını bilmesi için saklanır; `expires_at`ten geriye hesaplamak
    # her yenilemeden sonra yanlış sonuç verirdi.
    uzun         = Column(Boolean, default=False, nullable=False)
    ip           = Column(String(45))
    user_agent   = Column(String(255))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())


class EpostaTokeni(Base):
    """Tek kullanımlık e-posta bağlantısı: hesap doğrulama veya parola sıfırlama.

    Ham token yalnızca e-postada bulunur; burada sha256'sı durur. `kullanildi_at`
    dolduğunda token ölür (yeniden oynatma yok).
    """
    __tablename__ = "eposta_tokenleri"

    id            = Column(Integer, primary_key=True, index=True)
    token_hash    = Column(String(64), unique=True, nullable=False, index=True)
    kullanici_id  = Column(Integer, ForeignKey("kullanicilar.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    amac          = Column(String(20), nullable=False)   # dogrulama | sifre
    expires_at    = Column(DateTime(timezone=True), nullable=False)
    kullanildi_at = Column(DateTime(timezone=True))
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


class DenetimKaydi(Base):
    """Kim, ne zaman, neyi değiştirdi.

    `eposta` sütunu `kullanici_id` ile birlikte tutuluyor çünkü kullanıcı
    silindiğinde satır CASCADE ile gitmemeli — iz kaybolur. Bu yüzden burada
    ForeignKey YOK; `kullanici_id` yalnızca bir sayıdır.

    Tablo sınırsız büyümesin diye `auth_core.denetim_yaz()` her yazımda
    en eski kayıtları budar.
    """
    __tablename__ = "denetim_kayitlari"

    id           = Column(Integer, primary_key=True, index=True)
    kullanici_id = Column(Integer, index=True)
    eposta       = Column(String(254))
    eylem        = Column(String(50), nullable=False, index=True)
    hedef        = Column(String(200))
    detay        = Column(Text)
    ip           = Column(String(45))
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# Denetim ekranı hep "en yeniden eskiye, isteğe bağlı eylem filtresi" biçiminde
# sorguluyor; birleşik indeks tam bu sorguyu karşılar.
Index("ix_denetim_eylem_created", DenetimKaydi.eylem, DenetimKaydi.created_at)
