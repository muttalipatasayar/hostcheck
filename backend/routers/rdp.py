import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from rate_limiter import limiter
from ws_utils import TicketStore, safe_send

router = APIRouter(prefix="/api/rdp", tags=["rdp"])
logger = logging.getLogger(__name__)

GUACD_HOST = "127.0.0.1"
GUACD_PORT = 4822


# ─── Bağlantı bileti deposu ───────────────────────────────────────────────────
#
# İstemci önce POST /api/rdp/session ile bilgileri gövdede gönderir,
# karşılığında kısa ömürlü ve tek kullanımlık bir bilet alır; WebSocket
# yalnızca bu bileti taşır (gerekçe: ws_utils.TicketStore docstring'i).

_TICKET_TTL = 60.0  # saniye
_tickets = TicketStore(ttl=_TICKET_TTL)


class RDPSessionRequest(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=255)
    port: int = Field(3389, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field("", max_length=512)
    domain: str = Field("", max_length=255)
    width: int = Field(1280, ge=320, le=7680)
    height: int = Field(720, ge=240, le=4320)
    # Windows sunucular çoğunlukla NLA ister; "any" pazarlığı bazı guacd
    # sürümlerinde başarısız olur — kullanıcı açıkça seçebilmeli
    security: str = Field("any", pattern="^(any|nla|tls|rdp|vmconnect)$")


class RDPSessionResponse(BaseModel):
    ticket: str
    expires_in: int


@router.post("/session", response_model=RDPSessionResponse)
@limiter.limit("20/minute")
async def create_rdp_session(request: Request, payload: RDPSessionRequest):
    """Bağlantı bilgilerini alır, WebSocket için kısa ömürlü bir bilet döner."""
    hostname = payload.hostname.strip()
    username = payload.username.strip()
    if not hostname or not username:
        raise HTTPException(status_code=400, detail="hostname ve username zorunludur")

    ticket = _tickets.issue({
        "hostname": hostname,
        "port":     str(payload.port),
        "username": username,
        "password": payload.password,
        "domain":   payload.domain,
        "width":    str(payload.width),
        "height":   str(payload.height),
        "security": payload.security,
    })
    return RDPSessionResponse(ticket=ticket, expires_in=int(_TICKET_TTL))


@router.get("/guacd-status")
async def guacd_status():
    """guacd erişilebilir mi? — 'bağlanmıyor' şikayetlerinin bir numaralı nedeni
    guacd'ın hiç çalışmıyor olması; form bunu bağlantı denemeden gösterir."""
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(GUACD_HOST, GUACD_PORT), timeout=1.5)
        writer.close()
        return {"running": True, "address": f"{GUACD_HOST}:{GUACD_PORT}"}
    except Exception:
        return {"running": False, "address": f"{GUACD_HOST}:{GUACD_PORT}"}


# ─── Guacamole protocol helpers ───────────────────────────────────────────────

def _guac_encode(*args) -> bytes:
    """Encode values as a Guacamole protocol instruction: LEN.VAL,...;"""
    parts = [f"{len(str(a))}.{a}" for a in args]
    return (",".join(parts) + ";").encode("utf-8")


async def _guac_write(writer: asyncio.StreamWriter, *args):
    writer.write(_guac_encode(*args))
    await writer.drain()


async def _guac_read_one(reader: asyncio.StreamReader) -> str:
    """Read exactly one Guacamole instruction (terminated by semicolon)."""
    buf = bytearray()
    while True:
        ch = await reader.readexactly(1)
        buf += ch
        if ch == b";":
            return buf.decode("utf-8")
        if len(buf) > 131072:
            raise ValueError("Guacamole instruction too large")


def _guac_parse(msg: str):
    """Parse a Guacamole instruction string → (opcode, [arg, ...])."""
    msg = msg.rstrip(";")
    parts = []
    while msg:
        try:
            dot = msg.index(".")
        except ValueError:
            break
        length = int(msg[:dot])
        value = msg[dot + 1 : dot + 1 + length]
        parts.append(value)
        rest = msg[dot + 1 + length :]
        msg = rest[1:] if rest.startswith(",") else ""
    return (parts[0], parts[1:]) if parts else (None, [])


# ─── RDP WebSocket endpoint ───────────────────────────────────────────────────

