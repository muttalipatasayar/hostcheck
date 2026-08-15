"""WebSocket yardımcıları — SSH/RDP (ve ileride FTP) router'larının ortak katmanı."""

import secrets
import time

from fastapi import WebSocket


async def safe_send(websocket: WebSocket, text: str) -> None:
    """Soket kapanmış olsa bile hata fırlatmadan göndermeyi dener."""
    try:
        await websocket.send_text(text)
    except Exception:
        pass


class TicketStore:
    """Kısa ömürlü, tek kullanımlık bağlantı bileti deposu.

    Kimlik bilgileri WebSocket URL'ine (veya indirme linkine) konulmaz:
    URL'ler tarayıcı geçmişine, proxy loglarına ve uvicorn access loguna
    düz metin yazılır. Bunun yerine bilgiler önce HTTP gövdesiyle gönderilir,
    karşılığında bu depodan kısa ömürlü bir bilet verilir; URL yalnızca
    bileti taşır. `redeem` bileti tüketir, tekrar oynatılan bilet geçersizdir.

    Depo süreç içidir: reload'ı atlatamaz ve çoklu worker'da çalışmaz.
    """

    def __init__(self, ttl: float):
        self.ttl = ttl
        self._tickets: dict[str, tuple[float, dict]] = {}

    def _purge_expired(self, now: float) -> None:
        for key in [k for k, (exp, _) in self._tickets.items() if exp <= now]:
            self._tickets.pop(key, None)

    def issue(self, params: dict) -> str:
        now = time.monotonic()
        self._purge_expired(now)
        ticket = secrets.token_urlsafe(32)
        self._tickets[ticket] = (now + self.ttl, params)
        return ticket

    def redeem(self, ticket: str) -> dict | None:
        """Bileti tüketir (tek kullanımlık). Süresi dolmuş ya da yoksa None döner."""
        now = time.monotonic()
        self._purge_expired(now)
        entry = self._tickets.pop(ticket, None)
        if entry is None:
            return None
        expires_at, params = entry
        return params if expires_at > now else None
