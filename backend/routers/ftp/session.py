"""FTP dosya yöneticisi — oturum yaşam döngüsü + dosya işlemleri.

Oturum modeli RDP biletinin TERSİDİR: RDP bileti tek kullanımlık ve 60
saniyeliktir; burada canlı bir SFTP istemcisi oturum boyunca yaşar.

- `session_id` URL'de DEĞİL, `X-FTP-Session` header'ında taşınır (URL'ler
  access log'a yazılır). Tek istisna indirme: native Save dialog için
  <a href> gerektiğinden ws_utils.TicketStore'dan tek kullanımlık kısa
  ömürlü bilet verilir — rdp.py'deki desenin ikinci tüketicisi.
- paramiko SFTPClient eşzamanlı güvenli değildir; çift tıklama paralel istek
  üretir → her oturumun asyncio.Lock'u tüm işlemleri sıraya sokar.
- Bloklayan tüm çağrılar AYRILMIŞ ThreadPoolExecutor'da çalışır
  (screenshot.py deseni): asılı bir FTP sunucusu DNS araçlarının varsayılan
  havuzunu tüketemez.
- Idle TTL 15 dk, mutlak TTL 2 saat, arka plan süpürme, açık DELETE,
  MAX_SESSIONS=10 (tek operatörlük araç; sızıntı makineyi tüketemesin).
"""
import asyncio
import os
import posixpath
import secrets
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

import paramiko
from fastapi import APIRouter, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from rate_limiter import limiter
from ws_utils import TicketStore

from .backends.base import FtpBackend
from .backends.sftp_backend import SftpBackend
from .paths import safe_join

router = APIRouter(prefix="/api/ftp", tags=["ftp"])

# ── Limitler (.env) ───────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(512 * 1024 * 1024)))
MAX_LIST_ENTRIES = int(os.getenv("MAX_LIST_ENTRIES", "5000"))
MAX_INLINE_EDIT_BYTES = int(os.getenv("MAX_INLINE_EDIT_BYTES", str(1024 * 1024)))

MAX_SESSIONS = 10
IDLE_TTL = 15 * 60          # saniye
ABSOLUTE_TTL = 2 * 60 * 60  # saniye
CHUNK = 64 * 1024

# Ayrılmış executor — screenshot.py deseni
FTP_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ftp")

_download_tickets = TicketStore(ttl=60.0)


async def run_ftp(fn, *args):
    return await asyncio.get_running_loop().run_in_executor(FTP_EXECUTOR, fn, *args)


# ── Oturum deposu ─────────────────────────────────────────────────────────────

@dataclass
class FtpSession:
    backend: FtpBackend
    root: str                      # jail kökü (sunucudaki gerçek ev dizini)
    server_label: str              # "user@host:port" (breadcrumb için)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    created: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)


_SESSIONS: dict[str, FtpSession] = {}
_sweeper_task: Optional[asyncio.Task] = None


async def _sweeper():
    while True:
        await asyncio.sleep(60)
        now = time.monotonic()
        for sid, sess in list(_SESSIONS.items()):
            if now - sess.last_used > IDLE_TTL or now - sess.created > ABSOLUTE_TTL:
                _SESSIONS.pop(sid, None)
                asyncio.get_running_loop().run_in_executor(FTP_EXECUTOR, sess.backend.close)


def _ensure_sweeper():
    global _sweeper_task
    if _sweeper_task is None or _sweeper_task.done():
        _sweeper_task = asyncio.get_running_loop().create_task(_sweeper())


def get_session(x_ftp_session: Optional[str] = Header(default=None)) -> FtpSession:
    sess = _SESSIONS.get(x_ftp_session or "")
    if sess is None:
        raise HTTPException(410, "FTP oturumu bulunamadı veya süresi doldu — yeniden bağlanın")
    # TTL süpürücüyü beklemeden de uygulanır — süresi dolmuş oturum kullanılamaz
    now = time.monotonic()
    if now - sess.last_used > IDLE_TTL or now - sess.created > ABSOLUTE_TTL:
        _SESSIONS.pop(x_ftp_session, None)
        asyncio.get_running_loop().run_in_executor(FTP_EXECUTOR, sess.backend.close)
        raise HTTPException(410, "FTP oturumunun süresi doldu (boşta kalma) — yeniden bağlanın")
    sess.last_used = now
    return sess


