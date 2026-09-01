"""E-posta gönderimi — Brevo SMTP üzerinden.

`smtplib` BLOKLAYICIDIR. CLAUDE.md kuralı gereği her çağrı `run_in_executor`
ile ayrı bir iş parçacığına verilir ve `asyncio.wait_for` ile zaman aşımına
bağlanır; tek worker'lı event loop bir SMTP el sıkışması yüzünden durmamalı.

Geliştirme kaçışı: `ENV=development` ve `SMTP_USER` boşsa mail gönderilmez,
`data/mail-out/*.eml` dosyasına yazılır ve bağlantı log'a düşer. Böylece
uçtan uca akış gerçek SMTP kimliği olmadan test edilebilir.
"""
from __future__ import annotations

import asyncio
import html as _html
import logging
import os
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent


def _cikti_dizini() -> Path:
    """Geliştirme modunda maillerin yazıldığı dizin.

    Ortam değişkeniyle taşınabilir olması testler için: aksi hâlde test
    koşusu kaynak ağacına `.eml` dosyaları bırakırdı.
    """
    ozel = os.getenv("MAIL_CIKTI_DIZINI", "").strip()
    return Path(ozel) if ozel else _BACKEND_DIR / "data" / "mail-out"

SMTP_ZAMAN_ASIMI = 20.0


def _cfg(ad: str, varsayilan: str = "") -> str:
    return (os.getenv(ad, varsayilan) or "").strip()


def _gelistirme_mi() -> bool:
    return os.getenv("ENV", "production") == "development"


def yapilandirildi_mi() -> bool:
    return bool(_cfg("SMTP_USER") and _cfg("SMTP_PASS"))


def panel_adresi() -> str:
    """Maillerdeki bağlantıların tabanı. Sondaki eğik çizgi atılır."""
    return _cfg("PUBLIC_BASE_URL", "http://localhost:5173").rstrip("/")


def _temiz_baslik(deger: str) -> str:
    """Başlık enjeksiyonu kapısı.

    Kullanıcının verdiği ad-soyad `From`/`To` görünen adına giriyor; içine
    kaçırılan bir `\\n` ile saldırgan `Bcc:` başlığı ekleyip paneli spam
    rölesine çevirebilirdi.
    """
    if any(c in deger for c in "\r\n\x00"):
        raise HTTPException(status_code=400, detail="Geçersiz karakter tespit edildi.")
    return deger


def _mesaj_kur(alici: str, alici_adi: str, konu: str, metin: str, html: str) -> EmailMessage:
    gonderen = _cfg("MAIL_FROM") or _cfg("SMTP_USER") or "hostcheck@localhost"
    gonderen_adi = _cfg("MAIL_FROM_NAME", "HostCheck Destek Paneli")

    msg = EmailMessage()
    msg["Subject"] = _temiz_baslik(konu)
    msg["From"] = formataddr((_temiz_baslik(gonderen_adi), _temiz_baslik(gonderen)))
    msg["To"] = formataddr((_temiz_baslik(alici_adi), _temiz_baslik(alici)))
    msg["Message-ID"] = make_msgid(domain="hostcheck.local")
    msg["Date"] = datetime.now().astimezone().strftime("%a, %d %b %Y %H:%M:%S %z")
    # Otomatik yanıt döngüsünü kes.
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(metin)
    msg.add_alternative(html, subtype="html")
    return msg


def _dosyaya_yaz(msg: EmailMessage, alici: str) -> None:
    dizin = _cikti_dizini()
    dizin.mkdir(parents=True, exist_ok=True)
    ad = f"{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{alici.replace('@', '_at_')}.eml"
    yol = dizin / ad
    yol.write_bytes(bytes(msg))
    yol.chmod(0o600)
    logger.warning("SMTP yapılandırılmadı — mail dosyaya yazıldı: %s", yol)


