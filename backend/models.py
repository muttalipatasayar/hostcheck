from sqlalchemy import Column, Index, Integer, String, Text, DateTime, Enum, JSON, Boolean
from sqlalchemy.sql import func
from database import Base
import enum


class TicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_no = Column(String(20), unique=True, index=True)
    customer_name = Column(String(200), nullable=False)
    customer_email = Column(String(200), nullable=False)
    domain = Column(String(255), nullable=True)
    server_ip = Column(String(50), nullable=True)
    subject = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Enum(TicketStatus), default=TicketStatus.OPEN, nullable=False, index=True)
    priority = Column(Enum(TicketPriority), default=TicketPriority.MEDIUM, nullable=False, index=True)
    category = Column(String(100), nullable=True)
    check_results = Column(JSON, nullable=True)
    ai_response = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index('ix_tickets_status_created_at', 'status', 'created_at'),
    )


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
