import asyncio
import codecs
import logging

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from rate_limiter import limiter
from ws_utils import TicketStore, safe_send

router = APIRouter(prefix="/api/rdp", tags=["rdp"])
logger = logging.getLogger(__name__)

GUACD_HOST = "127.0.0.1"
GUACD_PORT = 4822

# guacd sessiz kaldığında tarayıcıya "3.nop;" gönderme aralığı.
# Tarayıcıdaki Guacamole.Tunnel.receiveTimeout 15 sn'dir; bu süreden ÖNCE
# bir şey gönderilmezse tünel "Server timeout" ile kapanır. Eski değer
# 60 sn idi ve bu eşiğin çok üzerindeydi.
_KEEPALIVE_SECONDS = 10.0

# Yarım kalan komut tamponunun üst sınırı — bozuk ya da kötü niyetli bir
# akışın sınırsız bellek tüketmesini engeller.
_MAX_BUFFER_CHARS = 16 * 1024 * 1024


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


def _split_instructions(buf: str) -> tuple[list[str], str]:
    """Tampondaki TAM komutları ayırır; yarım kalan kuyruğu geri döndürür.

    Guacamole komutu `UZUNLUK.DEĞER(,UZUNLUK.DEĞER)*;` biçimindedir ve uzunluk
    KARAKTER sayısıdır — ayırıcı ancak uzunluk kadar ilerledikten sonra
    okunabilir. Değerin içinde `;` geçebileceğinden noktalı virgüle bakarak
    bölmek YANLIŞTIR.
    """
    out: list[str] = []
    i = 0
    n = len(buf)
    while i < n:
        j = i
        while True:
            dot = buf.find(".", j)
            if dot < 0:                       # uzunluk öneki henüz tamamlanmadı
                return out, buf[i:]
            try:
                length = int(buf[j:dot])
            except ValueError:
                raise ValueError("guacd akışı bozuk: uzunluk öneki okunamadı")
            end = dot + 1 + length
            if end >= n:                      # ayırıcı henüz gelmedi
                return out, buf[i:]
            sep = buf[end]
            if sep == ";":
                out.append(buf[i:end + 1])
                i = end + 1
                break
            if sep != ",":
                raise ValueError("guacd akışı bozuk: beklenmeyen ayırıcı")
            j = end + 1
    return out, ""


