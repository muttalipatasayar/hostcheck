"""Hazır yanıt kütüphanesi — okuma HERKESE AÇIK, yazma Nginx Basic Auth arkasında.

31 Ağustos'ta bu uçlar uygulama içi üyeliğin (kurumsal e-posta ile kayıt)
arkasına alınmıştı; 3 Eylül'de o karar geri alındı. Erişim modeli yeniden
üyelik ÖNCESİNDEKİ hâlinde:

  GET    → herkese açık (teknisyen panelde arama yapar)
  POST / PUT / PATCH / DELETE → Nginx'te `location /api/hazir-yanitlar` içindeki
           `limit_except GET HEAD { auth_basic ... }` bloğu ile korunur.

Yazma korumasının UYGULAMADA karşılığı yoktur; tek kapı Nginx'tir. Backend'i
doğrudan (127.0.0.1:8000 dışında) yayına açmak ya da o `limit_except` bloğunu
düşürmek kütüphaneyi internete yazılabilir bırakır — bkz. `deploy/nginx-hostcheck.conf`.

Üyelikten kalan sertleştirmeler BİLEREK korundu: yazma uçlarındaki rate limit,
`MAX_CONTENT_LEN` ve kategori rengi regex'i erişim denetimi değil, kimlik
doğrulamadan bağımsız kaynak/enjeksiyon korumalarıdır.

`/kategoriler` rotaları `/{yanit_id}`'den ÖNCE tanımlı kalmalı — sıra
bozulursa FastAPI `kategoriler`'i int yol parametresi sanar ve kategori
uçları 422 döndürür.
"""
import json
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import HazirYanit, HazirYanitKategori
from rate_limiter import limiter

# `content` üst sınırsızdı (`Text` + `min_length=1`) ve yazma uçları limitsizdi:
# SQLite dosyası disk dolana kadar büyütülebiliyordu.
MAX_CONTENT_LEN = 20_000

# Kategori rengi doğrudan `style` özniteliğine giriyor; serbest metin
# bırakılırsa CSS enjeksiyonuna açık olur.
_RENK_RE = r"^#[0-9a-fA-F]{6}$"

router = APIRouter(prefix="/api/hazir-yanitlar", tags=["hazir-yanitlar"])

# ── Şemalar ───────────────────────────────────────────────────────────────────

class YanitBase(BaseModel):
    title:    str = Field(..., min_length=1, max_length=200)
    content:  str = Field(..., min_length=1, max_length=MAX_CONTENT_LEN)
    category: str = Field(..., min_length=1, max_length=100)

class YanitCreate(YanitBase):
    pass

class YanitUpdate(BaseModel):
    title:    Optional[str] = Field(None, min_length=1, max_length=200)
    content:  Optional[str] = Field(None, min_length=1, max_length=MAX_CONTENT_LEN)
    category: Optional[str] = Field(None, min_length=1, max_length=100)

class YanitResponse(BaseModel):
    id:        int
    title:     str
    content:   str
    category:  str
    is_pinned: bool
    use_count: int

    class Config:
        from_attributes = True

class KategoriCreate(BaseModel):
    name:  str = Field(..., min_length=1, max_length=100)
    color: str = Field('#6b7388', max_length=20, pattern=_RENK_RE)

class KategoriResponse(BaseModel):
    id:    int
    name:  str
    color: str

    class Config:
        from_attributes = True

# ── Seed: JSON verilerini DB'ye yükle ─────────────────────────────────────────

def seed_if_empty(db: Session):
    """Tablo boşsa hazirYanitlar.json'u yükle.

    Açılışta (`main._yasam_dongusu`) BİR KEZ çağrılır. Eskiden her
    `GET /api/hazir-yanitlar` isteğinde çağrılıyordu; uç yeniden anonime
    açılınca oraya geri taşımak mümkün ama gereksiz — her listeleme isteğinde
    bir `COUNT(*)` demek olurdu.
    """
    if db.query(HazirYanit).count() > 0:
        return
    # Seed verisi backend'in kendi data/ dizininde — frontend kaynak ağacına bağımlı değil
    json_path = os.path.join(os.path.dirname(__file__), "..", "data", "hazirYanitlar.json")
    if not os.path.exists(json_path):
        return
    with open(json_path, encoding="utf-8") as f:
        rows = json.load(f)
    for row in rows:
        db.add(HazirYanit(
            title=row["title"],
            content=row["content"],
            category=row.get("category", "Genel"),
        ))
    db.commit()

# ── Özel kategoriler — ÖNCE tanımlanmalı (/{yanit_id} önce eşleşmesin) ────────

@router.get("/kategoriler", response_model=List[KategoriResponse])
@limiter.limit("60/minute")
def list_kategoriler(request: Request, db: Session = Depends(get_db)):
    return db.query(HazirYanitKategori).order_by(HazirYanitKategori.id.asc()).all()


@router.post("/kategoriler", response_model=KategoriResponse, status_code=201)
@limiter.limit("20/minute")
def create_kategori(request: Request, payload: KategoriCreate,
                    db: Session = Depends(get_db)):
    existing = db.query(HazirYanitKategori).filter(
        HazirYanitKategori.name == payload.name
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Bu kategori zaten mevcut")
    row = HazirYanitKategori(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/kategoriler/{kategori_id}", status_code=204)
@limiter.limit("20/minute")
def delete_kategori(request: Request, kategori_id: int,
                    db: Session = Depends(get_db)):
    row = db.query(HazirYanitKategori).filter(
        HazirYanitKategori.id == kategori_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")
    db.delete(row)
    db.commit()

# ── Yanıtlar ──────────────────────────────────────────────────────────────────

@router.get("", response_model=List[YanitResponse])
@limiter.limit("60/minute")
def list_yanitlar(request: Request, db: Session = Depends(get_db)):
    return db.query(HazirYanit).order_by(HazirYanit.id.asc()).all()


@router.post("", response_model=YanitResponse, status_code=201)
@limiter.limit("20/minute")
def create_yanit(request: Request, payload: YanitCreate,
                 db: Session = Depends(get_db)):
    row = HazirYanit(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{yanit_id}", response_model=YanitResponse)
@limiter.limit("30/minute")
def update_yanit(request: Request, yanit_id: int, payload: YanitUpdate,
                 db: Session = Depends(get_db)):
    row = db.query(HazirYanit).filter(HazirYanit.id == yanit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Yanıt bulunamadı")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{yanit_id}", status_code=204)
@limiter.limit("30/minute")
def delete_yanit(request: Request, yanit_id: int, db: Session = Depends(get_db)):
    row = db.query(HazirYanit).filter(HazirYanit.id == yanit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Yanıt bulunamadı")
    db.delete(row)
    db.commit()


@router.patch("/{yanit_id}/pin", response_model=YanitResponse)
@limiter.limit("60/minute")
def toggle_pin(request: Request, yanit_id: int, db: Session = Depends(get_db)):
    row = db.query(HazirYanit).filter(HazirYanit.id == yanit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Yanıt bulunamadı")
    row.is_pinned = not row.is_pinned
    db.commit()
    db.refresh(row)
    return row


@router.post("/{yanit_id}/use", response_model=YanitResponse)
@limiter.limit("60/minute")
def increment_use(request: Request, yanit_id: int, db: Session = Depends(get_db)):
    """Kullanım sayacı — yanıtı panoya kopyalayan herkes artırır."""
    row = db.query(HazirYanit).filter(HazirYanit.id == yanit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Yanıt bulunamadı")
    row.use_count += 1
    db.commit()
    db.refresh(row)
    return row
