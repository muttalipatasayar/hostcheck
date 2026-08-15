from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
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
