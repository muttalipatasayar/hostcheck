"""Denetimler — ölçüm verisinden eyleme dönüştürülebilir bulgular çıkarır.

Buradaki denetimlerin çoğu PageSpeed Insights'ta YOKTUR ya da tek satırlık
bir özete gömülüdür. Bu araç bir hosting destek panelinde çalıştığı için
teknisyenin sorduğu soruya cevap vermeleri gerekiyor: hangi dosya, hangi
sunucu ayarı, kaç bayt.

Her denetim ortak sözleşmeyi döndürür:

    id            — `advice.ADVICE_DB` anahtarı; Türkçe öneri buradan bağlanır
    baslik        — teknisyene gösterilen başlık
    durum         — healthy | warning | error | info (panelin dört durumu)
    deger         — kısa özet ("1,2 MB", "14 dosya")
    detay         — bir cümlelik açıklama
    tasarruf_ms   — tahmini kazanç (fırsat sıralaması bununla yapılır)
    tasarruf_bayt — tahmini bayt kazancı
    ogeler        — tablo satırları (dosya listesi)
    grup          — firsat | teshis | bilgi
"""

import urllib.parse

# Mobil profilin indirme hızı (bayt/sn) — bayt tasarrufunu süreye çevirmek
# için. `engine.DEVICES["mobile"]["ag"]["downloadThroughput"]` ile aynı değer;
# burada sabit tutuluyor ki denetimler motora bağımlı olmasın.
_MOBIL_BANT_BPS = int(1.6 * 1024 * 0.9 * 1024 / 8)

# Sıkıştırılması beklenen içerik türleri
_METIN_MIME = (
    "text/html", "text/css", "text/plain", "text/xml", "text/javascript",
    "application/javascript", "application/x-javascript", "application/json",
    "application/xml", "application/rss+xml", "image/svg+xml",
    "application/manifest+json", "application/ld+json",
)
# Sıkıştırma denetiminde göz ardı edilecek küçük dosyalar (kazanç ihmal edilebilir)
_MIN_SIKISTIRMA_BAYT = 1500

# Uzun süre önbelleklenmesi beklenen statik türler
_STATIK_TIP = {"script", "css", "link", "img", "image", "font", "media"}
# Bunun altındaki max-age "kısa" sayılır (30 gün)
_IYI_CACHE_SN = 30 * 24 * 3600

_MODERN_GORSEL = ("image/webp", "image/avif")
_ESKI_GORSEL = ("image/jpeg", "image/png", "image/gif", "image/bmp", "image/tiff")

# Toplam sayfa ağırlığı eşikleri (bayt)
_AGIRLIK_IYI = 1_600_000
_AGIRLIK_KOTU = 4_000_000

# DOM düğüm sayısı eşikleri (Lighthouse ile aynı)
_DOM_IYI = 800
_DOM_KOTU = 1400

# PHP sürüm durumu — 31 Ağustos 2026 itibarıyla.
# php.net/supported-versions: aktif destek → yalnızca güvenlik → ömrü bitti.
_PHP_OMRU_BITMIS = ("5.", "7.0", "7.1", "7.2", "7.3", "7.4", "8.0", "8.1")
_PHP_GUVENLIK_SADECE = ("8.2", "8.3")


def _bayt_to_ms(bayt: int) -> int:
    """Bayt tasarrufunu mobil bant genişliğinde süre kazancına çevirir."""
    if bayt <= 0:
        return 0
    return int(bayt / _MOBIL_BANT_BPS * 1000)


def _insan_bayt(n: int) -> str:
    if n is None:
        return "-"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.2f} MB".replace(".", ",")


def _mime_temiz(mime: str) -> str:
    return (mime or "").split(";")[0].strip().lower()


