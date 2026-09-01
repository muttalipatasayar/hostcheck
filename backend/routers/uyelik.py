"""Üyelik uçları — kayıt, doğrulama, giriş, profil, parola.

Tasarım notları:

* **Hesap sayımı (enumeration) kapalı.** `/kayit` ve `/sifre-unuttum` adresin
  kayıtlı olup olmadığına bakmaksızın AYNI yanıtı verir; fark yalnızca gerçek
  adres sahibine giden e-postada görünür. Tek istisna alan adı reddidir:
  kullanıcı neden kabul edilmediğini bilmek zorunda (ürün gereksinimi) ve bu
  bilgi zaten hesap varlığını sızdırmıyor.
* **Kaba kuvvete iki katman.** IP başına slowapi limiti + hesap başına kilit.
  IP değiştirilebilir, hedef hesap değiştirilemez.
* **Çerezler `auth_core` üzerinden yazılır**; HttpOnly/Secure/SameSite
  kararları tek yerde durur.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import auth_core as ac
import mailer
from database import get_db
from models import EpostaTokeni, Kullanici, Oturum
from rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/uyelik", tags=["uyelik"])

# Ad-soyad serbest metin ve hem e-postaya hem arayüze giriyor.
#
# Yasaklı küme dar tutuldu: `< > " \ ` ` ve kontrol karakterleri. Kesme
# işareti (O'Brien) ve `&` BİLEREK serbest — team.blue tarafında bunlar
# meşru isimlerde geçiyor ve her iki çıkış noktası da zaten kaçırıyor:
# React metni otomatik, `mailer._kacis()` HTML gövdesini açıkça.
_AD_RE = re.compile(r"^[^\x00-\x1f<>\"`\\]{2,120}$")

# Kayıt/sıfırlama uçlarının değişmez yanıtı.
_GENEL_KAYIT = ("Kaydınız alındı. E-posta adresinize bir doğrulama bağlantısı "
                "gönderildi; gelen kutunuzu (ve spam klasörünü) kontrol edin.")
_GENEL_SIFRE = ("Adres kayıtlıysa parola sıfırlama bağlantısı gönderildi. "
                "Gelen kutunuzu kontrol edin.")


# ── Şemalar ──────────────────────────────────────────────────────────────────

class KayitIstek(BaseModel):
    ad_soyad: str = Field(..., min_length=2, max_length=120)
    email:    str = Field(..., min_length=5, max_length=254)
    parola:   str = Field(..., min_length=1, max_length=1024)


class GirisIstek(BaseModel):
    email:         str  = Field(..., min_length=5, max_length=254)
    parola:        str  = Field(..., min_length=1, max_length=1024)
    beni_hatirla:  bool = False


class EpostaIstek(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)


class SifreSifirlaIstek(BaseModel):
    token:      str = Field(..., min_length=10, max_length=200)
    yeni_parola: str = Field(..., min_length=1, max_length=1024)


class SifreDegistirIstek(BaseModel):
    mevcut_parola: str = Field(..., min_length=1, max_length=1024)
    yeni_parola:   str = Field(..., min_length=1, max_length=1024)


class ProfilIstek(BaseModel):
    ad_soyad: str = Field(..., min_length=2, max_length=120)


class KullaniciYanit(BaseModel):
    id:        int
    ad_soyad:  str
    email:     str
    rol:       str
    son_giris: Optional[str] = None


class OturumYanit(BaseModel):
    id:         int
    ip:         Optional[str] = None
    user_agent: Optional[str] = None
    created_at: Optional[str] = None
    bu_oturum:  bool = False


def _kullanici_yanit(k: Kullanici) -> KullaniciYanit:
    """Yanıt gövdesini elle kurar — `from_attributes` ile model dökülseydi
    `sifre_hash` gibi alanların dışarı sızması bir alan ekleme hatası kadar
    yakın olurdu."""
    return KullaniciYanit(
        id=k.id, ad_soyad=k.ad_soyad, email=k.email, rol=k.rol,
        son_giris=k.son_giris.isoformat() if k.son_giris else None,
    )


def _ad_dogrula(ham: str) -> str:
    ad = (ham or "").strip()
    if not _AD_RE.match(ad):
        raise HTTPException(
            status_code=400,
            detail="Ad soyad 2-120 karakter olmalı ve özel işaret içermemelidir.",
        )
    return ad


def _token_olustur(db: Session, kullanici: Kullanici, amac: str,
                   sure: timedelta) -> str:
    """Aynı amaçlı eski tokenleri geçersizleştirip yenisini üretir."""
    db.query(EpostaTokeni).filter(
        EpostaTokeni.kullanici_id == kullanici.id,
        EpostaTokeni.amac == amac,
        EpostaTokeni.kullanildi_at.is_(None),
    ).delete(synchronize_session=False)
    ham, hash_ = ac.token_uret()
    db.add(EpostaTokeni(
        token_hash=hash_, kullanici_id=kullanici.id, amac=amac,
        expires_at=ac.simdi() + sure,
    ))
    db.commit()
    return ham


# ── Genel ayarlar ────────────────────────────────────────────────────────────

@router.get("/ayarlar")
@limiter.limit("60/minute")
def ayarlar(request: Request):
    """Arayüzün uyarı metnini kurabilmesi için izinli alan adları.

    Listeyi frontend'e sabitlemek yerine buradan okutmak, `.env` değiştiğinde
    arayüzün yanlış alan adı yazmasını engeller.
    """
    return {
        "izinli_alanlar": ac.izinli_alanlar(),
        "kayit_acik": True,
        "parola_min": ac.PAROLA_MIN,
    }


# ── Kayıt ve doğrulama ───────────────────────────────────────────────────────

@router.post("/kayit", status_code=202)
@limiter.limit("3/minute")
async def kayit(request: Request, payload: KayitIstek, db: Session = Depends(get_db)):
    ac.origin_kontrol(request)

    eposta = ac.eposta_normalize(payload.email)
    ac.alan_kontrol(eposta)                 # açık ret — ürün gereksinimi
    ad_soyad = _ad_dogrula(payload.ad_soyad)
    ac.parola_politikasi(payload.parola, eposta)

    mevcut = db.query(Kullanici).filter(Kullanici.email == eposta).first()

    if mevcut is not None:
        if mevcut.dogrulandi:
            # Hesap var: yanıt değişmez, bilgi yalnızca adresin sahibine gider.
            ac.denetim_yaz(db, "kayit_tekrar", request=request, kullanici=mevcut)
            try:
                await mailer.zaten_kayitli_maili(mevcut.email, mevcut.ad_soyad)
            except HTTPException:
                logger.warning("Bilgilendirme maili gönderilemedi.")
            return {"mesaj": _GENEL_KAYIT}
        # Doğrulanmamış hesap: adı/parolayı tazele ve yeni bağlantı yolla.
        mevcut.ad_soyad = ad_soyad
        mevcut.sifre_hash = await asyncio.to_thread(ac.parola_hashle, payload.parola)
        db.commit()
        kullanici = mevcut
    else:
        # bcrypt ~300 ms saf CPU harcar; `async def` içinde doğrudan
        # çağrılsaydı tek event loop'u o süre boyunca kilitlerdi.
        kullanici = Kullanici(
            email=eposta,
            ad_soyad=ad_soyad,
            sifre_hash=await asyncio.to_thread(ac.parola_hashle, payload.parola),
            dogrulandi=False,
            aktif=True,
            rol="admin" if eposta in ac.kurucu_adminler() else "uye",
        )
        db.add(kullanici)
        db.commit()
        db.refresh(kullanici)

    ham = _token_olustur(db, kullanici, "dogrulama",
                         timedelta(hours=ac.DOGRULAMA_SAAT))
    ac.denetim_yaz(db, "kayit", request=request, kullanici=kullanici)
    await mailer.dogrulama_maili(kullanici.email, kullanici.ad_soyad, ham)
    return {"mesaj": _GENEL_KAYIT}


@router.get("/dogrula")
@limiter.limit("10/minute")
async def dogrula(request: Request, token: str = "", db: Session = Depends(get_db)):
    """E-postadaki bağlantı. Sonuç SPA'ya sorgu parametresiyle bildirilir.

    Yönlendirme hedefi SABİT ve GÖRELİ — kullanıcıdan gelen hiçbir değer
    hedefe girmiyor, dolayısıyla açık yönlendirme yok.
    """
    def _git(durum: str) -> RedirectResponse:
        return RedirectResponse(url=f"/?dogrulama={durum}", status_code=303)

    if not token or len(token) > 200:
        return _git("gecersiz")

    kayit_ = db.query(EpostaTokeni).filter(
        EpostaTokeni.token_hash == ac.token_hashle(token),
        EpostaTokeni.amac == "dogrulama",
    ).first()
    if kayit_ is None:
        return _git("gecersiz")
    if ac.naif(kayit_.expires_at) < ac.simdi():
        return _git("suresi-doldu")

    kullanici = db.query(Kullanici).filter(Kullanici.id == kayit_.kullanici_id).first()
    if kullanici is None:
        return _git("gecersiz")

    # TOKEN SÜRESİ DOLANA KADAR TEKRAR KULLANILABİLİR — bilerek.
    #
    # natro.com Microsoft 365 üzerindeyse Safe Links/ATP, kullanıcı tıklamadan
    # ÖNCE bağlantıyı açar. Tek kullanımlık katı davransaydı tarayıcı token'ı
    # yakar, gerçek kullanıcı "geçersiz bağlantı" görürdü — sistemin en sık
    # kırılacağı yer burasıydı. Tekrar çağrı yalnızca aynı hesabı yeniden
    # "doğrulandı" yapar; ek yetki vermez, oturum açmaz.
    if kayit_.kullanildi_at is not None and kullanici.dogrulandi:
        return _git("ok")

    ilk_dogrulama = not kullanici.dogrulandi
    kullanici.dogrulandi = True
    ac.rol_esitle(kullanici)
    kayit_.kullanildi_at = ac.simdi()
    ac.denetim_yaz(db, "dogrulama", request=request, kullanici=kullanici)

    if ilk_dogrulama:
        for admin_eposta in ac.kurucu_adminler():
            if admin_eposta == kullanici.email:
                continue
            try:
                await mailer.yeni_uye_bildirimi(admin_eposta, kullanici.ad_soyad,
                                                kullanici.email)
            except HTTPException:
                logger.warning("Yönetici bildirimi gönderilemedi.")
    return _git("ok")


@router.post("/dogrulama-tekrar", status_code=202)
@limiter.limit("2/minute")
async def dogrulama_tekrar(request: Request, payload: EpostaIstek,
                           db: Session = Depends(get_db)):
    ac.origin_kontrol(request)
    eposta = ac.eposta_normalize(payload.email)
    kullanici = db.query(Kullanici).filter(Kullanici.email == eposta).first()
    if kullanici is not None and not kullanici.dogrulandi and kullanici.aktif:
        ham = _token_olustur(db, kullanici, "dogrulama",
                             timedelta(hours=ac.DOGRULAMA_SAAT))
        await mailer.dogrulama_maili(kullanici.email, kullanici.ad_soyad, ham)
    return {"mesaj": _GENEL_KAYIT}


# ── Giriş / çıkış ────────────────────────────────────────────────────────────

@router.post("/giris", response_model=KullaniciYanit)
# IP başına 5/dk fazla sıkıydı: Natro çalışanları tek kurumsal NAT arkasından
# geliyor, bir kişinin hatalı denemeleri tüm ekibi kilitlerdi. Asıl kaba kuvvet
# freni HESAP BAZLI kilit (MAKS_BASARISIZ); buradaki limit sadece kaba bir tavan.
@limiter.limit("20/minute")
def giris(request: Request, response: Response, payload: GirisIstek,
          db: Session = Depends(get_db)):
    ac.origin_kontrol(request)
    eposta = ac.eposta_normalize(payload.email)
    kullanici = db.query(Kullanici).filter(Kullanici.email == eposta).first()

    kilitli = (kullanici is not None and kullanici.kilit_bitis is not None
               and ac.naif(kullanici.kilit_bitis) > ac.simdi())

    # Parola kontrolü kilitliyken de ÇALIŞTIRILIR: aksi hâlde yanıt süresi
    # "bu hesap kilitli" bilgisini sızdırırdı.
    dogru = ac.parola_dogrula(payload.parola,
                              kullanici.sifre_hash if kullanici else None)

    if kilitli:
        kalan = int((ac.naif(kullanici.kilit_bitis) - ac.simdi()).total_seconds() // 60) + 1
        ac.denetim_yaz(db, "giris_kilitli", request=request, kullanici=kullanici)
        raise HTTPException(
            status_code=429,
            detail=(f"Çok fazla hatalı deneme yapıldı. Hesabınız {kalan} dakika "
                    "boyunca girişe kapalı."),
        )

    if kullanici is None or not dogru:
        if kullanici is not None:
            kullanici.basarisiz_giris = (kullanici.basarisiz_giris or 0) + 1
            if kullanici.basarisiz_giris >= ac.MAKS_BASARISIZ:
                kullanici.kilit_bitis = ac.simdi() + timedelta(minutes=ac.KILIT_DAKIKA)
                kullanici.basarisiz_giris = 0
            ac.denetim_yaz(db, "giris_basarisiz", request=request, kullanici=kullanici)
        else:
            ac.denetim_yaz(db, "giris_basarisiz", request=request, eposta=eposta)
        # Bilinmeyen adres ve yanlış parola AYNI yanıtı alır.
        raise HTTPException(status_code=401, detail="E-posta veya parola hatalı.")

    if not kullanici.aktif:
        ac.denetim_yaz(db, "giris_askida", request=request, kullanici=kullanici)
        raise HTTPException(
            status_code=403,
            detail="Hesabınız askıya alınmış. Yönetici ile iletişime geçin.",
        )
    if not kullanici.dogrulandi:
        raise HTTPException(
            status_code=403,
            detail=("E-posta adresiniz henüz doğrulanmadı. Gelen kutunuzdaki "
                    "bağlantıya tıklayın veya yeni bağlantı isteyin."),
        )

    kullanici.basarisiz_giris = 0
    kullanici.kilit_bitis = None
    kullanici.son_giris = ac.simdi()
    ac.rol_esitle(kullanici)
    db.commit()

    ham, csrf, saniye = ac.oturum_ac(db, kullanici, request, uzun=payload.beni_hatirla)
    ac.cerez_yaz(response, ham, csrf, saniye, kalici=payload.beni_hatirla)
    ac.denetim_yaz(db, "giris", request=request, kullanici=kullanici)
    return _kullanici_yanit(kullanici)


@router.post("/cikis")
@limiter.limit("30/minute")
def cikis(request: Request, response: Response,
          kullanici: Optional[Kullanici] = Depends(ac.mevcut_kullanici),
          db: Session = Depends(get_db)):
    ham = ac.oturum_cerezi(request)
    if ham:
        ac.oturum_kapat(db, ham)
    if kullanici is not None:
        ac.denetim_yaz(db, "cikis", request=request, kullanici=kullanici)
    ac.cerez_sil(response)
    return {"mesaj": "Çıkış yapıldı."}


@router.get("/ben", response_model=KullaniciYanit)
@limiter.limit("120/minute")
def ben(request: Request, kullanici: Kullanici = Depends(ac.require_uye)):
    return _kullanici_yanit(kullanici)


# ── Parola ───────────────────────────────────────────────────────────────────

@router.post("/sifre-unuttum", status_code=202)
@limiter.limit("2/minute")
async def sifre_unuttum(request: Request, payload: EpostaIstek,
                        db: Session = Depends(get_db)):
    ac.origin_kontrol(request)
    eposta = ac.eposta_normalize(payload.email)
    kullanici = db.query(Kullanici).filter(Kullanici.email == eposta).first()
    if kullanici is not None and kullanici.aktif and kullanici.dogrulandi:
        ham = _token_olustur(db, kullanici, "sifre",
                             timedelta(minutes=ac.SIFRE_SIFIRLAMA_DAKIKA))
        ac.denetim_yaz(db, "sifre_sifirlama_istek", request=request, kullanici=kullanici)
        await mailer.sifre_sifirlama_maili(kullanici.email, kullanici.ad_soyad, ham)
    return {"mesaj": _GENEL_SIFRE}


@router.post("/sifre-sifirla")
@limiter.limit("5/minute")
def sifre_sifirla(request: Request, payload: SifreSifirlaIstek,
                  db: Session = Depends(get_db)):
    ac.origin_kontrol(request)
    kayit_ = db.query(EpostaTokeni).filter(
        EpostaTokeni.token_hash == ac.token_hashle(payload.token),
        EpostaTokeni.amac == "sifre",
    ).first()
    if kayit_ is None or kayit_.kullanildi_at is not None or \
            ac.naif(kayit_.expires_at) < ac.simdi():
        raise HTTPException(
            status_code=400,
            detail="Bağlantı geçersiz veya süresi dolmuş. Yeni bir bağlantı isteyin.",
        )
    kullanici = db.query(Kullanici).filter(Kullanici.id == kayit_.kullanici_id).first()
    if kullanici is None or not kullanici.aktif:
        raise HTTPException(status_code=400, detail="Bağlantı geçersiz.")

    ac.parola_politikasi(payload.yeni_parola, kullanici.email)
    kullanici.sifre_hash = ac.parola_hashle(payload.yeni_parola)
    kullanici.basarisiz_giris = 0
    kullanici.kilit_bitis = None
    kayit_.kullanildi_at = ac.simdi()
    ac.denetim_yaz(db, "sifre_sifirlandi", request=request, kullanici=kullanici)
    # Parola değiştiyse eski oturumlar da düşmeli — hesap ele geçirilmişse
    # saldırganın açık oturumu bu adımda kopar.
    ac.oturumlari_kapat(db, kullanici.id)
    return {"mesaj": "Parolanız güncellendi. Yeni parolanızla giriş yapabilirsiniz."}


@router.post("/sifre-degistir")
@limiter.limit("5/minute")
def sifre_degistir(request: Request, response: Response, payload: SifreDegistirIstek,
                   kullanici: Kullanici = Depends(ac.require_uye),
                   db: Session = Depends(get_db)):
    if not ac.parola_dogrula(payload.mevcut_parola, kullanici.sifre_hash):
        raise HTTPException(status_code=400, detail="Mevcut parolanız hatalı.")
    ac.parola_politikasi(payload.yeni_parola, kullanici.email)
    kullanici.sifre_hash = ac.parola_hashle(payload.yeni_parola)
    ac.denetim_yaz(db, "sifre_degistirildi", request=request, kullanici=kullanici)

    # Tüm oturumlar düşer, ardından bu cihaza yenisi verilir: kullanıcı
    # oturumunu kaybetmez ama diğer cihazlar çıkış yapmış olur.
    ac.oturumlari_kapat(db, kullanici.id)
    ham, csrf, saniye = ac.oturum_ac(db, kullanici, request)
    ac.cerez_yaz(response, ham, csrf, saniye, kalici=False)
    return {"mesaj": "Parolanız güncellendi. Diğer cihazlardaki oturumlar kapatıldı."}


# ── Profil ve oturumlar ──────────────────────────────────────────────────────

@router.patch("/profil", response_model=KullaniciYanit)
@limiter.limit("10/minute")
def profil_guncelle(request: Request, payload: ProfilIstek,
                    kullanici: Kullanici = Depends(ac.require_uye),
                    db: Session = Depends(get_db)):
    kullanici.ad_soyad = _ad_dogrula(payload.ad_soyad)
    ac.denetim_yaz(db, "profil_guncelle", request=request, kullanici=kullanici)
    return _kullanici_yanit(kullanici)


@router.get("/oturumlarim", response_model=list[OturumYanit])
@limiter.limit("30/minute")
def oturumlarim(request: Request, kullanici: Kullanici = Depends(ac.require_uye),
                db: Session = Depends(get_db)):
    bu_hash = ac.token_hashle(ac.oturum_cerezi(request))
    satirlar = (db.query(Oturum)
                  .filter(Oturum.kullanici_id == kullanici.id)
                  .order_by(Oturum.created_at.desc())
                  .limit(50).all())
    return [
        OturumYanit(
            id=o.id, ip=o.ip, user_agent=o.user_agent,
            created_at=o.created_at.isoformat() if o.created_at else None,
            bu_oturum=(o.token_hash == bu_hash),
        )
        for o in satirlar
    ]


@router.post("/oturumlarimi-kapat")
@limiter.limit("10/minute")
def oturumlarimi_kapat(request: Request, kullanici: Kullanici = Depends(ac.require_uye),
                       db: Session = Depends(get_db)):
    bu_hash = ac.token_hashle(ac.oturum_cerezi(request))
    n = ac.oturumlari_kapat(db, kullanici.id, haric_hash=bu_hash)
    ac.denetim_yaz(db, "oturumlar_kapatildi", request=request, kullanici=kullanici,
                   detay=f"{n} oturum")
    return {"mesaj": f"{n} oturum kapatıldı.", "kapatilan": n}
