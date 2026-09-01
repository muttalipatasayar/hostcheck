"""Yönetim uçları — yalnızca `rol == "admin"` olan üyeye açık.

Prefix bilerek `/api/admin` DEĞİL: o prefix Nginx'te `auth_basic` ile
korunuyor (SSH/RDP/FTP'nin tarayıcı kimlik penceresini tetiklemek için) ve
yöneticiye ikinci bir parola sorardı.
"""
from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import auth_core as ac
from database import get_db
from models import DenetimKaydi, EpostaTokeni, HazirYanit, Kullanici, Oturum
from rate_limiter import limiter

router = APIRouter(prefix="/api/yonetim", tags=["yonetim"])

SAYFA_BOYUTU_MAKS = 100


# ── Şemalar ──────────────────────────────────────────────────────────────────

class KullaniciSatir(BaseModel):
    id:              int
    ad_soyad:        str
    email:           str
    rol:             str
    aktif:           bool
    dogrulandi:      bool
    kilitli:         bool
    son_giris:       Optional[str] = None
    created_at:      Optional[str] = None
    acik_oturum:     int = 0
    kurucu_admin:    bool = False


class KullaniciListe(BaseModel):
    toplam:  int
    sayfa:   int
    limit:   int
    kayitlar: List[KullaniciSatir]


class KullaniciGuncelle(BaseModel):
    aktif: Optional[bool] = None
    rol:   Optional[str]  = Field(None, pattern="^(uye|admin)$")


class DenetimSatir(BaseModel):
    id:         int
    eylem:      str
    eposta:     Optional[str] = None
    hedef:      Optional[str] = None
    detay:      Optional[str] = None
    ip:         Optional[str] = None
    created_at: Optional[str] = None


class DenetimListe(BaseModel):
    toplam:   int
    sayfa:    int
    limit:    int
    kayitlar: List[DenetimSatir]


def _iso(d) -> Optional[str]:
    return d.isoformat() if d else None


def _satir(k: Kullanici, oturum_sayilari: dict[int, int], kurucular: set[str]) -> KullaniciSatir:
    return KullaniciSatir(
        id=k.id, ad_soyad=k.ad_soyad, email=k.email, rol=k.rol,
        aktif=bool(k.aktif), dogrulandi=bool(k.dogrulandi),
        kilitli=bool(k.kilit_bitis and ac.naif(k.kilit_bitis) > ac.simdi()),
        son_giris=_iso(k.son_giris), created_at=_iso(k.created_at),
        acik_oturum=oturum_sayilari.get(k.id, 0),
        kurucu_admin=k.email in kurucular,
    )


# ── İstatistikler ────────────────────────────────────────────────────────────

@router.get("/istatistik")
@limiter.limit("60/minute")
def istatistik(request: Request, db: Session = Depends(get_db),
               _admin: Kullanici = Depends(ac.require_admin)):
    simdi = ac.simdi()
    yedi_gun = simdi - timedelta(days=7)
    bir_gun = simdi - timedelta(days=1)

    en_cok = (db.query(HazirYanit.title, HazirYanit.category, HazirYanit.use_count)
                .filter(HazirYanit.use_count > 0)
                .order_by(HazirYanit.use_count.desc())
                .limit(5).all())

    return {
        "toplam_uye":      db.query(Kullanici).count(),
        "dogrulanmis":     db.query(Kullanici).filter(Kullanici.dogrulandi.is_(True)).count(),
        "bekleyen":        db.query(Kullanici).filter(Kullanici.dogrulandi.is_(False)).count(),
        "askida":          db.query(Kullanici).filter(Kullanici.aktif.is_(False)).count(),
        "yonetici":        db.query(Kullanici).filter(Kullanici.rol == "admin").count(),
        "acik_oturum":     db.query(Oturum).filter(Oturum.expires_at > simdi).count(),
        "giris_7gun":      db.query(DenetimKaydi).filter(
                               DenetimKaydi.eylem == "giris",
                               DenetimKaydi.created_at >= yedi_gun).count(),
        "basarisiz_24saat": db.query(DenetimKaydi).filter(
                               DenetimKaydi.eylem == "giris_basarisiz",
                               DenetimKaydi.created_at >= bir_gun).count(),
        "toplam_yanit":    db.query(HazirYanit).count(),
        "toplam_kullanim": db.query(func.coalesce(func.sum(HazirYanit.use_count), 0)).scalar() or 0,
        "en_cok_kullanilan": [
            {"baslik": t, "kategori": c, "kullanim": u} for t, c, u in en_cok
        ],
    }