def _cache_max_age(basliklar: dict) -> int | None:
    """Cache-Control'den saniye cinsinden max-age. Yoksa/no-store ise None."""
    cc = (basliklar.get("cache-control") or "").lower()
    if not cc:
        return None
    if "no-store" in cc or "no-cache" in cc:
        return 0
    for parca in cc.split(","):
        parca = parca.strip()
        if parca.startswith("s-maxage="):
            try:
                return int(parca.split("=", 1)[1])
            except ValueError:
                pass
    for parca in cc.split(","):
        parca = parca.strip()
        if parca.startswith("max-age="):
            try:
                return int(parca.split("=", 1)[1])
            except ValueError:
                return None
    return None


# ── Tekil denetimler ─────────────────────────────────────────────────────────

def _sunucu_yaniti(baglanti: dict) -> dict:
    med = (baglanti or {}).get("medyan") or {}
    sunucu = med.get("sunucu_ms")
    if sunucu is None:
        return {"id": "sunucu-yaniti", "baslik": "Sunucu yanıt süresi",
                "durum": "info", "deger": "-", "detay": "Ölçülemedi.",
                "tasarruf_ms": 0, "tasarruf_bayt": 0, "ogeler": [], "grup": "teshis"}

    if sunucu <= 200:
        durum, detay = "healthy", "Sunucu isteği hızlı karşılıyor."
    elif sunucu <= 600:
        durum, detay = "warning", "Sunucu yanıtı kabul edilebilir ama iyileştirilebilir."
    else:
        durum, detay = "error", ("Sunucu isteği işlemekte zorlanıyor — gecikme ağda "
                                 "değil, uygulama/veritabanı tarafında.")

    return {
        "id": "sunucu-yaniti",
        "baslik": "Sunucu yanıt süresi (TTFB'nin sunucu payı)",
        "durum": durum,
        "deger": f"{sunucu:.0f} ms",
        "detay": detay,
        # 200 ms'ye inmenin kazancı
        "tasarruf_ms": int(max(0, sunucu - 200)),
        "tasarruf_bayt": 0,
        "ogeler": [
            {"ad": "DNS çözümleme", "deger": f"{med.get('dns_ms', 0):.0f} ms"},
            {"ad": "TCP bağlantısı", "deger": f"{med.get('tcp_ms', 0):.0f} ms"},
            {"ad": "TLS el sıkışması", "deger": f"{med.get('tls_ms', 0):.0f} ms"},
            {"ad": "Sunucu işleme", "deger": f"{sunucu:.0f} ms"},
        ],
        "grup": "firsat" if durum != "healthy" else "teshis",
    }


def _sikistirma(kaynaklar: list) -> dict:
    kurbanlar = []
    toplam_kazanc = 0
    for k in kaynaklar:
        mime = _mime_temiz(k.get("mime"))
        if mime and mime not in _METIN_MIME:
            continue
        if not mime and k.get("tip") not in ("script", "css", "link", "xmlhttprequest", "fetch"):
            continue
        bayt = k.get("tel_bayt") or 0
        if bayt < _MIN_SIKISTIRMA_BAYT:
            continue
        enc = (k.get("basliklar") or {}).get("content-encoding", "")
        cozulmus = k.get("decodedBodySize") or 0
        kodlanmis = k.get("encodedBodySize") or 0
        # İki bağımsız kanıt: başlık yok VEYA boyut oranı 1'e çok yakın
        sikistirilmis = bool(enc) or (cozulmus > 0 and kodlanmis > 0
                                      and kodlanmis < cozulmus * 0.95)
        if sikistirilmis:
            continue
        # Metin içerikte gzip/brotli tipik olarak %70 kazandırır
        kazanc = int(bayt * 0.7)
        toplam_kazanc += kazanc
        kurbanlar.append({
            "url": k.get("url", ""), "boyut": _insan_bayt(bayt),
            "kazanc": _insan_bayt(kazanc),
        })

    kurbanlar.sort(key=lambda x: x["url"])
    if not kurbanlar:
        return {"id": "sikistirma", "baslik": "Metin sıkıştırma (gzip / brotli)",
                "durum": "healthy", "deger": "Etkin",
                "detay": "Metin tabanlı kaynaklar sıkıştırılmış olarak geliyor.",
                "tasarruf_ms": 0, "tasarruf_bayt": 0, "ogeler": [], "grup": "teshis"}

    return {
        "id": "sikistirma",
        "baslik": "Metin sıkıştırma (gzip / brotli)",
        "durum": "error" if toplam_kazanc > 100_000 else "warning",
        "deger": f"{len(kurbanlar)} dosya · {_insan_bayt(toplam_kazanc)} kazanç",
        "detay": ("Bu dosyalar sıkıştırılmadan gönderiliyor. Sunucuda gzip veya "
                  "brotli açmak tek satırlık bir ayar ve en yüksek getirili "
                  "müdahaledir."),
        "tasarruf_ms": _bayt_to_ms(toplam_kazanc),
        "tasarruf_bayt": toplam_kazanc,
        "ogeler": kurbanlar[:25],
        "grup": "firsat",
    }


