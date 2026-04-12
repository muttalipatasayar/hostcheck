from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import random
import string

from database import get_db
from models import Ticket, TicketStatus, TicketPriority
from schemas import TicketCreate, TicketUpdate, TicketResponse, TicketListItem

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


def generate_ticket_no():
    suffix = ''.join(random.choices(string.digits, k=6))
    return f"TKT-{suffix}"


@router.get("/", response_model=List[TicketListItem])
def list_tickets(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    skip: int = Query(0, ge=0, le=10000),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db)
):
    valid_statuses = [s.value for s in TicketStatus]
    valid_priorities = [p.value for p in TicketPriority]

    if status and status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Geçersiz status. Kabul edilenler: {valid_statuses}")
    if priority and priority not in valid_priorities:
        raise HTTPException(status_code=400, detail=f"Geçersiz priority. Kabul edilenler: {valid_priorities}")

    query = db.query(Ticket)
    if status:
        query = query.filter(Ticket.status == status)
    if priority:
        query = query.filter(Ticket.priority == priority)
    return query.order_by(Ticket.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket bulunamadı")
    return ticket


@router.post("/", response_model=TicketResponse, status_code=201)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)):
    ticket = Ticket(
        ticket_no=generate_ticket_no(),
        **payload.model_dump()
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@router.patch("/{ticket_id}", response_model=TicketResponse)
def update_ticket(ticket_id: int, payload: TicketUpdate, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket bulunamadı")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ticket, field, value)

    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    return ticket


@router.delete("/{ticket_id}", status_code=204)
def delete_ticket(ticket_id: int, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket bulunamadı")
    db.delete(ticket)
    db.commit()


@router.patch("/{ticket_id}/check-results", response_model=TicketResponse)
def save_check_results(ticket_id: int, results: dict, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket bulunamadı")
    ticket.check_results = results
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    return ticket


@router.patch("/{ticket_id}/ai-response", response_model=TicketResponse)
def save_ai_response(ticket_id: int, data: dict, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket bulunamadı")
    ticket.ai_response = data.get("response", "")
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    return ticket
