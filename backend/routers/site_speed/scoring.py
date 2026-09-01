"""Lighthouse performans skorlaması — `shared/statistics.js` Python portu.

Lighthouse her metriği log-normal bir eğriyle 0-1 arasına indirger, sonra
ağırlıklı ortalamayı alır. Eğri iki kontrol noktasıyla tanımlıdır:

    p10    → skor tam 90 (yeşil bandın alt sınırı)
    median → skor tam 50 (turuncu bandın alt sınırı)

Bu iki nokta ve `INVERSE_ERFC_ONE_FIFTH` sabiti Lighthouse kaynağından
birebir alınmıştır; sayıları "yaklaşık" değerlerle değiştirmeyin, skor
Google'ınkinden sapar.

ÖNEMLİ — Speed Index ölçmüyoruz. Lighthouse'un 100 puanlık ağırlık
dağılımında SI %10 yer tutar; bizim motorumuz filmstrip trace almadığı için
bu metriği üretemez. `performance_score` mevcut metriklerin ağırlık toplamına
böldüğü için SI'nin yokluğu kalan dört metrik arasında otomatik olarak
yeniden normalize edilir. Sonuç resmî PSI skorundan birkaç puan sapabilir;
arayüz bunu kullanıcıya yazıyor.
"""

import math

# Lighthouse'un skor bantlarını clamp'lediği sabitler
MIN_PASSING_SCORE = 0.90
MAX_AVERAGE_SCORE = 0.8999999999
MIN_AVERAGE_SCORE = 0.50
MAX_FAILING_SCORE = 0.4999999999

# erfc⁻¹(2/5) — eğrinin p10 noktasından geçmesini sağlayan sabit
INVERSE_ERFC_ONE_FIFTH = 0.9061938024368232

# Lighthouse 10, 11, 12 ve 13'te DEĞİŞMEDİ. Toplam 100.
WEIGHTS = {
    "first-contentful-paint":   10,
    "speed-index":              10,   # ölçmüyoruz — ağırlık yeniden dağılır
    "largest-contentful-paint": 25,
    "total-blocking-time":      30,
    "cumulative-layout-shift":  25,
}

# (p10, median) — masaüstü eşikleri mobilin yaklaşık yarısı kadar sıkıdır:
# aynı sayfa masaüstünde daha kolay düşük skor alır. Arayüz bunu açıklıyor.
CURVES = {
    "mobile": {
        "first-contentful-paint":   (1800, 3000),
        "speed-index":              (3387, 5800),
        "largest-contentful-paint": (2500, 4000),
        "total-blocking-time":      (200,  600),
        "cumulative-layout-shift":  (0.1,  0.25),
    },
    "desktop": {
        "first-contentful-paint":   (934,  1600),
        "speed-index":              (1311, 2300),
        "largest-contentful-paint": (1200, 2400),
        "total-blocking-time":      (150,  350),
        "cumulative-layout-shift":  (0.1,  0.25),
    },
}

# Core Web Vitals ve tanılayıcı metriklerin iyi / iyileştirilmeli sınırları.
# Skorlamadan AYRIDIR — bunlar web.dev'in yayınladığı kullanıcı deneyimi
# eşikleri, gauge'ın rengini değil metrik kartının rengini belirler.
THRESHOLDS = {
    "lcp_ms":  (2500, 4000),
    "cls":     (0.1,  0.25),
    "inp_ms":  (200,  500),
    "fcp_ms":  (1800, 3000),
    "ttfb_ms": (800,  1800),
    "tbt_ms":  (200,  600),
}


def log_normal_score(p10: float, median: float, value: float) -> float:
    """Tek bir metriği 0.0-1.0 arasına indirger (Lighthouse birebir)."""
    if value <= 0:
        return 1.0

    # max(5e-324, ...) sıfıra bölmeyi ve log(0) taşmasını engeller (LH ile aynı)
    x_log_ratio   = math.log(max(5e-324, value / median))
    p10_log_ratio = -math.log(max(5e-324, p10 / median))
    standardized  = x_log_ratio * INVERSE_ERFC_ONE_FIFTH / p10_log_ratio

    # Lighthouse erfc kullanır; erfc(x) == 1 - erf(x) olduğundan bu eşdeğer
    pct = (1 - math.erf(standardized)) / 2

    if value <= p10:
        return max(MIN_PASSING_SCORE, min(1.0, pct))
    if value <= median:
        return max(MIN_AVERAGE_SCORE, min(MAX_AVERAGE_SCORE, pct))
    return max(0.0, min(MAX_FAILING_SCORE, pct))


def metric_scores(metrics: dict, strategy: str = "mobile") -> dict:
    """Her metrik için 0-1 skoru. Bilinmeyen/None metrikler atlanır."""
    curves = CURVES.get(strategy, CURVES["mobile"])
    out = {}
    for key, (p10, median) in curves.items():
        value = metrics.get(key)
        if value is None:
            continue
        out[key] = log_normal_score(p10, median, value)
    return out


def performance_score(metrics: dict, strategy: str = "mobile") -> int:
    """Ağırlıklı performans skoru, 0-100 tam sayı.

    `metrics` Lighthouse audit id'leriyle anahtarlanır ve HAM değer taşır
    (ms cinsinden süreler, CLS birimsiz). Eksik metrikler ağırlık toplamından
    da düşülür — Speed Index'in yokluğu böyle telafi edilir.
    """
    scores = metric_scores(metrics, strategy)
    if not scores:
        return 0

    total_weight = sum(WEIGHTS[k] for k in scores)
    if total_weight == 0:
        return 0

    weighted = sum(scores[k] * WEIGHTS[k] for k in scores)
    return round(weighted / total_weight * 100)


def score_status(score: int) -> str:
    """0-100 skoru panelin dört durumlu sözlüğüne çevirir."""
    if score >= 90:
        return "healthy"
    if score >= 50:
        return "warning"
    return "error"


def metric_status(key: str, value) -> str:
    """Tek bir metriği web.dev eşiklerine göre değerlendirir."""
    if value is None:
        return "info"
    limits = THRESHOLDS.get(key)
    if not limits:
        return "info"
    good, poor = limits
    if value <= good:
        return "healthy"
    if value <= poor:
        return "warning"
    return "error"
