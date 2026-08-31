import asyncio
import concurrent.futures
import datetime
import ipaddress
import re
import socket
import ssl as _ssl
from typing import Optional

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from cryptography.x509.oid import NameOID
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from net_validation import resolve_public_ips_async
from rate_limiter import limiter

router = APIRouter(prefix="/api/ssl", tags=["ssl-tools"])

# Kripto işleri için AYRILMIŞ havuz (screenshot.py / ftp deseni).
# RSA-4096 anahtar üretimi bu makinede ~1.7 sn CPU harcıyor; `async def`
# içinde senkron çağrıldığında tek worker'lı sunucunun TEK event loop'unu
# o süre boyunca tamamen dondururyordu — auth'suz bir uçtan tam servis
# kesintisi anlamına geliyordu.
_CRYPTO_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="ssl-crypto")


async def _run_crypto(fn, *args):
    return await asyncio.get_running_loop().run_in_executor(_CRYPTO_EXECUTOR, fn, *args)


# SSL Checker'ın izin verdiği portlar. Eskiden 1-65535 serbestti ve uç
# auth'suz + rate limitsiz olduğu için dış hedeflere karşı port tarayıcısı
# olarak kullanılabiliyordu (hata metni portun durumunu ele veriyordu).
ALLOWED_TLS_PORTS = {443, 8443, 993, 995, 465, 587, 636, 989, 990, 5061, 25, 21}

# ── Türkçe karakter dönüşümü ─────────────────────────────────────────────────

_TR_MAP = {
    'ğ': 'g', 'Ğ': 'G', 'ü': 'u', 'Ü': 'U',
    'ş': 's', 'Ş': 'S', 'ı': 'i', 'İ': 'I',
    'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C',
}


def _sanitize(value: str) -> str:
    for tr, en in _TR_MAP.items():
        value = value.replace(tr, en)
    return value.strip()


def _get_attr(subject, oid) -> Optional[str]:
    try:
        return subject.get_attributes_for_oid(oid)[0].value
    except (IndexError, Exception):
        return None


# ── CSR Çözümle ───────────────────────────────────────────────────────────────

class CSRDecodeRequest(BaseModel):
    csr_pem: str


class CSRDecodeResponse(BaseModel):
    common_name: Optional[str] = None
    organization: Optional[str] = None
    organization_unit: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    locality: Optional[str] = None
    email: Optional[str] = None
    key_algorithm: Optional[str] = None
    key_size: Optional[int] = None
    signature_algorithm: Optional[str] = None
    san: list[str] = []
    is_valid: bool = False


@router.post("/csr-decode", response_model=CSRDecodeResponse)
@limiter.limit("30/minute")
async def decode_csr(request: Request, payload: CSRDecodeRequest):
    try:
        csr = await _run_crypto(x509.load_pem_x509_csr, payload.csr_pem.strip().encode())
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz CSR formatı — PEM olarak yapıştırdığınızdan emin olun")

    subject = csr.subject

    # Key bilgisi
    pub = csr.public_key()
    key_algo = key_size = None
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa as _rsa, ec
        if isinstance(pub, _rsa.RSAPublicKey):
            key_algo, key_size = "RSA", pub.key_size
        elif isinstance(pub, ec.EllipticCurvePublicKey):
            key_algo, key_size = "EC", pub.key_size
    except Exception:
        pass

    # SAN listesi
    san_list = []
    try:
        ext = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        san_list = ext.value.get_values_for_type(x509.DNSName)
    except Exception:
        pass

    sig_algo = None
    try:
        sig_algo = csr.signature_hash_algorithm.name.upper()
    except Exception:
        pass

    return CSRDecodeResponse(
        common_name=_get_attr(subject, NameOID.COMMON_NAME),
        organization=_get_attr(subject, NameOID.ORGANIZATION_NAME),
        organization_unit=_get_attr(subject, NameOID.ORGANIZATIONAL_UNIT_NAME),
        country=_get_attr(subject, NameOID.COUNTRY_NAME),
        state=_get_attr(subject, NameOID.STATE_OR_PROVINCE_NAME),
        locality=_get_attr(subject, NameOID.LOCALITY_NAME),
        email=_get_attr(subject, NameOID.EMAIL_ADDRESS),
        key_algorithm=key_algo,
        key_size=key_size,
        signature_algorithm=sig_algo,
        san=list(san_list),
        is_valid=csr.is_signature_valid,
    )


