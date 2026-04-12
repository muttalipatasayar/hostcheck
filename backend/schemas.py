from pydantic import BaseModel, EmailStr
from typing import Optional, Any, Dict
from datetime import datetime
from models import TicketStatus, TicketPriority


class TicketCreate(BaseModel):
    customer_name: str
    customer_email: EmailStr
    domain: Optional[str] = None
    server_ip: Optional[str] = None
    subject: str
    description: str
    priority: TicketPriority = TicketPriority.MEDIUM
    category: Optional[str] = None


class TicketUpdate(BaseModel):
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    domain: Optional[str] = None
    server_ip: Optional[str] = None


class TicketResponse(BaseModel):
    id: int
    ticket_no: str
    customer_name: str
    customer_email: str
    domain: Optional[str] = None
    server_ip: Optional[str] = None
    subject: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    category: Optional[str] = None
    check_results: Optional[Dict[str, Any]] = None
    ai_response: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TicketListItem(BaseModel):
    """Liste endpoint'i için hafif schema — büyük alanlar hariç."""
    id: int
    ticket_no: str
    customer_name: str
    customer_email: str
    domain: Optional[str] = None
    server_ip: Optional[str] = None
    subject: str
    status: TicketStatus
    priority: TicketPriority
    category: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CheckRequest(BaseModel):
    domain: Optional[str] = None
    server_ip: Optional[str] = None
    ticket_id: Optional[int] = None


class CheckResult(BaseModel):
    check_type: str
    status: str
    value: Optional[str] = None
    message: str
    latency_ms: Optional[float] = None


class CheckResponse(BaseModel):
    results: list[CheckResult]
    summary: str


class AIGenerateRequest(BaseModel):
    ticket_id: int
    additional_context: Optional[str] = None


class AIGenerateResponse(BaseModel):
    response: str
    ticket_id: int
