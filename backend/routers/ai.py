import os
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from anthropic import Anthropic

from database import get_db
from models import Ticket
from rate_limiter import limiter
from schemas import AIGenerateRequest, AIGenerateResponse

router = APIRouter(prefix="/api/ai", tags=["ai"])


def get_anthropic_client() -> Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY ortam değişkeni ayarlanmamış"
        )
    return Anthropic(api_key=api_key)


def format_check_results(check_results: dict | None) -> str:
    if not check_results:
        return "Otomatik kontrol yapılmamış."

    lines = []
    results = check_results.get("results", [])
    for r in results:
        status_icon = {"healthy": "✓", "error": "✗", "warning": "⚠", "skipped": "—"}.get(
            r.get("status", ""), "?"
        )
        check_type = r.get("check_type", "")
        message = r.get("message", "")
        latency = r.get("latency_ms")
        latency_str = f" ({latency:.0f}ms)" if latency else ""
        lines.append(f"  {status_icon} {check_type}: {message}{latency_str}")

    summary = check_results.get("summary", "")
    return "\n".join(lines) + (f"\n\nÖzet: {summary}" if summary else "")


@router.post("/generate", response_model=AIGenerateResponse)
@limiter.limit("5/minute")
async def generate_response(
    request: Request,
    payload: AIGenerateRequest,
    db: Session = Depends(get_db)
):
    ticket = db.query(Ticket).filter(Ticket.id == payload.ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket bulunamadı")

    client = get_anthropic_client()

    check_summary = format_check_results(ticket.check_results)

    system_prompt = """Sen bir profesyonel hosting firmasının deneyimli destek uzmanısın.
Görevin, müşteri destek taleplerine kurumsal, empatik ve teknik olarak doğru yanıtlar üretmek.

Yanıt yazarken:
- Müşteriye ismiyle hitap et
- Sorunu anladığını belirt
- Teknik kontrol sonuçlarını sade bir dille açıkla
- Yapılan veya yapılacak işlemleri net belirt
- Gerekirse müşteriden ek bilgi iste
- Profesyonel ve kibar bir dil kullan
- Yanıtı Türkçe yaz
- Ticket numarasını yanıtta belirt
- İmzayı "HostCheck Destek Ekibi" olarak yaz"""

    user_message = f"""Aşağıdaki destek talebi için profesyonel bir yanıt yaz:

**Ticket No:** {ticket.ticket_no}
**Müşteri:** {ticket.customer_name} <{ticket.customer_email}>
**Konu:** {ticket.subject}
**Açıklama:**
{ticket.description}

**Domain:** {ticket.domain or 'Belirtilmemiş'}
**Sunucu IP:** {ticket.server_ip or 'Belirtilmemiş'}
**Kategori:** {ticket.category or 'Genel'}
**Öncelik:** {ticket.priority}

**Otomatik Kontrol Sonuçları:**
{check_summary}

{f'**Ek Bağlam:** {payload.additional_context}' if payload.additional_context else ''}

Lütfen müşteriye gönderilecek profesyonel e-posta yanıtını yaz. Sadece yanıt metnini üret, başka açıklama ekleme."""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )

    ai_text = message.content[0].text

    # Yanıtı ticket'a kaydet
    ticket.ai_response = ai_text
    from datetime import datetime
    ticket.updated_at = datetime.utcnow()
    db.commit()

    return AIGenerateResponse(response=ai_text, ticket_id=ticket.id)


@router.post("/generate-stream")
@limiter.limit("5/minute")
async def generate_response_stream(
    request: Request,
    payload: AIGenerateRequest,
    db: Session = Depends(get_db)
):
    """SSE stream ile AI yanıt üretimi"""
    from fastapi.responses import StreamingResponse

    ticket = db.query(Ticket).filter(Ticket.id == payload.ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket bulunamadı")

    client = get_anthropic_client()
    check_summary = format_check_results(ticket.check_results)

    system_prompt = """Sen bir profesyonel hosting firmasının deneyimli destek uzmanısın.
Görevin, müşteri destek taleplerine kurumsal, empatik ve teknik olarak doğru yanıtlar üretmek.
Yanıtı Türkçe yaz. İmzayı "HostCheck Destek Ekibi" olarak yaz."""

    user_message = f"""Ticket No: {ticket.ticket_no}
Müşteri: {ticket.customer_name} <{ticket.customer_email}>
Konu: {ticket.subject}
Açıklama: {ticket.description}
Domain: {ticket.domain or 'Belirtilmemiş'}
Sunucu IP: {ticket.server_ip or 'Belirtilmemiş'}

Otomatik Kontrol Sonuçları:
{check_summary}

{f'Ek Bağlam: {payload.additional_context}' if payload.additional_context else ''}

Profesyonel e-posta yanıtı yaz."""

    async def event_generator():
        full_text = ""
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        ) as stream:
            for text in stream.text_stream:
                full_text += text
                yield f"data: {text}\n\n"

        # Stream bitince kaydet
        ticket.ai_response = full_text
        from datetime import datetime
        ticket.updated_at = datetime.utcnow()
        db.commit()
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
