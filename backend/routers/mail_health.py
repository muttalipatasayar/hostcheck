"""Mail sağlık paneli — bir alan adının e-posta altyapısını altı bölümde puanlar.

Ağırlıklar (toplam 100): MX 25, SPF 20, DKIM 20, DMARC 20, SMTP 10, PTR 5.

Dürüstlük uyarısı: giden 25 portu çoğu ISP tarafından kapalıdır. "Port 25
kapalı" sonucu müşterinin sunucusunu değil PANELİN AĞINI yansıtıyor olabilir;
bu yüzden panelin çıkış IP'si sonucun yanında gösterilir ve başarısız SMTP
denemesi puan kırar ama 'error' sayılmaz.
"""
import asyncio
from typing import Optional

import httpx
from fastapi import APIRouter, Request
from pydantic import BaseModel

import dns_core
from error_analysis import get_error_by_key
from mail_analysis import parse_dkim, parse_dmarc, parse_spf
from rate_limiter import limiter
from routers.quick_check import ErrorAnalysis, validate_domain
from routers.dns_toolbox import _dkim_auto_discover, _run_query, analyze_mx

router = APIRouter(prefix="/api/mail-health", tags=["mail-health"])

SMTP_TIMEOUT = 6.0

# Bölüm ağırlıkları — toplamı 100 olmalı (testte doğrulanır)
WEIGHTS = {"MX": 25, "SPF": 20, "DKIM": 20, "DMARC": 20, "SMTP": 10, "PTR": 5}
assert sum(WEIGHTS.values()) == 100


class MailHealthRequest(BaseModel):
    domain: str
    dkim_selector: Optional[str] = None   # boşsa yaygın selector'lar denenir


class MailCheckItem(BaseModel):
    label: str
    status: str          # healthy | warning | error | info
    value: Optional[str] = None
    detail: Optional[str] = None
    score: int
    max_score: int


class MailHealthResponse(BaseModel):
    domain: str
    score: int           # 0-100
    checks: list[MailCheckItem]
    overall: str         # healthy | warning | error
    summary: str
    egress_ip: Optional[str] = None
    error_analysis: Optional[ErrorAnalysis] = None


# ── Yardımcılar ───────────────────────────────────────────────────────────────

async def _get_egress_ip() -> Optional[str]:
    """Panelin dışarıya çıktığı IP — SMTP sonucunun dürüst yorumu için."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://ip-api.com/json/?fields=query")
            return resp.json().get("query")
    except Exception:
        return None


async def _smtp_banner(host: str) -> Optional[str]:
    """25 portuna bağlanıp SMTP karşılama satırını okur; olmazsa None."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, 25), timeout=SMTP_TIMEOUT)
        banner = await asyncio.wait_for(reader.readline(), timeout=SMTP_TIMEOUT)
        writer.close()
        return banner.decode("utf-8", errors="replace").strip() or None
    except Exception:
        return None