def _cache_politikasi(kaynaklar: list) -> dict:
    kurbanlar = []
    toplam = 0
    for k in kaynaklar:
        if k.get("tip") not in _STATIK_TIP:
            continue
        bayt = k.get("tel_bayt") or 0
        if bayt <= 0:
            continue
        basliklar = k.get("basliklar") or {}
        max_age = _cache_max_age(basliklar)
        if max_age is not None and max_age >= _IYI_CACHE_SN:
            continue
        # Expires ile uzun süre veriliyorsa da geç
        if max_age is None and basliklar.get("expires"):
            continue
        toplam += bayt
        kurbanlar.append({
            "url": k.get("url", ""),
            "boyut": _insan_bayt(bayt),
            "cache": (basliklar.get("cache-control") or "— (başlık yok)")[:60],
        })

    if not kurbanlar:
        return {"id": "cache-politikasi", "baslik": "Statik kaynak önbellek ömrü",
                "durum": "healthy", "deger": "Uygun",
                "detay": "Statik kaynaklar uzun süreli önbelleklenmiş.",
                "tasarruf_ms": 0, "tasarruf_bayt": 0, "ogeler": [], "grup": "teshis"}

    return {
        "id": "cache-politikasi",
        "baslik": "Statik kaynak önbellek ömrü",
        "durum": "warning",
        "deger": f"{len(kurbanlar)} dosya · {_insan_bayt(toplam)}",
        "detay": ("Bu dosyalar kısa ömürlü ya da önbelleksiz. Tekrar ziyaretlerde "
                  "gereksiz yere yeniden indiriliyorlar — ilk yüklemeyi değil, "
                  "dönen ziyaretçiyi etkiler."),
        # İlk yüklemede kazanç yok; tekrar ziyarette baytın tamamı kazanç
        "tasarruf_ms": 0,
        "tasarruf_bayt": toplam,
        "ogeler": kurbanlar[:25],
        "grup": "firsat",
    }


def _render_engelleme(engelleyen: list, kaynaklar: list) -> dict:
    if not engelleyen:
        return {"id": "render-engelleme", "baslik": "Render engelleyen kaynaklar",
                "durum": "healthy", "deger": "Yok",
                "detay": "<head> içinde ilk boyamayı geciktiren kaynak yok.",
                "tasarruf_ms": 0, "tasarruf_bayt": 0, "ogeler": [], "grup": "teshis"}

    sure_haritasi = {k.get("url"): k.get("sure", 0) for k in kaynaklar}
    ogeler, toplam_ms = [], 0
    for e in engelleyen:
        sure = sure_haritasi.get(e.get("url"), 0)
        toplam_ms += sure
        ogeler.append({"url": e.get("url", ""), "tur": e.get("tur", ""),
                       "sure": f"{sure} ms"})

    return {
        "id": "render-engelleme",
        "baslik": "Render engelleyen kaynaklar",
        "durum": "error" if len(engelleyen) >= 4 else "warning",
        "deger": f"{len(engelleyen)} kaynak",
        "detay": ("Bu script ve stylesheet'ler indirilip işlenmeden tarayıcı "
                  "sayfayı boyayamıyor. FCP ve LCP doğrudan bundan etkilenir."),
        # Gerçek kazanç zincirin uzunluğuna bağlı; muhafazakâr olarak yarısı
        "tasarruf_ms": int(toplam_ms * 0.5),
        "tasarruf_bayt": 0,
        "ogeler": ogeler[:20],
        "grup": "firsat",
    }