def _map_ftp_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, FileNotFoundError):
        return HTTPException(404, "Dosya veya dizin bulunamadı")
    if isinstance(exc, PermissionError):
        return HTTPException(403, "İzin reddedildi — sunucudaki dosya izinlerini kontrol edin")
    if isinstance(exc, OSError) and getattr(exc, "errno", None) is None and "exists" in str(exc).lower():
        return HTTPException(409, "Aynı ada sahip bir dosya/dizin zaten var")
    return HTTPException(502, f"SFTP hatası: {str(exc)[:120]}")


async def _resolve(sess: FtpSession, user_path: str, *, must_exist: bool = True) -> str:
    """Jail doğrulaması: string jail (safe_join) + sunucu realpath kontrolü.

    Uzak symlink saf string mantığını yener: /home/u/dis -> /etc gibi bir
    link, string olarak kök içinde görünür. Bu yüzden EYLEMDEN ÖNCE sunucunun
    kendi realpath'i ile doğrulanır — hedef yoksa (upload/mkdir) üst dizin
    doğrulanır.
    """
    real = safe_join(sess.root, user_path)
    probe = real if must_exist else (posixpath.dirname(real) or "/")
    try:
        resolved = await run_ftp(sess.backend.realpath, probe)
    except FileNotFoundError:
        raise HTTPException(404, "Dosya veya dizin bulunamadı")
    except Exception as exc:
        raise _map_ftp_error(exc)
    root_stripped = sess.root.rstrip("/")  # kök '/' ise '' — '//' prefix'i üretme
    if resolved != (root_stripped or "/") and not resolved.startswith(root_stripped + "/"):
        raise HTTPException(400, "Yol kök dizinin dışına çıkıyor (symlink algılandı)")
    return real


# ── Modeller ──────────────────────────────────────────────────────────────────

