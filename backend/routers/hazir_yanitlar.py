import json
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import HazirYanit, HazirYanitKategori

router = APIRouter(prefix="/api/hazir-yanitlar", tags=["hazir-yanitlar"])

# ── Şemalar ───────────────────────────────────────────────────────────────────

class YanitBase(BaseModel):
    title:    str = Field(..., min_length=1, max_length=200)
    content:  str = Field(..., min_length=1)
    category: str = Field(..., min_length=1, max_length=100)

class YanitCreate(YanitBase):
    pass

class YanitUpdate(BaseModel):
    title:    Optional[str] = Field(None, min_length=1, max_length=200)
    content:  Optional[str] = Field(None, min_length=1)
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
    color: str = Field('#6b7388', max_length=20)

class KategoriResponse(BaseModel):
    id:    int
    name:  str
    color: str

    class Config:
        from_attributes = True

# ── Seed: JSON verilerini DB'ye yükle ─────────────────────────────────────────

def seed_if_empty(db: Session):
    """Tablo boşsa hazirYanitlar.json'u yükle."""
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
def list_kategoriler(db: Session = Depends(get_db)):
    return db.query(HazirYanitKategori).order_by(HazirYanitKategori.id.asc()).all()


@router.post("/kategoriler", response_model=KategoriResponse, status_code=201)
def create_kategori(payload: KategoriCreate, db: Session = Depends(get_db)):
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
def delete_kategori(kategori_id: int, db: Session = Depends(get_db)):
    row = db.query(HazirYanitKategori).filter(
        HazirYanitKategori.id == kategori_id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Kategori bulunamadı")
    db.delete(row)
    db.commit()

# ── Yanıtlar ──────────────────────────────────────────────────────────────────

@router.get("", response_model=List[YanitResponse])
def list_yanitlar(db: Session = Depends(get_db)):
    seed_if_empty(db)
    return db.query(HazirYanit).order_by(HazirYanit.id.asc()).all()


@router.post("", response_model=YanitResponse, status_code=201)
def create_yanit(payload: YanitCreate, db: Session = Depends(get_db)):
    row = HazirYanit(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/{yanit_id}", response_model=YanitResponse)
def update_yanit(yanit_id: int, payload: YanitUpdate, db: Session = Depends(get_db)):
    row = db.query(HazirYanit).filter(HazirYanit.id == yanit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Yanıt bulunamadı")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{yanit_id}", status_code=204)
def delete_yanit(yanit_id: int, db: Session = Depends(get_db)):
    row = db.query(HazirYanit).filter(HazirYanit.id == yanit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Yanıt bulunamadı")
    db.delete(row)
    db.commit()


@router.patch("/{yanit_id}/pin", response_model=YanitResponse)
def toggle_pin(yanit_id: int, db: Session = Depends(get_db)):
    row = db.query(HazirYanit).filter(HazirYanit.id == yanit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Yanıt bulunamadı")
    row.is_pinned = not row.is_pinned
    db.commit()
    db.refresh(row)
    return row


@router.post("/{yanit_id}/use", response_model=YanitResponse)
def increment_use(yanit_id: int, db: Session = Depends(get_db)):
    row = db.query(HazirYanit).filter(HazirYanit.id == yanit_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Yanıt bulunamadı")
    row.use_count += 1
    db.commit()
    db.refresh(row)
    return row