def _gorsel_denetimi(gorseller: list, kaynaklar: list) -> list:
    """Üç ayrı görsel bulgusu: format, ölçü, lazy-load."""
    mime_haritasi = {k.get("url"): _mime_temiz(k.get("mime")) for k in kaynaklar}
    bayt_haritasi = {k.get("url"): (k.get("tel_bayt") or 0) for k in kaynaklar}

    eski_format, buyuk, lazy_eksik = [], [], []
    kazanc_format = kazanc_boyut = 0

    for g in gorseller:
        url = g.get("url") or ""
        if not url or url.startswith("data:"):
            continue
        bayt = bayt_haritasi.get(url, 0)
        mime = mime_haritasi.get(url, "")

        if mime in _ESKI_GORSEL and bayt > 10_000:
            k = int(bayt * 0.3)          # WebP/AVIF tipik olarak %30 küçültür
            kazanc_format += k
            eski_format.append({"url": url, "format": mime.split("/")[-1],
                                "boyut": _insan_bayt(bayt), "kazanc": _insan_bayt(k)})

        dg, gg = g.get("dogal_g", 0), g.get("goruntu_g", 0)
        dy, gy = g.get("dogal_y", 0), g.get("goruntu_y", 0)
        if dg and gg and dy and gy and bayt > 10_000:
            gerekli = (gg * 2) * (gy * 2)      # 2x DPR payı bırak
            gercek = dg * dy
            if gercek > gerekli * 1.5:
                oran = 1 - (gerekli / gercek)
                k = int(bayt * oran)
                kazanc_boyut += k
                buyuk.append({
                    "url": url,
                    "dogal": f"{dg}×{dy}",
                    "goruntu": f"{gg}×{gy}",
                    "kazanc": _insan_bayt(k),
                })

        if not g.get("ekranda") and not g.get("lazy") and bayt > 10_000:
            lazy_eksik.append({"url": url, "boyut": _insan_bayt(bayt)})

    sonuc = []

    sonuc.append({
        "id": "gorsel-format",
        "baslik": "Modern görsel formatı (WebP / AVIF)",
        "durum": "healthy" if not eski_format else ("error" if kazanc_format > 300_000 else "warning"),
        "deger": "Uygun" if not eski_format else f"{len(eski_format)} görsel · {_insan_bayt(kazanc_format)}",
        "detay": ("Görseller modern formatta." if not eski_format else
                  "JPEG/PNG görseller WebP veya AVIF'e çevrilirse aynı kalitede "
                  "belirgin şekilde küçülür."),
        "tasarruf_ms": _bayt_to_ms(kazanc_format),
        "tasarruf_bayt": kazanc_format,
        "ogeler": eski_format[:20],
        "grup": "firsat" if eski_format else "teshis",
    })

    sonuc.append({
        "id": "gorsel-boyut",
        "baslik": "Gereğinden büyük görseller",
        "durum": "healthy" if not buyuk else ("error" if kazanc_boyut > 300_000 else "warning"),
        "deger": "Uygun" if not buyuk else f"{len(buyuk)} görsel · {_insan_bayt(kazanc_boyut)}",
        "detay": ("Görsel ölçüleri gösterildikleri alana uygun." if not buyuk else
                  "Bu görseller ekranda kapladıkları alandan çok daha büyük "
                  "çözünürlükte indiriliyor."),
        "tasarruf_ms": _bayt_to_ms(kazanc_boyut),
        "tasarruf_bayt": kazanc_boyut,
        "ogeler": buyuk[:20],
        "grup": "firsat" if buyuk else "teshis",
    })

    sonuc.append({
        "id": "gorsel-lazy",
        "baslik": "Ekran dışı görsellerde gecikmeli yükleme",
        "durum": "healthy" if not lazy_eksik else "warning",
        "deger": "Uygun" if not lazy_eksik else f"{len(lazy_eksik)} görsel",
        "detay": ("Ekran dışı görseller gecikmeli yükleniyor." if not lazy_eksik else
                  'İlk ekranda görünmeyen bu görsellere loading="lazy" eklenirse '
                  "ilk yükleme hafifler."),
        "tasarruf_ms": 0,
        "tasarruf_bayt": 0,
        "ogeler": lazy_eksik[:20],
        "grup": "firsat" if lazy_eksik else "teshis",
    })

    return sonuc