class SessionRequest(BaseModel):
    protocol: str = "sftp"
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(22, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field("", max_length=512)


class SessionResponse(BaseModel):
    session_id: str
    cwd: str
    home: str
    features: list[str]
    server: str


class PathBody(BaseModel):
    path: str


class RenameBody(BaseModel):
    src: str
    dst: str


class DeleteBody(BaseModel):
    path: str
    recursive: bool = False


class ChmodBody(BaseModel):
    path: str
    mode: str = Field(..., pattern=r"^[0-7]{3,4}$")


class WriteBody(BaseModel):
    path: str
    content: str


# ── Oturum uçları ─────────────────────────────────────────────────────────────

@router.post("/session", response_model=SessionResponse)
@limiter.limit("10/minute")
async def create_session(request: Request, payload: SessionRequest):
    if payload.protocol.lower() != "sftp":
        raise HTTPException(400, "v1 yalnızca SFTP destekler — FTP/FTPS sonraki sürümde")
    if len(_SESSIONS) >= MAX_SESSIONS:
        raise HTTPException(429, f"En fazla {MAX_SESSIONS} eşzamanlı FTP oturumu açılabilir — kullanılmayanları kapatın")

    host = payload.host.strip()
    username = payload.username.strip()
    if not host or not username:
        raise HTTPException(400, "host ve username zorunludur")

    def _connect() -> SftpBackend:
        return SftpBackend(host, payload.port, username, payload.password)

    try:
        backend = await asyncio.wait_for(run_ftp(_connect), timeout=25.0)
    except asyncio.TimeoutError:
        raise HTTPException(504, "SFTP bağlantısı zaman aşımına uğradı")
    except paramiko.AuthenticationException:
        raise HTTPException(401, "Kimlik doğrulama başarısız — kullanıcı adı veya şifre hatalı")
    except paramiko.SSHException as exc:
        raise HTTPException(502, f"SFTP bağlantı hatası: {str(exc)[:120]}")
    except OSError as exc:
        raise HTTPException(502, f"Sunucuya ulaşılamadı: {str(exc)[:120]}")

    try:
        root = await run_ftp(backend.realpath, await run_ftp(backend.home))
    except Exception as exc:
        await run_ftp(backend.close)
        raise _map_ftp_error(exc)

    session_id = secrets.token_urlsafe(32)
    _SESSIONS[session_id] = FtpSession(
        backend=backend, root=root,
        server_label=f"{username}@{host}:{payload.port}",
    )
    _ensure_sweeper()

    return SessionResponse(
        session_id=session_id, cwd="/", home="/",
        features=sorted(backend.capabilities), server=_SESSIONS[session_id].server_label,
    )


@router.delete("/session")
async def close_session(x_ftp_session: Optional[str] = Header(default=None)):
    sess = _SESSIONS.pop(x_ftp_session or "", None)
    if sess:
        asyncio.get_running_loop().run_in_executor(FTP_EXECUTOR, sess.backend.close)
    return {"detail": "Oturum kapatıldı"}


# ── Dosya işlemleri ───────────────────────────────────────────────────────────

@router.get("/list")
async def list_dir(path: str = "/", x_ftp_session: Optional[str] = Header(default=None)):
    sess = get_session(x_ftp_session)
    real = await _resolve(sess, path)
    async with sess.lock:
        try:
            entries = await run_ftp(sess.backend.listdir, real)
        except Exception as exc:
            raise _map_ftp_error(exc)
    truncated = len(entries) > MAX_LIST_ENTRIES
    if truncated:
        entries = entries[:MAX_LIST_ENTRIES]
    # Dizinler önce, ada göre (Türkçe'ye duyarlı) sırala
    entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
    return {"path": path, "entries": entries, "truncated": truncated}


@router.post("/mkdir")
async def make_dir(body: PathBody, x_ftp_session: Optional[str] = Header(default=None)):
    sess = get_session(x_ftp_session)
    real = await _resolve(sess, body.path, must_exist=False)
    async with sess.lock:
        try:
            await run_ftp(sess.backend.mkdir, real)
        except Exception as exc:
            raise _map_ftp_error(exc)
    return {"detail": "Dizin oluşturuldu"}


@router.post("/rename")
async def rename(body: RenameBody, x_ftp_session: Optional[str] = Header(default=None)):
    sess = get_session(x_ftp_session)
    real_src = await _resolve(sess, body.src)
    real_dst = await _resolve(sess, body.dst, must_exist=False)
    async with sess.lock:
        try:
            await run_ftp(sess.backend.rename, real_src, real_dst)
        except Exception as exc:
            raise _map_ftp_error(exc)
    return {"detail": "Yeniden adlandırıldı"}


def _delete_recursive(backend: FtpBackend, real_path: str, depth: int = 0):
    """Derinlik öncelikli özyinelemeli silme. Link'lere GİRMEZ — linkin
    kendisini siler (dışarıyı gösteren bir link üzerinden içerik silinmesin)."""
    if depth > 32:
        raise HTTPException(400, "Dizin ağacı çok derin")
    st = backend.stat(real_path)
    if st["type"] != "dir":
        backend.delete_file(real_path)
        return
    for entry in backend.listdir(real_path):
        child = real_path.rstrip("/") + "/" + entry["name"]
        if entry["type"] == "dir":
            _delete_recursive(backend, child, depth + 1)
        else:
            backend.delete_file(child)   # dosya VE link — linke girilmez
    backend.rmdir(real_path)


@router.post("/delete")
async def delete(body: DeleteBody, x_ftp_session: Optional[str] = Header(default=None)):
    sess = get_session(x_ftp_session)
    real = await _resolve(sess, body.path)
    if real == sess.root:
        raise HTTPException(400, "Kök dizin silinemez")
    async with sess.lock:
        try:
            st = await run_ftp(sess.backend.stat, real)
            if st["type"] == "dir":
                if not body.recursive:
                    raise HTTPException(409, "Dizin boş değilse recursive=true gerekir")
                await run_ftp(_delete_recursive, sess.backend, real)
            else:
                await run_ftp(sess.backend.delete_file, real)
        except Exception as exc:
            raise _map_ftp_error(exc)
    return {"detail": "Silindi"}


@router.post("/chmod")
async def chmod(body: ChmodBody, x_ftp_session: Optional[str] = Header(default=None)):
    sess = get_session(x_ftp_session)
    if "chmod" not in sess.backend.capabilities:
        raise HTTPException(400, "Bu protokol chmod desteklemiyor")
    real = await _resolve(sess, body.path)
    async with sess.lock:
        try:
            await run_ftp(sess.backend.chmod, real, int(body.mode, 8))
        except Exception as exc:
            raise _map_ftp_error(exc)
    return {"detail": f"İzinler {body.mode} olarak ayarlandı"}


# ── Satır içi düzenleme ───────────────────────────────────────────────────────

@router.get("/file")
async def read_file(path: str, x_ftp_session: Optional[str] = Header(default=None)):
    sess = get_session(x_ftp_session)
    real = await _resolve(sess, path)
    async with sess.lock:
        try:
            st = await run_ftp(sess.backend.stat, real)
            if st["size"] > MAX_INLINE_EDIT_BYTES:
                raise HTTPException(
                    413,
                    f"Dosya {st['size']} bayt — satır içi düzenleyici sınırı "
                    f"{MAX_INLINE_EDIT_BYTES // 1024} KB. Dosyayı indirin.",
                )
            data = await run_ftp(sess.backend.read_bytes, real, MAX_INLINE_EDIT_BYTES + 1)
        except Exception as exc:
            raise _map_ftp_error(exc)
    return {"path": path, "size": st["size"],
            "content": data.decode("utf-8", errors="replace")}


@router.put("/file")
async def write_file(body: WriteBody, x_ftp_session: Optional[str] = Header(default=None)):
    sess = get_session(x_ftp_session)
    data = body.content.encode("utf-8")
    if len(data) > MAX_INLINE_EDIT_BYTES:
        raise HTTPException(413, "İçerik satır içi düzenleyici sınırını aşıyor")
    real = await _resolve(sess, body.path, must_exist=False)
    async with sess.lock:
        try:
            await run_ftp(sess.backend.write_bytes, real, data)
        except Exception as exc:
            raise _map_ftp_error(exc)
    return {"detail": "Kaydedildi", "size": len(data)}


# ── Yükleme ───────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload(
    file: UploadFile,
    path: str = Form("/"),
    x_ftp_session: Optional[str] = Header(default=None),
):
    sess = get_session(x_ftp_session)
    filename = (file.filename or "dosya").replace("\\", "/").rsplit("/", 1)[-1]
    if not filename or "\x00" in filename:
        raise HTTPException(400, "Geçersiz dosya adı")
    target_user_path = path.rstrip("/") + "/" + filename
    real = await _resolve(sess, target_user_path, must_exist=False)

    async with sess.lock:
        try:
            handle = await run_ftp(sess.backend.open_write, real)
        except Exception as exc:
            raise _map_ftp_error(exc)
        written = 0
        try:
            while True:
                chunk = await file.read(CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        413, f"Dosya {MAX_UPLOAD_BYTES // (1024*1024)} MB yükleme sınırını aşıyor")
                await run_ftp(handle.write, chunk)
        except HTTPException:
            # Yarım dosyayı bırakma — kapat ve sil
            await run_ftp(handle.close)
            try:
                await run_ftp(sess.backend.delete_file, real)
            except Exception:
                pass
            raise
        except Exception as exc:
            await run_ftp(handle.close)
            raise _map_ftp_error(exc)
        await run_ftp(handle.close)

    return {"detail": "Yüklendi", "name": filename, "size": written}


