"""Üyelik çekirdeği — parola, oturum, çerez, CSRF, yetki ve denetim kaydı.

Neden ayrı bir modül: `routers/uyelik.py`, `routers/yonetim.py` ve
`routers/hazir_yanitlar.py` üçü de aynı kapılardan geçmek zorunda.
`net_validation.py` (SSRF kapısı) ve `ws_utils.py` (WebSocket origin kapısı)
ile aynı rolü oynar: doğrulama tek yerde yapılır, çağıranlar kopyalamaz.

Panelin geri kalanı KİMLİK DOĞRULAMASIZ kalmaya devam eder (DNS/SSL/IP
araçları herkese açık). Bu modülün koruduğu tek şey hazır yanıt kütüphanesi
ve yönetim uçlarıdır.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import bcrypt
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from database import get_db
from models import DenetimKaydi, Kullanici, Oturum

# ── Yapılandırma ─────────────────────────────────────────────────────────────

# Çerez adları ÜRETİMDE `__Host-` önekli.
#
# Bu makinede `aipromt.com.tr`, `risale.aipromt.com.tr` ve `dns.aipromt.com.tr`
# aynı kayıtlı alan adını paylaşıyor. Kardeş bir vhost'ta XSS bulan biri
# `Set-Cookie: hc_oturum=...; Domain=aipromt.com.tr; Path=/` yazabilir;
# tarayıcı iki çerezi de gönderir ve Starlette'in ayrıştırıcısı SONUNCUYU
# kazandırır → oturum sabitleme. `__Host-` öneki tarayıcı tarafında
# "Secure + Path=/ + Domain YOK" şartını zorunlu kılar, yani saldırgan bu
# adı `Domain` ile set EDEMEZ.
#
# Geliştirmede (http) `Secure` çerez yazılamayacağı için önek düşer.
_COOKIE_OTURUM_TABAN = "hc_oturum"
_COOKIE_CSRF_TABAN = "hc_csrf"


def cerez_adlari() -> tuple[str, str]:
    """(oturum_adi, csrf_adi). Fonksiyon çünkü `ENV` .env'den geç yüklenebilir."""
    onek = "" if _gelistirme_mi() else "__Host-"
    return onek + _COOKIE_OTURUM_TABAN, onek + _COOKIE_CSRF_TABAN


def oturum_cerezi(request: "Request") -> str:
    """İsteğin taşıdığı oturum tokeni. Üretim ve geliştirme adının ikisine de bakar."""
    oturum_ad, _ = cerez_adlari()
    return request.cookies.get(oturum_ad) or ""

# Oturum süreleri. "Beni hatırla" işaretlenmezse tarayıcı kapanınca çerez
# düşer (session cookie), ayrıca sunucu tarafı da 12 saat sonra süresini
# doldurur — iki katman birden.
_VARSAYILAN_SAAT = int(os.getenv("OTURUM_SURESI_SAAT", "12"))
_UZUN_GUN = int(os.getenv("OTURUM_UZUN_SURE_GUN", "30"))

# E-posta bağlantılarının ömrü.
DOGRULAMA_SAAT = 24
SIFRE_SIFIRLAMA_DAKIKA = 30

# Kaba kuvvet kelepçesi (IP limitine EK olarak, hesap bazlı).
MAKS_BASARISIZ = 5
# Kullanıcı başına aynı anda açık kalabilecek oturum sayısı.
MAKS_OTURUM = 10
KILIT_DAKIKA = 15

PAROLA_MIN = 10
# Denetim kaydı tavanı. 5000 çok düşüktü: günde yüzlerce giriş + CRUD ile
# kayıt bir haftada dönerdi. 20.000 satır SQLite'ta ~4 MB.
DENETIM_TAVAN = 20_000
# Budamayı HER yazımda çalıştırmak her yazıma fazladan bir COUNT ve bir DELETE
# ekler; WAL'da bile gereksiz fsync demektir. Olasılıksal tetikleme aynı
# tavanı çok daha ucuza tutar.
_BUDAMA_OLASILIGI = 100

