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


# ── Origin doğrulaması ────────────────────────────────────────────────────────

import os
from urllib.parse import urlparse


def _allowed_origins() -> set[str]:
    """CORS ile AYNI listeyi kullanır — tek yapılandırma noktası."""
    raw = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
    return {o.strip().rstrip("/") for o in raw.split(",") if o.strip()}


async def check_origin(websocket: WebSocket) -> bool:
    """El sıkışmadan ÖNCE çağrılır; origin izinli değilse soketi kapatır.

    Neden gerekli: WebSocket el sıkışması Same-Origin Policy'ye TABİ DEĞİLDİR
    ve `CORSMiddleware` WS'i hiç görmez. Basic Auth ise "ambient"tır —
    tarayıcı Authorization başlığını cross-origin WS el sıkışmasına da
    otomatik ekler. Yani Nginx auth_basic bu saldırıyı DURDURMAZ: kötü
    niyetli bir sayfa operatörün tarayıcısından wss://panel/api/ssh/ws
    açıp panelin iç ağ erişimini ödünç alabilir (CSWSH).

    Origin başlığı hiç yoksa istek tarayıcıdan gelmiyordur (curl, betik) —
    bu durumda ağ sınırı (127.0.0.1 binding + Nginx auth) tek koruma olarak
    kalır ve bağlantıya izin verilir; CSWSH yalnızca tarayıcı kaynaklı bir
    saldırıdır.
    """
    origin = websocket.headers.get("origin")
    if not origin:
        return True

    allowed = _allowed_origins()
    if origin.rstrip("/") in allowed:
        return True

    # Aynı origin'den gelen istek: Nginx tek origin'den servis ettiğinde
    # Origin, isteğin Host'uyla aynıdır ve CORS_ORIGINS'te yazmasa da meşrudur.
    host = websocket.headers.get("host", "")
    if host and urlparse(origin).netloc == host:
        return True

    await websocket.close(code=1008, reason="Origin izin verilmiyor")
    return False