# ── İndirme (tek kullanımlık bilet) ──────────────────────────────────────────

@router.post("/download-ticket")
async def download_ticket(body: PathBody, x_ftp_session: Optional[str] = Header(default=None)):
    sess = get_session(x_ftp_session)
    real = await _resolve(sess, body.path)
    try:
        st = await run_ftp(sess.backend.stat, real)
    except Exception as exc:
        raise _map_ftp_error(exc)
    if st["type"] == "dir":
        raise HTTPException(400, "Dizin indirilemez — dosya seçin (zip indirme v2'de)")
    ticket = _download_tickets.issue({
        "session_id": x_ftp_session,
        "real": real,
        "filename": st["name"],
        "size": st["size"],
    })
    return {"ticket": ticket, "expires_in": 60}


@router.get("/download")
async def download(ticket: str):
    params = _download_tickets.redeem(ticket.strip())
    if params is None:
        raise HTTPException(410, "İndirme bileti geçersiz veya süresi dolmuş — yeniden deneyin")
    sess = _SESSIONS.get(params["session_id"] or "")
    if sess is None:
        raise HTTPException(410, "FTP oturumu kapanmış — yeniden bağlanın")
    sess.last_used = time.monotonic()

    async def streamer():
        async with sess.lock:
            handle = await run_ftp(sess.backend.open_read, params["real"])
            try:
                while True:
                    chunk = await run_ftp(handle.read, CHUNK)
                    if not chunk:
                        break
                    yield chunk
            finally:
                await run_ftp(handle.close)

    quoted = urllib.parse.quote(params["filename"])
    return StreamingResponse(
        streamer(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted}",
            "Content-Length": str(params["size"]),
        },
    )