# `bcrypt` 72 bayttan sonrasını sessizce keser. Parolayı önce sha256'dan
# geçirip base64'lemek hem bu kesilmeyi hem de gömülü null baytı ortadan
# kaldırır; sonuç daima 44 bayt ASCII olur.
_BCRYPT_MALIYET = 12
# Kullanıcı bulunamadığında da bcrypt çalıştırmak için kukla hash — "bu
# e-posta kayıtlı mı" sorusunun yanıt süresinden okunmasını engeller.
_KUKLA_HASH = bcrypt.hashpw(b"x" * 44, bcrypt.gensalt(_BCRYPT_MALIYET))

# bcrypt maliyet 12 ≈ 250-400 ms SAF CPU. Panel tek worker'la çalışıyor ve
# aynı süreçte SSH/RDP tünelleri, Playwright ölçümleri ve DNS fan-out'ları var.
# Kelepçe olmasaydı kimliği doğrulanmamış giriş denemeleri panelin tamamını
# yavaşlatan bir CPU tüketim ilkesine dönüşürdü. 4 eşzamanlı hash tavanı,
# gerçek kullanıcıyı yavaşlatmadan bu yüzeyi kapatır.
_HASH_KELEPCE = threading.BoundedSemaphore(4)


def izinli_alanlar() -> list[str]:
    """Üye olabilecek e-posta alan adları. Ortamdan okunur, testte değişebilir."""
    ham = os.getenv("IZINLI_MAIL_ALANLARI", "natro.com,team.blue")
    return [a.strip().lower() for a in ham.split(",") if a.strip()]


def kurucu_adminler() -> set[str]:
    """`.env` ile sabitlenen yönetici adresleri — panelden düşürülemezler."""
    ham = os.getenv("ADMIN_EPOSTALARI", "yonetici@sirketiniz.com")
    return {a.strip().lower() for a in ham.split(",") if a.strip()}


def _gelistirme_mi() -> bool:
    # Varsayılan "production": .env okunamazsa çerezler Secure kalır.
    return os.getenv("ENV", "production") == "development"


# ── Zaman ────────────────────────────────────────────────────────────────────
#
# SQLite `DateTime(timezone=True)` sütunları geri okunduğunda NAİF datetime
# döndürür. Karşılaştırmada naif/aware karışırsa TypeError alınır, o da
# "oturum hiç dolmuyor" gibi sessiz bir güvenlik hatasına dönüşür. Bu yüzden
# her şey NAİF UTC olarak yazılır ve okunur.