def _gonder_bloklayici(msg: EmailMessage) -> None:
    host = _cfg("SMTP_HOST", "smtp-relay.brevo.com")
    port = int(_cfg("SMTP_PORT", "587") or 587)
    kullanici = _cfg("SMTP_USER")
    parola = _cfg("SMTP_PASS")

    baglam = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=SMTP_ZAMAN_ASIMI, context=baglam) as s:
            s.login(kullanici, parola)
            s.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=SMTP_ZAMAN_ASIMI) as s:
        s.ehlo()
        s.starttls(context=baglam)
        s.ehlo()
        s.login(kullanici, parola)
        s.send_message(msg)


async def mail_gonder(alici: str, alici_adi: str, konu: str, metin: str, html: str) -> None:
    """Maili gönderir. Başarısızlıkta Türkçe HTTPException fırlatır."""
    msg = _mesaj_kur(alici, alici_adi, konu, metin, html)

    if not yapilandirildi_mi():
        if _gelistirme_mi():
            _dosyaya_yaz(msg, alici)
            return
        logger.error("SMTP yapılandırılmamış; mail gönderilemedi (alıcı gizlendi).")
        raise HTTPException(
            status_code=503,
            detail=("E-posta servisi yapılandırılmamış. Yöneticiye bildirin "
                    "(sunucuda SMTP_USER / SMTP_PASS eksik)."),
        )

    dongu = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            dongu.run_in_executor(None, _gonder_bloklayici, msg),
            timeout=SMTP_ZAMAN_ASIMI + 5,
        )
    except asyncio.TimeoutError:
        logger.error("SMTP zaman aşımı.")
        raise HTTPException(status_code=504, detail="E-posta sunucusu yanıt vermedi. Biraz sonra tekrar deneyin.")
    except Exception as e:
        # Ham SMTP hatası kullanıcıya gösterilmez: sunucu adı, kimlik durumu
        # ve alıcı listesi hakkında bilgi sızdırır.
        logger.error("SMTP hatası: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="E-posta gönderilemedi. Biraz sonra tekrar deneyin.")


# ── Şablonlar ────────────────────────────────────────────────────────────────

_ALT = """
Bu e-posta HostCheck Destek Paneli tarafından otomatik gönderildi.
Bu isteği siz yapmadıysanız yapmanız gereken bir şey yok, bağlantıyı yok sayın.
"""

_STIL = (
    "font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"
    "background:#f0f2f7;padding:28px 16px;margin:0;color:#1a1d2e;"
)
_KART = (
    "max-width:520px;margin:0 auto;background:#ffffff;border-radius:12px;"
    "padding:32px;border:1px solid rgba(0,6,30,0.07);"
)
_BUTON = (
    "display:inline-block;background:#2563eb;color:#ffffff;text-decoration:none;"
    "padding:12px 26px;border-radius:6px;font-weight:600;font-size:15px;"
)


def _kacis(deger: str) -> str:
    """Kullanıcıdan gelen her değer HTML gövdesine girmeden önce kaçırılır.

    Kaçırılmasaydı saldırgan ad-soyad alanına `<a href="...">` yazıp
    YÖNETİCİYE giden "yeni üye" bildirimine kendi bağlantısını
    yerleştirebilirdi — panelin kendi adresinden gelen kusursuz bir oltalama.
    """
    return _html.escape(deger or "", quote=True)


def _iskelet(baslik: str, govde_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="tr"><body style="{_STIL}">
  <div style="{_KART}">
    <p style="margin:0 0 4px;font-size:13px;color:#6b7388;letter-spacing:.04em;
              text-transform:uppercase;">HostCheck</p>
    <h1 style="margin:0 0 18px;font-size:20px;color:#1a1d2e;">{baslik}</h1>
    {govde_html}
    <hr style="border:none;border-top:1px solid rgba(0,6,30,0.08);margin:26px 0 14px;">
    <p style="margin:0;font-size:12px;color:#9da5be;line-height:1.6;">
      Bu e-posta HostCheck Destek Paneli tarafından otomatik gönderildi.<br>
      Bu isteği siz yapmadıysanız bağlantıyı yok sayın.
    </p>
  </div>
</body></html>"""


async def dogrulama_maili(alici: str, ad_soyad: str, ham_token: str,
                          istek_zamani: str = "", istek_ip: str = "") -> None:
    """Hesap doğrulama bağlantısı.

    Mailde kaydın NE ZAMAN ve HANGİ IP'den başlatıldığı yazıyor. Sebebi:
    e-posta doğrulaması olan her sistemde artakalan bir risk var — üçüncü biri
    sizin adresinizle kayıt başlatabilir ve doğrulama bağlantısı size gelir;
    tıklarsanız hesap ONUN belirlediği parolayla açılır. Buna karşı tek
    gerçek savunma alıcının "bunu ben başlatmadım" diyebilmesidir, o da ancak
    zaman ve kaynak bilgisi verilirse mümkün olur. Aynı anda yalnızca EN SON
    bağlantı geçerlidir (`_token_olustur` eskileri siler).
    """
    link = f"{panel_adresi()}/api/uyelik/dogrula?token={ham_token}"
    kaynak = ""
    if istek_zamani:
        kaynak = f"\nKayıt isteği: {istek_zamani}"
        if istek_ip and istek_ip != "-":
            kaynak += f" · {istek_ip} adresinden"
    metin = (
        f"Merhaba {ad_soyad},\n\n"
        "HostCheck Destek Paneli üyeliğinizi tamamlamak için aşağıdaki bağlantıya tıklayın:\n\n"
        f"{link}\n\n"
        f"{kaynak}\n\n"
        "Bağlantı 24 saat geçerlidir. Bu kaydı SİZ başlatmadıysanız bağlantıya "
        "tıklamayın — tıklarsanız hesap, kaydı başlatan kişinin belirlediği "
        "parolayla açılır.\n"
        f"{_ALT}"
    )
    ad_g = _kacis(ad_soyad)
    html = _iskelet(
        "E-posta adresinizi doğrulayın",
        f"""<p style="margin:0 0 20px;font-size:15px;line-height:1.6;">
             Merhaba <strong>{ad_g}</strong>, HostCheck Destek Paneli üyeliğinizi
             tamamlamak için aşağıdaki düğmeye tıklayın.</p>
           <p style="margin:0 0 20px;"><a href="{link}" style="{_BUTON}">E-postamı doğrula</a></p>
           <p style="margin:0;font-size:13px;color:#6b7388;line-height:1.6;">
             Düğme çalışmazsa bu adresi tarayıcınıza yapıştırın:<br>
             <span style="word-break:break-all;color:#2563eb;">{link}</span></p>
           <p style="margin:16px 0 0;font-size:13px;color:#6b7388;">
             Bağlantı <strong>24 saat</strong> geçerlidir.{_kacis(kaynak)}</p>
           <p style="margin:12px 0 0;font-size:13px;color:#b45309;background:#fffbeb;
                     border-left:3px solid #f59e0b;padding:10px 12px;border-radius:4px;">
             Bu kaydı <strong>siz başlatmadıysanız</strong> bağlantıya tıklamayın —
             tıklarsanız hesap, kaydı başlatan kişinin belirlediği parolayla açılır.</p>""",
    )
    await mail_gonder(alici, ad_soyad, "HostCheck — E-posta adresinizi doğrulayın", metin, html)


async def sifre_sifirlama_maili(alici: str, ad_soyad: str, ham_token: str) -> None:
    link = f"{panel_adresi()}/?sifre-sifirla={ham_token}"
    metin = (
        f"Merhaba {ad_soyad},\n\n"
        "HostCheck parolanızı sıfırlamak için aşağıdaki bağlantıya tıklayın:\n\n"
        f"{link}\n\n"
        "Bağlantı 30 dakika geçerlidir ve yalnızca bir kez kullanılabilir.\n"
        f"{_ALT}"
    )
    ad_g = _kacis(ad_soyad)
    html = _iskelet(
        "Parolanızı sıfırlayın",
        f"""<p style="margin:0 0 20px;font-size:15px;line-height:1.6;">
             Merhaba <strong>{ad_g}</strong>, parolanızı sıfırlamak için
             aşağıdaki düğmeye tıklayın.</p>
           <p style="margin:0 0 20px;"><a href="{link}" style="{_BUTON}">Parolamı sıfırla</a></p>
           <p style="margin:0;font-size:13px;color:#6b7388;line-height:1.6;">
             Düğme çalışmazsa bu adresi tarayıcınıza yapıştırın:<br>
             <span style="word-break:break-all;color:#2563eb;">{link}</span></p>
           <p style="margin:16px 0 0;font-size:13px;color:#6b7388;">
             Bağlantı <strong>30 dakika</strong> geçerlidir.</p>""",
    )
    await mail_gonder(alici, ad_soyad, "HostCheck — Parola sıfırlama", metin, html)


async def zaten_kayitli_maili(alici: str, ad_soyad: str) -> None:
    """Kayıtlı bir adrese yeniden kayıt denendiğinde gider.

    Kayıt ucu, adresin kayıtlı olup olmadığını yanıtında AÇIKLAMAZ; bilgi
    yalnızca adresin gerçek sahibine, e-posta ile ulaşır.
    """
    link = f"{panel_adresi()}/"
    metin = (
        f"Merhaba {ad_soyad},\n\n"
        "Bu adresle HostCheck'e yeni bir üyelik açılmaya çalışıldı, ancak zaten "
        "bir hesabınız var. Giriş yapmak için panele gidin:\n\n"
        f"{link}\n\n"
        "Parolanızı hatırlamıyorsanız giriş ekranındaki 'Şifremi unuttum' "
        f"bağlantısını kullanabilirsiniz.\n{_ALT}"
    )
    ad_g = _kacis(ad_soyad)
    html = _iskelet(
        "Bu adresle zaten bir hesabınız var",
        f"""<p style="margin:0 0 20px;font-size:15px;line-height:1.6;">
             Merhaba <strong>{ad_g}</strong>, bu adresle yeni bir üyelik açılmaya
             çalışıldı ancak zaten bir hesabınız var.</p>
           <p style="margin:0 0 20px;"><a href="{link}" style="{_BUTON}">Panele git</a></p>
           <p style="margin:0;font-size:13px;color:#6b7388;line-height:1.6;">
             Parolanızı hatırlamıyorsanız giriş ekranındaki
             <strong>Şifremi unuttum</strong> bağlantısını kullanın.</p>""",
    )
    await mail_gonder(alici, ad_soyad, "HostCheck — Hesabınız zaten mevcut", metin, html)


async def yeni_uye_bildirimi(admin_eposta: str, uye_ad: str, uye_eposta: str) -> None:
    metin = (
        "HostCheck paneline yeni bir üye katıldı.\n\n"
        f"Ad Soyad : {uye_ad}\n"
        f"E-posta  : {uye_eposta}\n\n"
        f"Yönetim sekmesinden görüntüleyebilirsiniz: {panel_adresi()}/\n"
    )
    ad_g, eposta_g = _kacis(uye_ad), _kacis(uye_eposta)
    html = _iskelet(
        "Yeni üye kaydı",
        f"""<p style="margin:0 0 16px;font-size:15px;line-height:1.6;">
             HostCheck paneline yeni bir üye katıldı ve e-posta adresini doğruladı.</p>
           <table style="font-size:14px;color:#1a1d2e;border-collapse:collapse;margin:0 0 20px;">
             <tr><td style="padding:4px 16px 4px 0;color:#6b7388;">Ad Soyad</td>
                 <td style="padding:4px 0;"><strong>{ad_g}</strong></td></tr>
             <tr><td style="padding:4px 16px 4px 0;color:#6b7388;">E-posta</td>
                 <td style="padding:4px 0;"><strong>{eposta_g}</strong></td></tr>
           </table>
           <p style="margin:0;"><a href="{panel_adresi()}/" style="{_BUTON}">Yönetim paneli</a></p>""",
    )
    await mail_gonder(admin_eposta, "Yönetici", "HostCheck — Yeni üye kaydı", metin, html)
