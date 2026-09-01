"""Ölçüm geçmişinin saklanması ve karşılaştırılması.

Aracın asıl sorusu "site yavaş mı" değil, "yaptığım optimizasyon işe yaradı
mı". Bunu ancak önceki ölçümle karşılaştırarak cevaplayabiliriz.
"""

import json

from sqlalchemy import desc
from sqlalchemy.orm import Session

from models import SiteHiziOlcum

# Domain + strateji başına tutulacak en fazla kayıt. Sınırsız bırakılırsa
# tablo tek bir alan adı için bile sürekli büyür (projedeki diğer süreç içi
# depolarda görülen sorunun kalıcı hâli olurdu).
_MAX_KAYIT = 50


def kaydet(db: Session, domain: str, strategy: str, sonuc: dict,
           motor: str = "yerel") -> SiteHiziOlcum:
    """Bir ölçümü kaydeder ve eski kayıtları budar."""
    m = sonuc.get("metrikler") or {}
    ozet = {
        "skor": sonuc.get("skor"),
        "metrikler": m,
        "denetim_ozeti": [
            {"id": d.get("id"), "durum": d.get("durum"), "deger": d.get("deger")}
            for d in (sonuc.get("denetimler") or [])
        ],
    }

    kayit = SiteHiziOlcum(
        domain=domain,
        strategy=strategy,
        motor=motor,
        score=int(sonuc.get("skor") or 0),
        fcp_ms=_int(m.get("fcp_ms")),
        lcp_ms=_int(m.get("lcp_ms")),
        tbt_ms=_int(m.get("tbt_ms")),
        ttfb_ms=_int(m.get("ttfb_ms")),
        cls=_float(m.get("cls")),
        toplam_bayt=_int(sonuc.get("toplam_bayt")),
        istek_sayisi=_int(sonuc.get("kaynak_sayisi")),
        ozet_json=json.dumps(ozet, ensure_ascii=False),
    )
    db.add(kayit)
    db.commit()
    db.refresh(kayit)
    _buda(db, domain, strategy)
    return kayit


def _buda(db: Session, domain: str, strategy: str) -> None:
    fazla = (db.query(SiteHiziOlcum.id)
               .filter(SiteHiziOlcum.domain == domain,
                       SiteHiziOlcum.strategy == strategy)
               .order_by(desc(SiteHiziOlcum.created_at), desc(SiteHiziOlcum.id))
               .offset(_MAX_KAYIT).all())
    if not fazla:
        return
    db.query(SiteHiziOlcum).filter(
        SiteHiziOlcum.id.in_([f[0] for f in fazla])).delete(synchronize_session=False)
    db.commit()


def gecmis(db: Session, domain: str, strategy: str | None = None,
           limit: int = 20) -> list[dict]:
    q = db.query(SiteHiziOlcum).filter(SiteHiziOlcum.domain == domain)
    if strategy:
        q = q.filter(SiteHiziOlcum.strategy == strategy)
    kayitlar = (q.order_by(desc(SiteHiziOlcum.created_at), desc(SiteHiziOlcum.id))
                  .limit(limit).all())
    return [_serile(k) for k in kayitlar]


def onceki(db: Session, domain: str, strategy: str, haric_id: int | None = None) -> dict | None:
    """Karşılaştırma için bir önceki ölçüm."""
    q = db.query(SiteHiziOlcum).filter(SiteHiziOlcum.domain == domain,
                                       SiteHiziOlcum.strategy == strategy)
    if haric_id is not None:
        q = q.filter(SiteHiziOlcum.id != haric_id)
    k = q.order_by(desc(SiteHiziOlcum.created_at), desc(SiteHiziOlcum.id)).first()
    return _serile(k) if k else None


def karsilastir(guncel: dict, gecmis_kayit: dict | None) -> dict | None:
    """İki ölçüm arasındaki farkı yüzde ve yön olarak çıkarır.

    Süre metriklerinde AZALMA iyidir, skorda ARTIŞ iyidir — `iyilesme`
    alanı bu farkı normalize eder ki arayüz tek kurala göre renk versin.
    """
    if not gecmis_kayit:
        return None

    farklar = {}
    for alan, dusus_iyi in (("skor", False), ("lcp_ms", True), ("fcp_ms", True),
                            ("tbt_ms", True), ("ttfb_ms", True), ("cls", True)):
        yeni = guncel.get("metrikler", {}).get(alan) if alan != "skor" else guncel.get("skor")
        eski = gecmis_kayit.get("metrikler", {}).get(alan) if alan != "skor" else gecmis_kayit.get("skor")
        if yeni is None or eski is None:
            continue
        fark = yeni - eski
        yuzde = (fark / eski * 100) if eski else 0.0
        farklar[alan] = {
            "eski": eski,
            "yeni": yeni,
            "fark": round(fark, 4),
            "yuzde": round(yuzde, 1),
            "iyilesme": (fark < 0) if dusus_iyi else (fark > 0),
            "degisti": abs(yuzde) >= 3,     # %3'ün altı ölçüm gürültüsüdür
        }

    return {"onceki_zaman": gecmis_kayit.get("zaman"), "farklar": farklar}


def _serile(k: SiteHiziOlcum) -> dict:
    return {
        "id": k.id,
        "domain": k.domain,
        "strategy": k.strategy,
        "motor": k.motor,
        "skor": k.score,
        "metrikler": {
            "fcp_ms": k.fcp_ms, "lcp_ms": k.lcp_ms, "tbt_ms": k.tbt_ms,
            "ttfb_ms": k.ttfb_ms, "cls": k.cls,
        },
        "toplam_bayt": k.toplam_bayt,
        "kaynak_sayisi": k.istek_sayisi,
        "zaman": k.created_at.isoformat() if k.created_at else None,
    }


def _int(v):
    try:
        return int(round(float(v))) if v is not None else None
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None