def _ucuncu_taraf(kaynaklar: list) -> dict:
    alanlar: dict[str, dict] = {}
    toplam_bayt = 0
    for k in kaynaklar:
        if not k.get("ucuncu_taraf"):
            continue
        host = k.get("host") or "?"
        d = alanlar.setdefault(host, {"alan": host, "sayi": 0, "bayt": 0, "sure": 0})
        d["sayi"] += 1
        d["bayt"] += k.get("tel_bayt") or 0
        d["sure"] += k.get("sure") or 0
        toplam_bayt += k.get("tel_bayt") or 0

    siralanmis = sorted(alanlar.values(), key=lambda x: x["bayt"], reverse=True)
    ogeler = [{"alan": a["alan"], "istek": a["sayi"],
               "boyut": _insan_bayt(a["bayt"]), "sure": f"{a['sure']} ms"}
              for a in siralanmis[:20]]

    if not siralanmis:
        durum, detay = "healthy", "Sayfa tamamen kendi alan adından yükleniyor."
    elif toplam_bayt > 800_000:
        durum, detay = "error", ("Üçüncü taraf kaynaklar sayfa ağırlığının büyük "
                                 "kısmını oluşturuyor ve yükleme süresini siz "
                                 "kontrol edemiyorsunuz.")
    else:
        durum, detay = "warning", ("Üçüncü taraf kaynaklar mevcut; yükleme süreleri "
                                   "sizin sunucunuza bağlı değil.")

    return {
        "id": "ucuncu-taraf",
        "baslik": "Üçüncü taraf yükü",
        "durum": durum,
        "deger": f"{len(siralanmis)} alan · {_insan_bayt(toplam_bayt)}",
        "detay": detay,
        "tasarruf_ms": 0,
        "tasarruf_bayt": 0,
        "ogeler": ogeler,
        "grup": "teshis",
    }


def _toplam_agirlik(kaynaklar: list, navigasyon: dict) -> dict:
    toplam = sum(k.get("tel_bayt") or 0 for k in kaynaklar)
    toplam += (navigasyon or {}).get("encodedBodySize", 0)

    tipler: dict[str, dict] = {}
    for k in kaynaklar:
        tip = k.get("tip") or "diğer"
        d = tipler.setdefault(tip, {"tip": tip, "sayi": 0, "bayt": 0})
        d["sayi"] += 1
        d["bayt"] += k.get("tel_bayt") or 0

    ogeler = sorted(
        ({"tip": t["tip"], "istek": t["sayi"], "boyut": _insan_bayt(t["bayt"]),
          "bayt": t["bayt"]} for t in tipler.values()),
        key=lambda x: x["bayt"], reverse=True)

    if toplam <= _AGIRLIK_IYI:
        durum = "healthy"
    elif toplam <= _AGIRLIK_KOTU:
        durum = "warning"
    else:
        durum = "error"

    return {
        "id": "toplam-agirlik",
        "baslik": "Toplam sayfa ağırlığı",
        "durum": durum,
        "deger": f"{_insan_bayt(toplam)} · {len(kaynaklar) + 1} istek",
        "detay": ("Sayfa ağırlığı makul." if durum == "healthy" else
                  "Sayfa ağırlığı mobil bağlantıda yükleme süresini doğrudan uzatıyor."),
        "tasarruf_ms": 0,
        "tasarruf_bayt": 0,
        "ogeler": ogeler,
        "grup": "teshis",
    }