# ── Kullanıcılar ─────────────────────────────────────────────────────────────

@router.get("/kullanicilar", response_model=KullaniciListe)
@limiter.limit("60/minute")
def kullanicilar(request: Request, arama: str = "", durum: str = "hepsi",
                 sayfa: int = 1, limit: int = 25,
                 db: Session = Depends(get_db),
                 _admin: Kullanici = Depends(ac.require_admin)):
    sayfa = max(1, sayfa)
    limit = max(1, min(limit, SAYFA_BOYUTU_MAKS))

    q = db.query(Kullanici)
    if arama.strip():
        # ORM `ilike` parametreli sorgu üretir; `%` ve `_` kaçırılarak
        # kullanıcının tüm tabloyu tarayan bir desen yazması engellenir.
        desen = "%" + arama.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        q = q.filter(Kullanici.email.ilike(desen, escape="\\") |
                     Kullanici.ad_soyad.ilike(desen, escape="\\"))
    if durum == "aktif":
        q = q.filter(Kullanici.aktif.is_(True), Kullanici.dogrulandi.is_(True))
    elif durum == "bekleyen":
        q = q.filter(Kullanici.dogrulandi.is_(False))
    elif durum == "askida":
        q = q.filter(Kullanici.aktif.is_(False))
    elif durum == "yonetici":
        q = q.filter(Kullanici.rol == "admin")

    toplam = q.count()
    satirlar = (q.order_by(Kullanici.created_at.desc(), Kullanici.id.desc())
                 .offset((sayfa - 1) * limit).limit(limit).all())

    # Açık oturum sayıları tek sorguda — satır başına sorgu N+1 üretirdi.
    sayilar = dict(
        db.query(Oturum.kullanici_id, func.count(Oturum.id))
          .filter(Oturum.expires_at > ac.simdi())
          .group_by(Oturum.kullanici_id).all()
    )
    kurucular = ac.kurucu_adminler()
    return KullaniciListe(
        toplam=toplam, sayfa=sayfa, limit=limit,
        kayitlar=[_satir(k, sayilar, kurucular) for k in satirlar],
    )


def _hedef(db: Session, kullanici_id: int) -> Kullanici:
    k = db.query(Kullanici).filter(Kullanici.id == kullanici_id).first()
    if k is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    return k


@router.patch("/kullanicilar/{kullanici_id}", response_model=KullaniciSatir)
@limiter.limit("30/minute")
def kullanici_guncelle(request: Request, kullanici_id: int, payload: KullaniciGuncelle,
                       db: Session = Depends(get_db),
                       admin: Kullanici = Depends(ac.require_admin)):
    hedef = _hedef(db, kullanici_id)

    # Yönetici kendi yetkisini elinden alamaz: son yönetici kendini "uye"
    # yaparsa panelin yönetim tarafı kimseye açılmaz hâle gelirdi.
    if hedef.id == admin.id and (payload.rol is not None or payload.aktif is False):
        raise HTTPException(
            status_code=400,
            detail="Kendi hesabınızın rolünü veya erişimini değiştiremezsiniz.",
        )
    # `.env`'de tanımlı kurucu yönetici panelden düşürülemez; aksi hâlde iki
    # yönetici birbirini düşürüp sistemi yönetilemez bırakabilirdi.
    if hedef.email in ac.kurucu_adminler() and (payload.rol == "uye" or payload.aktif is False):
        raise HTTPException(
            status_code=400,
            detail="Bu hesap sunucu yapılandırmasında yönetici olarak tanımlı; panelden değiştirilemez.",
        )

    degisenler = []
    if payload.aktif is not None and bool(hedef.aktif) != payload.aktif:
        hedef.aktif = payload.aktif
        degisenler.append("aktif=" + ("evet" if payload.aktif else "hayır"))
        if not payload.aktif:
            # Askıya alınan hesabın açık oturumları ANINDA düşmeli.
            ac.oturumlari_kapat(db, hedef.id)
    if payload.rol is not None and hedef.rol != payload.rol:
        hedef.rol = payload.rol
        degisenler.append("rol=" + payload.rol)

    if degisenler:
        ac.denetim_yaz(db, "kullanici_guncelle", request=request, kullanici=admin,
                       hedef=f"kullanici:{hedef.id}",
                       detay=f"{hedef.email} → {', '.join(degisenler)}")
    else:
        db.commit()

    sayilar = dict(
        db.query(Oturum.kullanici_id, func.count(Oturum.id))
          .filter(Oturum.kullanici_id == hedef.id, Oturum.expires_at > ac.simdi())
          .group_by(Oturum.kullanici_id).all()
    )
    return _satir(hedef, sayilar, ac.kurucu_adminler())