class _GuacStream:
    """guacd'ın TCP akışını TAM Guacamole komutlarına böler.

    NEDEN ZORUNLU: tarayıcıdaki Guacamole.WebSocketTunnel her WebSocket
    mesajını BAĞIMSIZ ayrıştırır — mesajlar arasında tampon TUTMAZ. Yarım
    komut içeren tek bir mesaj tüneli anında "Incomplete instruction"
    (SERVER_ERROR / 519) ile kapatır. guacd'dan gelen ham TCP parçaları ise
    komut sınırına denk gelmez: tek bir ekran çizimi 64 KB'lik okuma
    penceresini rahatlıkla aşar. Bu yüzden çerçeveyi burada, komut sınırında
    kurmak şart.

    Ayrıca UTF-8 çözümü artımlıdır: çok baytlı bir karakter iki okumaya
    bölünse bile bozulmaz. Eski kod `errors="replace"` kullanıyordu; bu,
    bölünen karakteri `?` ile değiştirip uzunluk önekini değerle uyumsuz
    hâle getiriyordu (pano metnindeki Türkçe harfler).
    """

    def __init__(self, reader: asyncio.StreamReader):
        self._reader = reader
        self._decoder = codecs.getincrementaldecoder("utf-8")()
        self._buf = ""
        self._pending: list[str] = []

    async def _fill(self, timeout: float) -> None:
        data = await asyncio.wait_for(self._reader.read(65536), timeout=timeout)
        if not data:
            raise ConnectionResetError("guacd bağlantıyı kapattı")
        self._buf += self._decoder.decode(data)
        if len(self._buf) > _MAX_BUFFER_CHARS:
            raise ValueError("guacd komutu izin verilen boyutu aştı")
        found, self._buf = _split_instructions(self._buf)
        self._pending.extend(found)

    async def read_instruction(self, timeout: float) -> str:
        """El sıkışması için: tek bir tam komut döndürür."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not self._pending:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            await self._fill(remaining)
        return self._pending.pop(0)

    async def read_batch(self, timeout: float) -> list[str]:
        """Aktarım için: biriken tüm tam komutları tek seferde döndürür."""
        if not self._pending:
            await self._fill(timeout)
        batch, self._pending = self._pending, []
        return batch


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
        stream = _GuacStream(reader)

        # 1. rdp protokolünü seç
        await _guac_write(writer, "select", "rdp")

        # 2. guacd'ın desteklediği argüman listesini al
        args_msg = await stream.read_instruction(timeout=10.0)
        opcode, supported_args = _guac_parse(args_msg)
        if opcode != "args":
            await safe_send(
                websocket,
                _guac_encode("error", "guacd el sıkışma hatası (args beklendi)", "515").decode()
            )
            return

        # 3. İstemci yeteneklerini bildir — guacamole-client'ın yaptığı sıra.
        #    Bunlar gönderilmezse guacd ekran ölçüsünü ve görüntü kodlamasını
        #    varsayılanlarından seçer. Tarayıcı tarafında ses/video oynatıcı
        #    kurulmadığı için o iki liste bilerek BOŞ bırakılıyor: aksi hâlde
        #    guacd oynatılamayacak ses akışları gönderir.
        await _guac_write(writer, "size", params["width"], params["height"], "96")
        await _guac_write(writer, "audio")
        await _guac_write(writer, "video")
        await _guac_write(writer, "image", "image/png", "image/jpeg")

        # 4. guacd'ın beklediği sırayla bağlantı değerlerini gönder
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
        # args listesinin İLK ögesi bir bağlantı parametresi DEĞİL, guacd'ın
        # protokol sürümüdür ("VERSION_1_5_0") ve aynen geri yollanmalıdır —
        # istemcinin sürüm pazarlığındaki cevabı budur. param_map'te
        # karşılığı olmadığı için eskiden boş gidiyordu; guacd bunu
        # "sürüm bildirmeyen eski istemci" sayıp protokolü 1.0.0'a düşürüyor,
        # sonraki tüm davranışı (timezone, required, ölçek) o sürüme göre
        # seçiyordu.
        connect_vals = []
        for index, arg in enumerate(supported_args):
            if index == 0 and arg.startswith("VERSION_"):
                connect_vals.append(arg)
            else:
                connect_vals.append(param_map.get(arg, ""))
        await _guac_write(writer, "connect", *connect_vals)

        # 5. ready sinyalini al
        ready_msg = await stream.read_instruction(timeout=15.0)
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
            """guacd → tarayıcı (çizim & kontrol komutları).

            Her WebSocket mesajı TAM komut(lar) içerir. Ham TCP parçalarını
            olduğu gibi iletmek RDP'yi kullanılamaz hâle getiriyordu: ilk
            ekran çizimi 64 KB'lik okuma penceresini aştığı anda mesaj yarım
            bir komutla bitiyor, tarayıcıdaki tünel bunu "Incomplete
            instruction" sayıp bağlantıyı SERVER_ERROR (519) ile kapatıyordu.
            """
            while True:
                try:
                    batch = await stream.read_batch(timeout=_KEEPALIVE_SECONDS)
                except asyncio.TimeoutError:
                    # guacd sessiz — tarayıcının 15 sn'lik tünel zaman aşımına
                    # yakalanmamak için canlılık işareti gönder
                    try:
                        await websocket.send_text("3.nop;")
                        continue
                    except Exception:
                        break
                except ValueError:
                    logger.warning("guacd akışı ayrıştırılamadı — tünel kapatılıyor")
                    break
                except Exception:
                    break
                if not batch:
                    continue
                try:
                    await websocket.send_text("".join(batch))
                except Exception:
                    break

        async def browser_to_guacd():
            """tarayıcı → guacd (klavye, fare, pano)."""
            while True:
                try:
                    msg = await websocket.receive()
                except Exception:
                    break
                if msg.get("type") == "websocket.disconnect":
                    break
                text = msg.get("text")
                if not text:
                    continue
                try:
                    writer.write(text.encode("utf-8"))
                    await writer.drain()
                except Exception:
                    break

        # Hangi yön önce biterse diğerini de kapat. Eskiden yalnızca tarayıcı
        # tarafı bekleniyordu: guacd düştüğünde soket, tarayıcı kendi 15 sn'lik
        # zaman aşımına düşene kadar açık kalıyordu.
        tasks = [
            asyncio.create_task(guacd_to_browser()),
            asyncio.create_task(browser_to_guacd()),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

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