def _http_protokol(baglanti: dict, navigasyon: dict) -> dict:
    tls = (baglanti or {}).get("tls") or {}
    alpn = tls.get("alpn")
    nav_proto = (navigasyon or {}).get("protokol") or ""
    h3 = (baglanti or {}).get("http3_beyani")

    protokol = alpn or nav_proto or "bilinmiyor"
    etiket = {"h2": "HTTP/2", "h3": "HTTP/3", "http/1.1": "HTTP/1.1"}.get(protokol, protokol)

    if protokol in ("h2", "h3"):
        durum = "healthy"
        detay = "Bağlantı çoklamalı modern protokol üzerinden kuruluyor."
    else:
        durum = "warning"
        detay = ("Sunucu HTTP/1.1 kullanıyor. HTTP/2 tek bağlantı üzerinden "
                 "paralel indirme sağlar; çok kaynaklı sayfalarda belirgin fark yaratır.")

    ogeler = [{"ad": "Görüşülen protokol (ALPN)", "deger": etiket}]
    if h3:
        ogeler.append({"ad": "HTTP/3 beyanı (alt-svc)", "deger": "Var"})
    if tls.get("tls_version"):
        ogeler.append({"ad": "TLS sürümü", "deger": tls["tls_version"]})
    if tls.get("cipher"):
        ogeler.append({"ad": "Şifre süiti", "deger": tls["cipher"]})

    return {
        "id": "http-protokol", "baslik": "HTTP protokol sürümü",
        "durum": durum, "deger": etiket + (" + HTTP/3" if h3 else ""),
        "detay": detay, "tasarruf_ms": 0, "tasarruf_bayt": 0,
        "ogeler": ogeler, "grup": "teshis",
    }


def _tls_surumu(baglanti: dict) -> dict:
    tls = (baglanti or {}).get("tls") or {}
    surum = tls.get("tls_version")
    if not surum:
        return {"id": "tls-surumu", "baslik": "TLS sürümü", "durum": "info",
                "deger": "-", "detay": "TLS el sıkışması yapılamadı (HTTP olabilir).",
                "tasarruf_ms": 0, "tasarruf_bayt": 0, "ogeler": [], "grup": "teshis"}

    eski = surum in ("TLSv1", "TLSv1.1", "SSLv3")
    return {
        "id": "tls-surumu", "baslik": "TLS sürümü",
        "durum": "error" if eski else ("healthy" if surum == "TLSv1.3" else "warning"),
        "deger": surum,
        "detay": ("Kullanımdan kaldırılmış TLS sürümü — tarayıcılar uyarı gösteriyor."
                  if eski else
                  "TLS 1.3 en hızlı el sıkışmayı sağlar." if surum == "TLSv1.3" else
                  "TLS 1.2 güvenli ama 1.3 daha az gidiş-dönüş gerektirir."),
        "tasarruf_ms": 0, "tasarruf_bayt": 0, "ogeler": [], "grup": "teshis",
    }