# ── PFX Dönüştür ──────────────────────────────────────────────────────────────

class PFXConvertRequest(BaseModel):
    cert_pem: str
    key_pem: str
    ca_pem: Optional[str] = None
    password: str = ""


@router.post("/pfx-convert")
@limiter.limit("20/minute")
async def convert_pfx(request: Request, payload: PFXConvertRequest):
    # Sertifika
    try:
        cert = x509.load_pem_x509_certificate(payload.cert_pem.strip().encode())
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz sertifika (CRT/PEM) formatı")

    # Private key
    try:
        private_key = serialization.load_pem_private_key(
            payload.key_pem.strip().encode(),
            password=None,
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz Private Key formatı")

    # CA zinciri (opsiyonel, birden fazla sertifika olabilir)
    ca_certs = []
    if payload.ca_pem and payload.ca_pem.strip():
        raw = payload.ca_pem.strip().encode()
        parts = raw.split(b"-----END CERTIFICATE-----")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            pem_block = part + b"\n-----END CERTIFICATE-----\n"
            try:
                ca_certs.append(x509.load_pem_x509_certificate(pem_block))
            except Exception:
                pass
        if not ca_certs:
            raise HTTPException(status_code=400, detail="Geçersiz CA sertifika formatı")

    password_bytes = payload.password.encode() if payload.password else None
    enc = (
        serialization.BestAvailableEncryption(password_bytes)
        if password_bytes
        else serialization.NoEncryption()
    )

    try:
        # Parola verildiğinde KDF iterasyonları CPU harcar → executor'da çalıştır
        pfx_data = await _run_crypto(
            lambda: pkcs12.serialize_key_and_certificates(
                name=b"certificate",
                key=private_key,
                cert=cert,
                cas=ca_certs if ca_certs else None,
                encryption_algorithm=enc,
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PFX oluşturulamadı: {str(e)[:120]}")

    return Response(
        content=pfx_data,
        media_type="application/x-pkcs12",
        headers={"Content-Disposition": 'attachment; filename="certificate.pfx"'},
    )


# ── CSR Oluştur ───────────────────────────────────────────────────────────────

class CSRGenerateRequest(BaseModel):
    common_name: str
    organization: str = ""
    organization_unit: str = ""
    country: str = "TR"
    state: str = ""
    locality: str = ""
    email: str = ""
    san_list: list[str] = []
    key_size: int = 2048


class CSRGenerateResponse(BaseModel):
    csr_pem: str
    private_key_pem: str


# ── SSL Checker ───────────────────────────────────────────────────────────────

class SSLCheckResponse(BaseModel):
    domain: str
    port: int
    is_active: bool
    is_trusted: bool
    cert_type: str        # DV | OV | EV
    is_wildcard: bool
    common_name: str
    organization: str
    issuer: str
    valid_from: str
    valid_until: str
    days_remaining: int
    total_days: int
    san: list[str]
    error: Optional[str] = None


def _utc(dt: datetime.datetime) -> datetime.datetime:
    """Ensure datetime is UTC-aware regardless of cryptography version."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _detect_cert_type(cert: x509.Certificate, org: str) -> str:
    """Detect DV / OV / EV based on Certificate Policies and Subject."""
    try:
        policies = cert.extensions.get_extension_for_class(x509.CertificatePolicies)
        for policy in policies.value:
            # CA/Browser Forum EV OID
            if policy.policy_identifier.dotted_string == "2.23.140.1.1":
                return "EV"
    except Exception:
        pass
    if org.strip():
        return "OV"
    return "DV"


# NOT: Eski `_is_private_host` kaldırıldı. Yerini `net_validation`
# içindeki ortak kapı aldı (`resolve_public_ips_async`): çözümlemeyi
# executor'da yapar, `is_reserved`/`is_multicast`/IPv4-mapped IPv6 dâhil
# tam süzgeç uygular ve bağlantı doğrulanmış IP'ye pinlenir.


def _check_ssl_sync(domain: str, port: int, target_ip: str = "") -> dict:
    """Blocking SSL check — called via run_in_executor.

    `target_ip` verilirse bağlantı O ADRESE kurulur ve `server_hostname`
    alan adı olarak kalır: SNI ve sertifika doğrulaması alan adına göre
    yapılır, ama işletim sistemi ikinci bir DNS çözümlemesi yapmaz — yani
    doğrulama ile bağlantı arasındaki rebinding penceresi kapanır.
    """
    connect_to = target_ip or domain
    base: dict = dict(
        domain=domain, port=port,
        is_active=False, is_trusted=False,
        cert_type="DV", is_wildcard=False,
        common_name="", organization="",
        issuer="", valid_from="", valid_until="",
        days_remaining=0, total_days=1, san=[], error=None,
    )

    # — Fetch certificate (no trust verification, so we get it even if expired) —
    ctx_raw = _ssl.create_default_context()
    ctx_raw.check_hostname = False
    ctx_raw.verify_mode = _ssl.CERT_NONE
    cert_der = None
    try:
        with socket.create_connection((connect_to, port), timeout=10) as raw:
            with ctx_raw.wrap_socket(raw, server_hostname=domain) as tls:
                cert_der = tls.getpeercert(binary_form=True)
    except (socket.timeout, TimeoutError):
        base["error"] = f"Bağlantı zaman aşımı — {domain}:{port} erişilemiyor"
        return base
    except ConnectionRefusedError:
        base["error"] = f"Bağlantı reddedildi — port {port} kapalı olabilir"
        return base
    except _ssl.SSLError as e:
        base["error"] = f"SSL el sıkışma hatası: {e.reason or e}"
        return base
    except OSError as e:
        base["error"] = f"Bağlantı hatası: {e}"
        return base
    except Exception as e:
        base["error"] = f"Beklenmeyen hata: {e}"
        return base

    if not cert_der:
        base["error"] = "Sertifika alınamadı"
        return base

    # — Parse certificate —
    try:
        cert = x509.load_der_x509_certificate(cert_der)
    except Exception as e:
        base["error"] = f"Sertifika çözümlenemedi: {e}"
        return base

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    valid_from  = _utc(cert.not_valid_before)
    valid_until = _utc(cert.not_valid_after)
    days_remaining = (valid_until - now).days
    total_days = max((valid_until - valid_from).days, 1)

    cn       = _get_attr(cert.subject, NameOID.COMMON_NAME)       or ""
    org      = _get_attr(cert.subject, NameOID.ORGANIZATION_NAME) or ""
    issuer   = (_get_attr(cert.issuer, NameOID.COMMON_NAME) or
                _get_attr(cert.issuer, NameOID.ORGANIZATION_NAME) or "")

    # SAN list
    san_list: list[str] = []
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        san_list = list(ext.value.get_values_for_type(x509.DNSName))
    except Exception:
        pass

    is_wildcard = cn.startswith("*.") or any(s.startswith("*.") for s in san_list)
    cert_type   = _detect_cert_type(cert, org)

    # — Trust check (full CA verification + hostname matching) —
    is_trusted = False
    try:
        ctx_trusted = _ssl.create_default_context()
        with socket.create_connection((connect_to, port), timeout=10) as raw:
            with ctx_trusted.wrap_socket(raw, server_hostname=domain) as _tls:
                is_trusted = True
    except Exception:
        pass

    is_active = days_remaining > 0 and is_trusted

    base.update(
        is_active=is_active,
        is_trusted=is_trusted,
        cert_type=cert_type,
        is_wildcard=is_wildcard,
        common_name=cn,
        organization=org,
        issuer=issuer,
        valid_from=valid_from.strftime("%d %b %Y %H:%M UTC"),
        valid_until=valid_until.strftime("%d %b %Y %H:%M UTC"),
        days_remaining=days_remaining,
        total_days=total_days,
        san=san_list,
    )
    return base


@router.get("/check", response_model=SSLCheckResponse)
@limiter.limit("20/minute")
async def check_ssl(request: Request, domain: str, port: int = 443):
    """SSL sertifikasını sorgular; aktiflik, tür (DV/OV/EV/Wildcard) ve kalan gün döner."""
    # — Sanitize —
    domain = domain.strip().lower()
    for prefix in ("https://", "http://"):
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    domain = domain.split("/")[0].split("?")[0].split(":")[0]

    if not domain:
        raise HTTPException(400, "Domain adı zorunludur")
    if not re.match(r"^[a-z0-9.\-*]+$", domain):
        raise HTTPException(400, "Geçersiz domain adı")
    if port not in ALLOWED_TLS_PORTS:
        raise HTTPException(
            400,
            "Bu port sorgulanamaz. İzin verilenler: "
            + ", ".join(str(p) for p in sorted(ALLOWED_TLS_PORTS)),
        )

    # SSRF kapısı. Eski `_is_private_host` doğruydu ama iki kusuru vardı:
    # (1) `async def` içinde senkron `getaddrinfo` çağırıp event loop'u
    #     bloklıyordu, (2) çözümlemeyi doğrulayıp bağlantıyı ALAN ADINA
    #     kurduğu için araya DNS rebinding penceresi giriyordu.
    # Artık çözümleme executor'da yapılır ve bağlantı doğrulanmış IP'ye pinlenir.
    target_ip = (await resolve_public_ips_async(domain, port))[0]

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _check_ssl_sync, domain, port, target_ip)

    if result["error"] and not result["common_name"]:
        raise HTTPException(400, result["error"])

    return result


@router.post("/csr-generate", response_model=CSRGenerateResponse)
@limiter.limit("5/minute")
async def generate_csr(request: Request, payload: CSRGenerateRequest):
    if not payload.common_name.strip():
        raise HTTPException(status_code=400, detail="Common Name (alan adı) zorunludur")

    if payload.key_size not in (2048, 4096):
        raise HTTPException(status_code=400, detail="Key boyutu 2048 veya 4096 olmalıdır")

    # Private key oluştur — AYRILMIŞ executor'da.
    # RSA-4096 ~1.7 sn CPU harcar; event loop'ta çalıştırıldığında tüm panel
    # (SSH/RDP/FTP oturumları dâhil) o süre boyunca donuyordu.
    private_key = await _run_crypto(
        lambda: rsa.generate_private_key(
            public_exponent=65537,
            key_size=payload.key_size,
            backend=default_backend(),
        )
    )

    # Subject alanları — Türkçe karakterleri temizle
    cn = _sanitize(payload.common_name)
    attrs = [x509.NameAttribute(NameOID.COMMON_NAME, cn)]

    country = _sanitize(payload.country).upper()[:2]
    if country:
        attrs.append(x509.NameAttribute(NameOID.COUNTRY_NAME, country))
    if payload.state:
        attrs.append(x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, _sanitize(payload.state)))
    if payload.locality:
        attrs.append(x509.NameAttribute(NameOID.LOCALITY_NAME, _sanitize(payload.locality)))
    if payload.organization:
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, _sanitize(payload.organization)))
    if payload.organization_unit:
        attrs.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, _sanitize(payload.organization_unit)))
    if payload.email:
        attrs.append(x509.NameAttribute(NameOID.EMAIL_ADDRESS, _sanitize(payload.email)))

    builder = x509.CertificateSigningRequestBuilder().subject_name(x509.Name(attrs))

    # SAN — CN + ek alan adları
    san_entries = []
    seen: set[str] = set()
    for d in [cn] + [_sanitize(s) for s in payload.san_list if s.strip()]:
        d = d.strip().lower()
        if d and d not in seen:
            san_entries.append(x509.DNSName(d))
            seen.add(d)

    if san_entries:
        builder = builder.add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False,
        )

    csr = await _run_crypto(
        lambda: builder.sign(private_key, hashes.SHA256(), default_backend()))

    csr_pem = csr.public_bytes(Encoding.PEM).decode()
    key_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    return CSRGenerateResponse(csr_pem=csr_pem, private_key_pem=key_pem)
