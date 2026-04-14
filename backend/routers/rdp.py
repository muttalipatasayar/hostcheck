import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/rdp", tags=["rdp"])
logger = logging.getLogger(__name__)

GUACD_HOST = "127.0.0.1"
GUACD_PORT = 4822


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


async def _safe_send(ws: WebSocket, text: str):
    try:
        await ws.send_text(text)
    except Exception:
        pass


# ─── RDP WebSocket endpoint ───────────────────────────────────────────────────

@router.websocket("/ws")
async def rdp_tunnel(websocket: WebSocket):
    """
    Guacamole protokolünü kullanarak tarayıcı ile guacd arasında köprü kurar.
    Bağlantı parametreleri WebSocket URL query string'inden okunur.
    guacd'ın localhost:4822'de çalışıyor olması gerekir.
    """
    await websocket.accept()
    writer = None

    try:
        # ── Bağlantı parametrelerini URL query string'den al ─────────────────
        qp = websocket.query_params
        hostname = str(qp.get("hostname", "")).strip()
        port     = str(qp.get("port",     "3389")).strip()
        username = str(qp.get("username", "")).strip()
        password = str(qp.get("password", ""))
        domain   = str(qp.get("domain",   ""))
        width    = str(qp.get("width",    "1280"))
        height   = str(qp.get("height",   "720"))

        if not hostname or not username:
            await _safe_send(
                websocket,
                _guac_encode("error", "hostname ve username zorunludur", "771").decode()
            )
            return

        try:
            port_int = int(port)
            if not (1 <= port_int <= 65535):
                raise ValueError()
        except ValueError:
            await _safe_send(
                websocket,
                _guac_encode("error", "Geçersiz port numarası", "771").decode()
            )
            return

        # ── guacd'a bağlan ───────────────────────────────────────────────────
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(GUACD_HOST, GUACD_PORT),
                timeout=5.0,
            )
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError) as exc:
            await _safe_send(
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
            await _safe_send(
                websocket,
                _guac_encode("error", "guacd el sıkışma hatası (args beklendi)", "515").decode()
            )
            return

        # 3. guacd'ın beklediği sırayla bağlantı değerlerini gönder
        param_map = {
            "hostname":                   hostname,
            "port":                       port,
            "username":                   username,
            "password":                   password,
            "domain":                     domain,
            "width":                      width,
            "height":                     height,
            "dpi":                        "96",
            "color-depth":                "24",
            "cursor":                     "remote",
            "security":                   "any",
            "ignore-cert":                "true",
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
            await _safe_send(websocket, ready_msg)
            return
        if op != "ready":
            await _safe_send(
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
        await _safe_send(
            websocket,
            _guac_encode("error", "Bağlantı zaman aşımına uğradı", "514").decode()
        )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("RDP tunnel hatası: %s", exc)
        await _safe_send(
            websocket,
            _guac_encode("error", str(exc), "514").decode()
        )
    finally:
        if writer:
            try:
                writer.close()
            except Exception:
                pass