@router.delete("/kullanicilar/{kullanici_id}", status_code=204)
@limiter.limit("20/minute")
def kullanici_sil(request: Request, kullanici_id: int, db: Session = Depends(get_db),
                  admin: Kullanici = Depends(ac.require_admin)):
    hedef = _hedef(db, kullanici_id)
    if hedef.id == admin.id:
        raise HTTPException(status_code=400, detail="Kendi hesabınızı silemezsiniz.")
    if hedef.email in ac.kurucu_adminler():
        raise HTTPException(
            status_code=400,
            detail="Sunucu yapılandırmasında tanımlı yönetici hesabı silinemez.",
        )

    eposta = hedef.email
    # `PRAGMA foreign_keys=ON` (database.py) CASCADE'i çalıştırıyor, ama
    # bağımlıları açıkça silmek pragmanın ileride kapanma ihtimaline karşı
    # öksüz satır bırakmaz.
    db.query(Oturum).filter(Oturum.kullanici_id == hedef.id).delete(synchronize_session=False)
    db.query(EpostaTokeni).filter(EpostaTokeni.kullanici_id == hedef.id).delete(
        synchronize_session=False)
    db.delete(hedef)
    db.commit()
    # Denetim satırı silinen kullanıcıdan SONRA yazılır ve `kullanici_id`
    # taşımaz; `eposta` alanı sayesinde iz yine de okunabilir kalır.
    ac.denetim_yaz(db, "kullanici_sil", request=request, kullanici=admin,
                   hedef=f"kullanici:{kullanici_id}", detay=eposta)


@router.post("/kullanicilar/{kullanici_id}/oturumlari-kapat")
@limiter.limit("20/minute")
def oturumlari_kapat(request: Request, kullanici_id: int, db: Session = Depends(get_db),
                     admin: Kullanici = Depends(ac.require_admin)):
    hedef = _hedef(db, kullanici_id)
    n = ac.oturumlari_kapat(db, hedef.id)
    ac.denetim_yaz(db, "oturum_kapat_yonetici", request=request, kullanici=admin,
                   hedef=f"kullanici:{hedef.id}", detay=f"{hedef.email} · {n} oturum")
    return {"mesaj": f"{hedef.email} için {n} oturum kapatıldı.", "kapatilan": n}


# ── Denetim kaydı ────────────────────────────────────────────────────────────

@router.get("/denetim", response_model=DenetimListe)
@limiter.limit("60/minute")
def denetim(request: Request, eylem: str = "", sayfa: int = 1, limit: int = 50,
            db: Session = Depends(get_db),
            _admin: Kullanici = Depends(ac.require_admin)):
    sayfa = max(1, sayfa)
    limit = max(1, min(limit, SAYFA_BOYUTU_MAKS))

    q = db.query(DenetimKaydi)
    if eylem.strip():
        q = q.filter(DenetimKaydi.eylem == eylem.strip()[:50])
    toplam = q.count()
    satirlar = (q.order_by(DenetimKaydi.id.desc())
                 .offset((sayfa - 1) * limit).limit(limit).all())
    return DenetimListe(
        toplam=toplam, sayfa=sayfa, limit=limit,
        kayitlar=[
            DenetimSatir(id=d.id, eylem=d.eylem, eposta=d.eposta, hedef=d.hedef,
                         detay=d.detay, ip=d.ip, created_at=_iso(d.created_at))
            for d in satirlar
        ],
    )


@router.get("/denetim/eylemler", response_model=List[str])
@limiter.limit("30/minute")
def denetim_eylemleri(request: Request, db: Session = Depends(get_db),
                      _admin: Kullanici = Depends(ac.require_admin)):
    """Filtre açılır listesini besler — sabit liste tutmak yeni eylem
    eklendiğinde güncellemeyi unutturuyordu."""
    return [e[0] for e in db.query(DenetimKaydi.eylem).distinct()
                            .order_by(DenetimKaydi.eylem.asc()).all()]