def simdi() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def naif(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


# ── E-posta ──────────────────────────────────────────────────────────────────
#
# Yalnızca ASCII kabul edilir. Unicode'a izin verilseydi Kiril "а" (U+0430)
# ile yazılmış `nаtro.com` alan adı listeye göre farklı bir dize olurdu ama
# gözle `natro.com`dan ayırt edilemezdi.
_EPOSTA_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_EPOSTA_MAKS = 254


def eposta_normalize(ham: str) -> str:
    """Biçimi doğrular ve saklanacak kanonik hâli döndürür.

    Alan adı kontrolü BURADA DEĞİL (`alan_kontrol`) — bazı uçlar (parola
    sıfırlama) yalnızca biçim doğrulaması ister.
    """
    e = (ham or "").strip()
    if not e:
        raise HTTPException(status_code=400, detail="E-posta adresi boş olamaz.")
    if "\x00" in e or "\r" in e or "\n" in e:
        # Satır sonu enjeksiyonu: adres SMTP başlıklarına yazılıyor.
        raise HTTPException(status_code=400, detail="E-posta adresi geçersiz karakter içeriyor.")
    if len(e) > _EPOSTA_MAKS:
        raise HTTPException(status_code=400, detail="E-posta adresi çok uzun.")
    if not e.isascii():
        raise HTTPException(
            status_code=400,
            detail="E-posta adresi yalnızca İngilizce harf ve rakam içerebilir.",
        )
    if e.count("@") != 1:
        raise HTTPException(status_code=400, detail="Geçerli bir e-posta adresi girin.")
    e = e.lower()
    if not _EPOSTA_RE.match(e):
        raise HTTPException(status_code=400, detail="Geçerli bir e-posta adresi girin.")
    return e


def alan_kontrol(eposta: str) -> None:
    """Kurumsal alan adı kapısı. TAM eşleşme — sonek eşleşmesi DEĞİL.

    Sonek eşleşmesi (`endswith(".natro.com")` gibi) `evil-natro.com` ve
    `natro.com.saldirgan.net` adreslerini içeri alırdı. Alt alan adları da
    (`mail.natro.com`) bilerek dışarıda: izin verilecekse listeye açıkça
    eklenmeli.
    """
    alan = eposta.rsplit("@", 1)[1]
    izinli = izinli_alanlar()
    if alan not in izinli:
        liste = " ve ".join("@" + a for a in izinli)
        raise HTTPException(
            status_code=403,
            detail=(
                f"Yalnızca {liste} uzantılı kurumsal e-posta adresleriyle üye "
                f"olunabilir. Girdiğiniz adres (@{alan}) kabul edilmiyor."
            ),
        )


# ── Parola ───────────────────────────────────────────────────────────────────

def parola_politikasi(parola: str, eposta: str) -> None:
    p = parola or ""
    if len(p) < PAROLA_MIN:
        raise HTTPException(
            status_code=400,
            detail=f"Parola en az {PAROLA_MIN} karakter olmalıdır.",
        )
    if len(p.encode("utf-8")) > 1024:
        raise HTTPException(status_code=400, detail="Parola çok uzun.")
    if not any(c.isalpha() for c in p) or not any(c.isdigit() for c in p):
        raise HTTPException(
            status_code=400,
            detail="Parola en az bir harf ve bir rakam içermelidir.",
        )
    yerel = eposta.split("@", 1)[0].lower()
    if len(yerel) >= 3 and yerel in p.lower():
        raise HTTPException(
            status_code=400,
            detail="Parola e-posta adresinizi içeremez.",
        )


def _on_hash(parola: str) -> bytes:
    return base64.b64encode(hashlib.sha256(parola.encode("utf-8")).digest())


def parola_hashle(parola: str) -> str:
    with _HASH_KELEPCE:
        return bcrypt.hashpw(_on_hash(parola), bcrypt.gensalt(_BCRYPT_MALIYET)).decode()


def parola_dogrula(parola: str, hash_: Optional[str]) -> bool:
    """Hash yoksa da bcrypt çalıştırır — zamanlamadan hesap sayımı yapılmasın."""
    hedef = (hash_ or "").encode() or _KUKLA_HASH
    with _HASH_KELEPCE:
        try:
            eslesti = bcrypt.checkpw(_on_hash(parola), hedef)
        except ValueError:
            # Bozuk hash — kukla ile aynı süreyi harca, sonra reddet.
            bcrypt.checkpw(_on_hash(parola), _KUKLA_HASH)
            return False
    return bool(eslesti) and hash_ is not None


# ── Token üretimi ────────────────────────────────────────────────────────────

def token_uret() -> tuple[str, str]:
    """(ham, sha256_hex). Ham token yalnızca çereze/e-postaya gider."""
    ham = secrets.token_urlsafe(32)
    return ham, token_hashle(ham)


def token_hashle(ham: str) -> str:
    return hashlib.sha256(ham.encode("utf-8")).hexdigest()


# ── Origin doğrulaması (oturumsuz POST'lar için) ─────────────────────────────

def _izinli_originler() -> set[str]:
    ham = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
    return {o.strip().rstrip("/") for o in ham.split(",") if o.strip()}


def origin_kontrol(request: Request) -> None:
    """Kayıt/giriş gibi henüz oturumu olmayan POST'ları korur.

    Oturumlu isteklerde CSRF jetonu var; burada yok. `ws_utils.check_origin`
    ile aynı mantık: Origin başlığı hiç yoksa istek tarayıcıdan gelmiyordur
    (curl, betik, test) ve geçirilir — CSRF yalnızca tarayıcı kaynaklı bir
    saldırıdır.
    """
    origin = request.headers.get("origin")
    if not origin:
        # Origin yoksa istek muhtemelen tarayıcıdan gelmiyor (curl, betik,
        # test). Yine de modern tarayıcılar `Sec-Fetch-Site` gönderir; varsa
        # ona bak — "cross-site" ise bu bir tarayıcı isteğidir ve reddedilir.
        sfs = request.headers.get("sec-fetch-site")
        if sfs and sfs not in ("same-origin", "same-site", "none"):
            raise HTTPException(status_code=403, detail="İstek kaynağı doğrulanamadı.")
        return
    o = origin.rstrip("/")
    if o in _izinli_originler():
        return
    host = request.headers.get("host", "")
    if host and urlparse(origin).netloc == host:
        return
    raise HTTPException(status_code=403, detail="İstek kaynağı doğrulanamadı.")


# ── Oturum ───────────────────────────────────────────────────────────────────

_GUVENLI_METOTLAR = frozenset({"GET", "HEAD", "OPTIONS"})


def oturum_ac(db: Session, kullanici: Kullanici, request: Request,
              uzun: bool = False) -> tuple[str, str, int]:
    """Yeni oturum satırı açar. (ham_token, csrf, saniye) döndürür.

    Her girişte YENİ token üretilir; saldırganın önceden bildiği bir çereze
    oturum bağlanamaz (session fixation).
    """
    ham, hash_ = token_uret()
    csrf = secrets.token_urlsafe(32)
    sure = timedelta(days=_UZUN_GUN) if uzun else timedelta(hours=_VARSAYILAN_SAAT)

    db.add(Oturum(
        token_hash=hash_,
        csrf=csrf,
        kullanici_id=kullanici.id,
        expires_at=simdi() + sure,
        uzun=uzun,
        ip=istemci_ip(request),
        user_agent=_tek_satir(request.headers.get("user-agent"), 255),
    ))
    # Süresi dolmuş satırlar birikmesin — girişte temizlemek ayrı bir zamanlayıcı
    # gerektirmez ve maliyeti indeksli tek DELETE'tir.
    db.query(Oturum).filter(Oturum.expires_at < simdi()).delete(synchronize_session=False)
    db.commit()

    # Kullanıcı başına oturum tavanı: aksi hâlde bir hesapla sınırsız giriş
    # yapılıp `oturumlar` tablosu şişirilebilirdi.
    fazla = (db.query(Oturum.id)
               .filter(Oturum.kullanici_id == kullanici.id)
               .order_by(Oturum.id.desc())
               .offset(MAKS_OTURUM).all())
    if fazla:
        db.query(Oturum).filter(Oturum.id.in_([f[0] for f in fazla])).delete(
            synchronize_session=False)
        db.commit()
    return ham, csrf, int(sure.total_seconds())


def oturum_kapat(db: Session, ham_token: str) -> None:
    db.query(Oturum).filter(Oturum.token_hash == token_hashle(ham_token)).delete(
        synchronize_session=False)
    db.commit()


def oturumlari_kapat(db: Session, kullanici_id: int, haric_hash: Optional[str] = None) -> int:
    q = db.query(Oturum).filter(Oturum.kullanici_id == kullanici_id)
    if haric_hash:
        q = q.filter(Oturum.token_hash != haric_hash)
    n = q.delete(synchronize_session=False)
    db.commit()
    return n


def _oturum_coz(db: Session, request: Request) -> tuple[Optional[Kullanici], Optional[Oturum]]:
    ham = oturum_cerezi(request)
    if not ham:
        return None, None
    oturum = db.query(Oturum).filter(Oturum.token_hash == token_hashle(ham)).first()
    if oturum is None:
        return None, None
    if naif(oturum.expires_at) is None or naif(oturum.expires_at) < simdi():
        db.delete(oturum)
        db.commit()
        return None, None
    kullanici = db.query(Kullanici).filter(Kullanici.id == oturum.kullanici_id).first()
    # Askıya alınan ya da doğrulaması geri alınan hesabın oturumu ANINDA düşer;
    # JWT yerine sunucu tarafı oturum tutmamızın asıl sebebi bu.
    if kullanici is None or not kullanici.aktif or not kullanici.dogrulandi:
        db.delete(oturum)
        db.commit()
        return None, None
    return kullanici, oturum


# ── Çerezler ─────────────────────────────────────────────────────────────────

def cerez_yaz(response: Response, ham_token: str, csrf: str, saniye: int,
              kalici: bool) -> None:
    guvenli = not _gelistirme_mi()
    ortak = dict(
        # Path="/": doğrulama bağlantısı `/api/...` dışına da yönlendiriyor ve
        # SPA kökten servis ediliyor.
        path="/",
        # Strict: panele dış bağlantıdan girilmiyor, kayıp yok. Lax olsaydı
        # üçüncü taraf sayfadan tetiklenen üst düzey GET'ler çerezi taşırdı.
        samesite="strict",
        secure=guvenli,
        # "Beni hatırla" yoksa max_age verilmez: çerez tarayıcı kapanınca ölür.
        **({"max_age": saniye} if kalici else {}),
    )
    oturum_ad, csrf_ad = cerez_adlari()
    response.set_cookie(oturum_ad, ham_token, httponly=True, **ortak)
    # CSRF çerezi bilerek HttpOnly DEĞİL — JavaScript okuyup başlığa koyacak.
    # Değerin gizliliği önemli değil; önemli olan başka bir origin'in onu
    # OKUYAMAMASI, bunu da Same-Origin Policy sağlıyor.
    response.set_cookie(csrf_ad, csrf, httponly=False, **ortak)


def cerez_sil(response: Response) -> None:
    # Silerken Path/SameSite/Secure yazarkenkiyle BİREBİR aynı olmalı;
    # farklı olursa tarayıcı eski çerezi silmez, çıkış görünüşte olur.
    for ad in cerez_adlari():
        response.delete_cookie(ad, path="/", samesite="strict",
                               secure=not _gelistirme_mi())


# ── İstemci IP ───────────────────────────────────────────────────────────────

def istemci_ip(request: Request) -> str:
    """Denetim kaydı için istemci adresi.

    Uvicorn `--forwarded-allow-ips=127.0.0.1` ile Nginx'in X-Forwarded-For'unu
    `request.client.host`a taşır; Nginx de global conf'ta Cloudflare'in
    `CF-Connecting-IP`'sini gerçek adres olarak çözer. Zincir kopmuşsa
    (doğrudan uvicorn'a bağlanma) 127.0.0.1 görünür — denetim kaydında bu
    yanlış değil, "proxy dışından geldi" demektir.
    """
    return (request.client.host if request.client else "") or "-"


# ── Yetki bağımlılıkları ─────────────────────────────────────────────────────

def mevcut_kullanici(request: Request, db: Session = Depends(get_db)) -> Optional[Kullanici]:
    """Oturum varsa kullanıcıyı döndürür, yoksa None. Uç KORUMAZ.

    Durum değiştiren metotlarda CSRF jetonunu BURADA doğrular — kontrolü tek
    tek uçlara bırakmak, bir tanesini unutmaya davetiye çıkarırdı.
    """
    kullanici, oturum = _oturum_coz(db, request)
    if kullanici is None or oturum is None:
        return None

    if request.method not in _GUVENLI_METOTLAR:
        basliktaki = request.headers.get("x-csrf-token") or ""
        if not basliktaki or not hmac.compare_digest(basliktaki, oturum.csrf or ""):
            raise HTTPException(
                status_code=403,
                detail="Oturum doğrulaması başarısız — sayfayı yenileyip tekrar deneyin.",
            )

    # Kayan yenileme: kalan süre yarıdan azsa uzat. Her istekte yazmak SQLite'ı
    # gereksiz kilitlerdi.
    toplam = timedelta(days=_UZUN_GUN) if oturum.uzun else timedelta(hours=_VARSAYILAN_SAAT)
    if naif(oturum.expires_at) - simdi() < toplam / 2:
        oturum.expires_at = simdi() + toplam
        db.commit()

    request.state.oturum = oturum
    return kullanici


def require_uye(kullanici: Optional[Kullanici] = Depends(mevcut_kullanici)) -> Kullanici:
    if kullanici is None:
        raise HTTPException(
            status_code=401,
            detail="Bu bölümü görüntülemek için giriş yapmalısınız.",
        )
    return kullanici


def require_admin(kullanici: Kullanici = Depends(require_uye)) -> Kullanici:
    if kullanici.rol != "admin":
        raise HTTPException(
            status_code=403,
            detail="Bu işlem yalnızca yöneticiye açıktır.",
        )
    return kullanici


def rol_esitle(kullanici: Kullanici) -> bool:
    """`.env`'deki kurucu admin listesini kullanıcının rolüne yansıtır.

    Listeye sonradan eklenen bir adres bir sonraki girişte yönetici olur;
    listeden çıkarılan, panelden verilmiş yöneticiliğini kaybetmez (onu
    yönetici elle geri alır). Değişiklik varsa True döner.
    """
    if kullanici.email in kurucu_adminler() and kullanici.rol != "admin":
        kullanici.rol = "admin"
        return True
    return False


# ── Denetim kaydı ────────────────────────────────────────────────────────────

def _tek_satir(deger: Optional[str], sinir: int) -> Optional[str]:
    """Log/denetim enjeksiyonu kapısı: satır sonlarını kırp, uzunluğu kelepçele.

    E-posta ve hedef alanları kullanıcıdan geliyor; ham `\n` yazılırsa denetim
    tablosu ekranda sahte satırlar üretir.
    """
    if not deger:
        return None
    temiz = " ".join(str(deger).split())
    return temiz[:sinir] or None


def denetim_yaz(db: Session, eylem: str, *, request: Optional[Request] = None,
                kullanici: Optional[Kullanici] = None, eposta: Optional[str] = None,
                hedef: Optional[str] = None, detay: Optional[str] = None,
                commit: bool = True) -> None:
    """Denetim satırı ekler ve tabloyu `DENETIM_TAVAN` satırda tutar.

    Budama olmasaydı tablo sınırsız büyürdü: başarısız giriş denemeleri de
    kaydediliyor, yani saldırgan doğrudan diski doldurabilirdi.
    """
    db.add(DenetimKaydi(
        kullanici_id=kullanici.id if kullanici else None,
        eposta=_tek_satir(eposta or (kullanici.email if kullanici else None), 254),
        eylem=eylem[:50],
        hedef=_tek_satir(hedef, 200),
        detay=_tek_satir(detay, 2000),
        ip=istemci_ip(request) if request is not None else None,
    ))

    if secrets.randbelow(_BUDAMA_OLASILIGI) == 0:
        esik = (db.query(DenetimKaydi.id)
                  .order_by(DenetimKaydi.id.desc())
                  .offset(DENETIM_TAVAN)
                  .limit(1)
                  .scalar())
        if esik is not None:
            db.query(DenetimKaydi).filter(DenetimKaydi.id <= esik).delete(
                synchronize_session=False)

    if commit:
        db.commit()