@router.websocket("/ws")
async def rdp_tunnel(websocket: WebSocket):
    """
    Guacamole protokolünü kullanarak tarayıcı ile guacd arasında köprü kurar.
    Bağlantı parametreleri POST /api/rdp/session ile alınan bilet üzerinden
    çözülür — kimlik bilgileri URL'de taşınmaz.
    guacd'ın localhost:4822'de çalışıyor olması gerekir.
    """
    # guacamole-common-js soketi 'guacamole' alt-protokolüyle açar; sunucu bu
    # alt-protokolü GERİ BİLDİRMEZSE tarayıcı el sıkışmayı reddeder ve bağlantı
    # hiç kurulamaz ("Error during WebSocket handshake"). RDP'nin bugüne kadar
    # hiç çalışmamasının kök nedeni buydu.
    await websocket.accept(subprotocol="guacamole")
    writer = None

    try:
        # ── Bileti çöz ────────────────────────────────────────────────────────
        ticket = str(websocket.query_params.get("ticket", "")).strip()
        params = _tickets.redeem(ticket) if ticket else None
        if params is None:
            await safe_send(
                websocket,
                _guac_encode(
                    "error",
                    "Bağlantı bileti geçersiz veya süresi dolmuş. Yeniden bağlanın.",
                    "771"
                ).decode()
            )
            return

        # ── guacd'a bağlan ───────────────────────────────────────────────────
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(GUACD_HOST, GUACD_PORT),
                timeout=5.0,
            )
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
            await safe_send(
                websocket,
                _guac_encode(
                    "error",
                    f"guacd çalışmıyor ({GUACD_HOST}:{GUACD_PORT}). "
                    "Docker ile başlatın: docker run -d -p 4822:4822 guacamole/guacd",
                    "514"
                ).decode()
            )
            return

        # ── Guacamole el sıkışması ───────────────────────────────────────────
        # 1. rdp protokolünü seç
        await _guac_write(writer, "select", "rdp")

        # 2. guacd'ın desteklediği argüman listesini al
        args_msg = await asyncio.wait_for(_guac_read_one(reader), timeout=10.0)
        opcode, supported_args = _guac_parse(args_msg)
        if opcode != "args":
            await safe_send(
                websocket,
                _guac_encode("error", "guacd el sıkışma hatası (args beklendi)", "515").decode()
            )
            return

        # 3. guacd'ın beklediği sırayla bağlantı değerlerini gönder
        param_map = {
            "hostname":                   params["hostname"],
            "port":                       params["port"],
            "username":                   params["username"],
            "password":                   params["password"],
            "domain":                     params["domain"],
            "width":                      params["width"],
            "height":                     params["height"],
            "dpi":                        "96",
            "color-depth":                "24",
            "cursor":                     "remote",
            "security":                   params.get("security", "any"),
            "ignore-cert":                "true",
            # Pano senkronu — iki yön de açık (Aşama 8)
            "disable-copy":               "false",
            "disable-paste":              "false",
            "client-name":                "HostCheck",
            "resize-method":              "reconnect",
            "enable-wallpaper":           "true",
            "enable-theming":             "true",
            "enable-font-smoothing":      "true",
        }
        connect_vals = [param_map.get(arg, "") for arg in supported_args]
        await _guac_write(writer, "connect", *connect_vals)

        # 4. ready sinyalini al
        ready_msg = await asyncio.wait_for(_guac_read_one(reader), timeout=15.0)
        op, _ = _guac_parse(ready_msg)

        if op == "error":
            await safe_send(websocket, ready_msg)
            return
        if op != "ready":
            await safe_send(
                websocket,
                _guac_encode("error", "guacd hazır sinyali alınamadı", "515").decode()
            )
            return

        # ready mesajını tarayıcıya ilet
        await websocket.send_text(ready_msg)

        # ── Çift yönlü veri aktarımı ─────────────────────────────────────────
        async def guacd_to_browser():
            """guacd → tarayıcı (çizim & kontrol komutları)."""
            while True:
                try:
                    data = await asyncio.wait_for(reader.read(65536), timeout=60.0)
                    if not data:
                        break
                    await websocket.send_text(data.decode("utf-8", errors="replace"))
                except asyncio.TimeoutError:
                    # Bağlantıyı canlı tut
                    try:
                        await websocket.send_text("3.nop;")
                    except Exception:
                        break
                except Exception:
                    break

        relay_task = asyncio.create_task(guacd_to_browser())

        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if "text" in msg and msg["text"]:
                    writer.write(msg["text"].encode("utf-8"))
                    await writer.drain()
        finally:
            relay_task.cancel()
            try:
                await relay_task
            except asyncio.CancelledError:
                pass

    except asyncio.TimeoutError:
        await safe_send(
            websocket,
            _guac_encode("error", "Bağlantı zaman aşımına uğradı", "514").decode()
        )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("RDP tunnel hatası: %s", exc)
        await safe_send(
            websocket,
            _guac_encode("error", str(exc), "514").decode()
        )
    finally:
        if writer:
            try:
                writer.close()
            except Exception:
                pass
