from typing import Optional

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12, Encoding
from cryptography.x509.oid import NameOID
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

router = APIRouter(prefix="/api/ssl", tags=["ssl-tools"])

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
async def decode_csr(payload: CSRDecodeRequest):
    try:
        csr = x509.load_pem_x509_csr(payload.csr_pem.strip().encode())
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
async def convert_pfx(payload: PFXConvertRequest):
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
        pfx_data = pkcs12.serialize_key_and_certificates(
            name=b"certificate",
            key=private_key,
            cert=cert,
            cas=ca_certs if ca_certs else None,
            encryption_algorithm=enc,
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


@router.post("/csr-generate", response_model=CSRGenerateResponse)
async def generate_csr(payload: CSRGenerateRequest):
    if not payload.common_name.strip():
        raise HTTPException(status_code=400, detail="Common Name (alan adı) zorunludur")

    if payload.key_size not in (2048, 4096):
        raise HTTPException(status_code=400, detail="Key boyutu 2048 veya 4096 olmalıdır")

    # Private key oluştur
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=payload.key_size,
        backend=default_backend(),
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

    csr = builder.sign(private_key, hashes.SHA256(), default_backend())

    csr_pem = csr.public_bytes(Encoding.PEM).decode()
    key_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    return CSRGenerateResponse(csr_pem=csr_pem, private_key_pem=key_pem)