def _sunucu_teknolojisi(baglanti: dict) -> dict:
    basliklar = (baglanti or {}).get("headers") or {}
    server = basliklar.get("server") or ""
    powered = basliklar.get("x-powered-by") or ""

    ogeler = []
    if server:
        ogeler.append({"ad": "Server", "deger": server[:80]})
    if powered:
        ogeler.append({"ad": "X-Powered-By", "deger": powered[:80]})

    # PHP sürümü hem Server hem X-Powered-By içinde geçebilir
    php_surum = None
    for kaynak in (powered, server):
        alt = kaynak.lower()
        if "php/" in alt:
            php_surum = alt.split("php/", 1)[1].split(" ")[0].strip()
            break

    durum, detay = "info", "Sunucu kendini tanıtmıyor."
    deger = server or powered or "Belirtilmemiş"

    if php_surum:
        deger = f"PHP {php_surum}"
        ogeler.append({"ad": "PHP sürümü", "deger": php_surum})
        if php_surum.startswith(_PHP_OMRU_BITMIS):
            durum = "error"
            detay = (f"PHP {php_surum} ömrünü tamamladı — güvenlik yaması almıyor. "
                     "Güncel bir sürüme geçmek hem güvenlik hem performans kazancıdır.")
        elif php_surum.startswith(_PHP_GUVENLIK_SADECE):
            durum = "warning"
            detay = (f"PHP {php_surum} yalnızca güvenlik yaması alıyor, aktif "
                     "geliştirme desteği bitti. Yükseltme planlanmalı.")
        else:
            durum = "healthy"
            detay = f"PHP {php_surum} güncel destek kapsamında."
    elif server or powered:
        durum = "warning"
        detay = ("Sunucu yazılımı ve sürümü başlıkta açıkça yayınlanıyor. "
                 "Bu bilgi saldırgana hedef seçmede yardımcı olur; "
                 "gizlenmesi önerilir.")

    return {
        "id": "sunucu-teknolojisi", "baslik": "Sunucu teknolojisi",
        "durum": durum, "deger": deger, "detay": detay,
        "tasarruf_ms": 0, "tasarruf_bayt": 0, "ogeler": ogeler, "grup": "teshis",
    }


def _cdn(baglanti: dict) -> dict:
    saglayici = (baglanti or {}).get("cdn")
    return {
        "id": "cdn",
        "baslik": "İçerik dağıtım ağı (CDN)",
        "durum": "healthy" if saglayici else "info",
        "deger": saglayici or "Tespit edilmedi",
        "detay": (f"İstekler {saglayici} üzerinden geçiyor — statik içerik "
                  "kullanıcıya yakın sunucudan servis ediliyor."
                  if saglayici else
                  "CDN imzası bulunamadı. Coğrafi olarak dağınık ziyaretçisi olan "
                  "sitelerde CDN gecikmeyi belirgin şekilde düşürür."),
        "tasarruf_ms": 0, "tasarruf_bayt": 0, "ogeler": [], "grup": "teshis",
    }


def _dom_boyutu(dugum: int) -> dict:
    if dugum <= _DOM_IYI:
        durum = "healthy"
    elif dugum <= _DOM_KOTU:
        durum = "warning"
    else:
        durum = "error"
    return {
        "id": "dom-boyutu", "baslik": "DOM boyutu",
        "durum": durum, "deger": f"{dugum} düğüm",
        "detay": ("DOM boyutu makul." if durum == "healthy" else
                  "Büyük DOM her stil hesaplamasını ve yeniden düzeni pahalı hâle "
                  "getirir; etkileşim gecikmesinin (INP) başlıca sebebidir."),
        "tasarruf_ms": 0, "tasarruf_bayt": 0, "ogeler": [], "grup": "teshis",
    }


def _basarisiz_istekler(basarisiz: list, kaynaklar: list) -> dict:
    ogeler = [{"url": b.get("url", ""), "sebep": b.get("sebep", "")}
              for b in basarisiz if b.get("url")]
    for k in kaynaklar:
        st = k.get("status") or 0
        if st >= 400:
            ogeler.append({"url": k.get("url", ""), "sebep": f"HTTP {st}"})

    return {
        "id": "basarisiz-istekler", "baslik": "Başarısız istekler",
        "durum": "healthy" if not ogeler else ("error" if len(ogeler) > 3 else "warning"),
        "deger": "Yok" if not ogeler else f"{len(ogeler)} istek",
        "detay": ("Tüm kaynaklar başarıyla yüklendi." if not ogeler else
                  "Bu kaynaklar yüklenemedi. Eksik dosya hem görünümü bozar hem "
                  "tarayıcıyı boş yere bekletir."),
        "tasarruf_ms": 0, "tasarruf_bayt": 0, "ogeler": ogeler[:20], "grup": "teshis",
    }