async def _find_spf(domain: str) -> tuple[Optional[str], int]:
    """TXT kayıtları içinden v=spf1 olanları döner: (ilk_spf, spf_sayısı)."""
    res = await dns_core.resolve_async(domain, "TXT", timeout=5.0)
    spfs = [r for r in res["records"] if r.lower().startswith("v=spf1")]
    return (spfs[0] if spfs else None), len(spfs)


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/check", response_model=MailHealthResponse)
@limiter.limit("10/minute")
async def check_mail_health(request: Request, payload: MailHealthRequest):
    domain = validate_domain(payload.domain)
    checks: list[MailCheckItem] = []
    error_analysis = None

    # ── MX (25) ──────────────────────────────────────────────────────────────
    mx_records = []
    try:
        mx_records, _ms = await _run_query(domain, "MX")
    except Exception:
        pass

    if mx_records:
        checks.append(MailCheckItem(
            label="MX Kayıtları", status="healthy",
            value=", ".join(f"{r.priority} {r.value}" for r in mx_records[:4]),
            detail=analyze_mx(mx_records),
            score=WEIGHTS["MX"], max_score=WEIGHTS["MX"],
        ))
    else:
        checks.append(MailCheckItem(
            label="MX Kayıtları", status="error",
            value="MX kaydı yok",
            detail="Bu alan adına e-posta teslim edilemez — diğer tüm kontroller bunun üzerine kuruludur.",
            score=0, max_score=WEIGHTS["MX"],
        ))
        entry = get_error_by_key("mail_mx")
        if entry:
            error_analysis = ErrorAnalysis(**entry)

    # ── SPF (20) ─────────────────────────────────────────────────────────────
    spf_txt, spf_count = await _find_spf(domain)
    if spf_txt is None:
        checks.append(MailCheckItem(
            label="SPF", status="error", value="SPF kaydı yok",
            detail="Alıcı sunucular gönderenin yetkisini doğrulayamaz — sahtecilik ve spam klasörü riski.",
            score=0, max_score=WEIGHTS["SPF"],
        ))
    else:
        parsed = parse_spf(spf_txt)
        policy = parsed["policy"]
        score_map = {"-all": 20, "~all": 16, "?all": 10, "+all": 5}
        spf_score = score_map.get(policy, 8)
        status = "healthy" if spf_score >= 16 else "warning"
        detail_map = {
            "-all": "Sıkı politika (-all) — önerilen ayar.",
            "~all": "Yumuşak politika (~all) — kabul edilebilir; -all daha güçlü.",
            "?all": "Nötr politika (?all) — koruma sağlamaz.",
            "+all": "Açık politika (+all) — herkes bu alan adıyla mail gönderebilir!",
        }
        detail = detail_map.get(policy, "Politika mekanizması (all) bulunamadı — kayıt eksik görünüyor.")
        if spf_count > 1:
            spf_score = spf_score // 2
            status = "warning"
            detail += f" DİKKAT: {spf_count} ayrı SPF kaydı var — RFC'ye aykırı, doğrulama başarısız sayılabilir."
        checks.append(MailCheckItem(
            label="SPF", status=status, value=spf_txt[:120],
            detail=detail, score=spf_score, max_score=WEIGHTS["SPF"],
        ))

    # ── DKIM (20) ────────────────────────────────────────────────────────────
    dkim_item = None
    selector = (payload.dkim_selector or "").strip()
    if selector:
        try:
            recs, _ms = await _run_query(f"{selector}._domainkey.{domain}", "TXT")
        except Exception:
            recs = []
        if recs:
            dkim_item = (recs[0].value, selector)
    else:
        found = await _dkim_auto_discover(domain)
        if found:
            recs, sel, _ms = found
            dkim_item = (recs[0].value, sel)

    if dkim_item:
        txt, sel = dkim_item
        parsed = parse_dkim(txt)
        if not parsed["valid"]:
            checks.append(MailCheckItem(
                label="DKIM", status="warning", value=f"selector: {sel}",
                detail="Kayıt var ama public key (p=) boş — anahtar iptal edilmiş olabilir.",
                score=5, max_score=WEIGHTS["DKIM"],
            ))
        elif parsed["key_bits"] >= 1024:
            strong = parsed["key_bits"] >= 2048
            checks.append(MailCheckItem(
                label="DKIM", status="healthy" if strong else "warning",
                value=f"selector: {sel} · ~{parsed['key_bits']} bit {parsed['algorithm']}",
                detail="Güçlü anahtar." if strong else "Anahtar 1024 bit — 2048+ önerilir.",
                score=WEIGHTS["DKIM"] if strong else 14, max_score=WEIGHTS["DKIM"],
            ))
        else:
            checks.append(MailCheckItem(
                label="DKIM", status="warning",
                value=f"selector: {sel} · ~{parsed['key_bits']} bit",
                detail="Anahtar boyutu çok küçük — güvenlik riski.",
                score=8, max_score=WEIGHTS["DKIM"],
            ))
    else:
        checks.append(MailCheckItem(
            label="DKIM", status="warning", value="Bulunamadı",
            detail=("Yaygın selector'lar denendi, DKIM kaydı bulunamadı. Kayıt farklı bir "
                    "selector'da olabilir — biliyorsanız panelden selector girin."),
            score=0, max_score=WEIGHTS["DKIM"],
        ))

    # ── DMARC (20) ───────────────────────────────────────────────────────────
    dmarc_res = await dns_core.resolve_async(f"_dmarc.{domain}", "TXT", timeout=5.0)
    dmarc_txts = [r for r in dmarc_res["records"] if r.lower().startswith("v=dmarc1")]
    if not dmarc_txts:
        checks.append(MailCheckItem(
            label="DMARC", status="warning", value="DMARC kaydı yok",
            detail="SPF/DKIM başarısızlığında ne yapılacağı tanımsız — sahte mailler engellenmez.",
            score=0, max_score=WEIGHTS["DMARC"],
        ))
    else:
        parsed = parse_dmarc(dmarc_txts[0])
        policy = parsed["policy"].lower()
        score_map = {"reject": 20, "quarantine": 16, "none": 10}
        dmarc_score = score_map.get(policy, 8)
        detail_map = {
            "reject": "Ret politikası (reject) — en güçlü koruma.",
            "quarantine": "Karantina politikası — iyi; reject daha güçlü.",
            "none": "Yalnızca izleme (none) — rapor toplar, sahte maili engellemez.",
        }
        checks.append(MailCheckItem(
            label="DMARC", status="healthy" if dmarc_score >= 16 else "warning",
            value=dmarc_txts[0][:120],
            detail=detail_map.get(policy, f"Politika: {policy}"),
            score=dmarc_score, max_score=WEIGHTS["DMARC"],
        ))

    # ── SMTP (10) + PTR (5) — ilk MX üzerinden ───────────────────────────────
    egress_ip = await _get_egress_ip()

    if mx_records:
        first_mx = mx_records[0].value
        banner = await _smtp_banner(first_mx)
        if banner:
            checks.append(MailCheckItem(
                label="SMTP (Port 25)", status="healthy",
                value=banner[:100],
                detail=f"{first_mx} 25 portundan yanıt verdi.",
                score=WEIGHTS["SMTP"], max_score=WEIGHTS["SMTP"],
            ))
        else:
            checks.append(MailCheckItem(
                label="SMTP (Port 25)", status="warning",
                value=f"{first_mx}:25 yanıt vermedi",
                detail=(f"DİKKAT: Bu sonuç panelin ağını yansıtıyor olabilir — çoğu ISP giden 25 portunu "
                        f"kapatır. Panelin çıkış IP'si: {egress_ip or 'belirlenemedi'}. "
                        "Sunucu tarafında doğrulamadan arıza kaydı açmayın."),
                score=0, max_score=WEIGHTS["SMTP"],
            ))

        # PTR: ilk MX'in A kaydı → ters DNS
        ptr_score = 0
        ptr_status, ptr_value, ptr_detail = "warning", "Kontrol edilemedi", None
        a_res = await dns_core.resolve_async(first_mx, "A", timeout=5.0)
        if a_res["records"]:
            mx_ip = a_res["records"][0]
            import dns.reversename
            rev_name = str(dns.reversename.from_address(mx_ip)).rstrip(".")
            ptr_res = await dns_core.resolve_async(rev_name, "PTR", timeout=5.0)
            if ptr_res["records"]:
                ptr_score = WEIGHTS["PTR"]
                ptr_status = "healthy"
                ptr_value = f"{mx_ip} → {ptr_res['records'][0]}"
                ptr_detail = "Ters DNS tanımlı — birçok alıcı sunucu bunu şart koşar."
            else:
                ptr_value = f"{mx_ip} için PTR yok"
                ptr_detail = "Ters DNS eksik — bazı alıcılar maili reddedebilir. Sunucu sağlayıcısından istenir."
        checks.append(MailCheckItem(
            label="PTR (Ters DNS)", status=ptr_status, value=ptr_value,
            detail=ptr_detail, score=ptr_score, max_score=WEIGHTS["PTR"],
        ))
    else:
        checks.append(MailCheckItem(
            label="SMTP (Port 25)", status="info", value="Atlandı",
            detail="MX kaydı olmadığından test edilemedi.", score=0, max_score=WEIGHTS["SMTP"]))
        checks.append(MailCheckItem(
            label="PTR (Ters DNS)", status="info", value="Atlandı",
            detail="MX kaydı olmadığından test edilemedi.", score=0, max_score=WEIGHTS["PTR"]))

    # ── Toplam skor + özet ───────────────────────────────────────────────────
    score = sum(c.score for c in checks)
    if any(c.status == "error" for c in checks):
        overall = "error"
    elif any(c.status == "warning" for c in checks):
        overall = "warning"
    else:
        overall = "healthy"

    if score >= 85:
        summary = f"{domain} e-posta altyapısı sağlıklı görünüyor ({score}/100)."
    elif score >= 55:
        summary = f"{domain} e-posta altyapısında iyileştirilebilir noktalar var ({score}/100)."
    else:
        summary = f"{domain} e-posta altyapısında ciddi eksikler var ({score}/100) — teslim edilebilirlik risk altında."

    return MailHealthResponse(
        domain=domain, score=score, checks=checks,
        overall=overall, summary=summary, egress_ip=egress_ip,
        error_analysis=error_analysis,
    )