def _konsol_hatalari(hatalar: list) -> dict:
    ogeler = [{"mesaj": h.get("mesaj", ""), "kaynak": h.get("kaynak", ""),
               "satir": h.get("satir", 0)} for h in hatalar]
    return {
        "id": "konsol-hatalari", "baslik": "Tarayıcı konsol hataları",
        "durum": "healthy" if not ogeler else "warning",
        "deger": "Yok" if not ogeler else f"{len(ogeler)} hata",
        "detay": ("Sayfa JavaScript hatası üretmiyor." if not ogeler else
                  "Sayfa JavaScript hatası üretiyor. Performansı doğrudan "
                  "etkilemeyebilir ama işlevsel bir bozukluğun işaretidir."),
        "tasarruf_ms": 0, "tasarruf_bayt": 0, "ogeler": ogeler[:20], "grup": "teshis",
    }


def _yonlendirme(hedef_url: str, son_url: str) -> dict:
    hedef = urllib.parse.urlparse(hedef_url)
    son = urllib.parse.urlparse(son_url or hedef_url)
    yonlendirildi = (hedef.scheme, hedef.netloc, hedef.path.rstrip("/")) != \
                    (son.scheme, son.netloc, son.path.rstrip("/"))

    return {
        "id": "yonlendirme", "baslik": "Yönlendirme",
        "durum": "warning" if yonlendirildi else "healthy",
        "deger": "Var" if yonlendirildi else "Yok",
        "detay": (f"İstek {son_url} adresine yönlendirildi. Her yönlendirme "
                  "ek bir gidiş-dönüş demek; kanonik adresi doğrudan vermek "
                  "bu maliyeti kaldırır." if yonlendirildi else
                  "İstek doğrudan karşılandı, yönlendirme yok."),
        # Bir yönlendirme mobil bağlantıda tipik olarak ~300 ms
        "tasarruf_ms": 300 if yonlendirildi else 0,
        "tasarruf_bayt": 0,
        "ogeler": ([{"ad": "İstenen", "deger": hedef_url},
                    {"ad": "Ulaşılan", "deger": son_url}] if yonlendirildi else []),
        "grup": "firsat" if yonlendirildi else "teshis",
    }


def calistir(olcum: dict, baglanti: dict, domain: str) -> list[dict]:
    """Tüm denetimleri çalıştırır ve tek listede döndürür.

    Sıralama: önce fırsatlar (tasarrufa göre azalan), sonra teşhisler
    (durumu kötü olan önde). PageSpeed'in kendi sıralama mantığı budur.
    """
    kaynaklar = olcum.get("kaynaklar") or []
    denetimler: list[dict] = [
        _sunucu_yaniti(baglanti),
        _sikistirma(kaynaklar),
        _cache_politikasi(kaynaklar),
        _render_engelleme(olcum.get("engelleyen") or [], kaynaklar),
    ]
    denetimler += _gorsel_denetimi(olcum.get("gorseller") or [], kaynaklar)
    denetimler += [
        _ucuncu_taraf(kaynaklar),
        _toplam_agirlik(kaynaklar, olcum.get("navigasyon") or {}),
        _http_protokol(baglanti, olcum.get("navigasyon") or {}),
        _tls_surumu(baglanti),
        _sunucu_teknolojisi(baglanti),
        _cdn(baglanti),
        _dom_boyutu(olcum.get("dom_dugum_sayisi") or 0),
        _basarisiz_istekler(olcum.get("basarisiz") or [], kaynaklar),
        _konsol_hatalari(olcum.get("konsol_hatalari") or []),
        _yonlendirme(f"https://{domain}/", olcum.get("son_url") or ""),
    ]

    oncelik = {"error": 0, "warning": 1, "info": 2, "healthy": 3}
    firsatlar = [d for d in denetimler if d["grup"] == "firsat"]
    teshisler = [d for d in denetimler if d["grup"] != "firsat"]
    firsatlar.sort(key=lambda d: (-d["tasarruf_ms"], -d["tasarruf_bayt"]))
    teshisler.sort(key=lambda d: oncelik.get(d["durum"], 9))
    return firsatlar + teshisler
