#!/usr/bin/env bash
# HostCheck — yayın sonrası güvenlik doğrulaması.
# Kullanım:  bash verify-deployment.sh panel.ornek.com
#
# Doğrular:
#   • HTTPS ayakta ve HTTP→HTTPS yönleniyor
#   • Genel araçlar auth'suz erişilebilir (200)
#   • SSH/RDP/FTP/admin uçları auth ZORUNLU kılıyor (401)  ← en kritik
#   • Hazır Yanıtlar: okuma açık (200), YAZMA auth zorunlu (401)  ← en kritik
#
# 401 beklenen yerde 200/404 görürseniz: YÖNETİCİ UÇLARI AÇIKTA. Nginx
# auth_basic yapılandırmasını ve htpasswd yolunu düzeltin.

set -u
HOST="${1:-}"
if [ -z "$HOST" ]; then
  echo "Kullanım: bash verify-deployment.sh panel.ornek.com"
  exit 2
fi

BASE="https://$HOST"
fail=0
pass=0

code() { curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$@"; }

check() {  # açıklama  beklenen  gerçek
  local desc="$1" expect="$2" actual="$3"
  if [ "$actual" = "$expect" ]; then
    echo "  ✓ $desc (HTTP $actual)"
    pass=$((pass+1))
  else
    echo "  ✗ $desc — beklenen $expect, gelen $actual"
    fail=$((fail+1))
  fi
}

echo "── HTTPS / yönlendirme ────────────────────────────────"
check "HTTP → HTTPS yönlendiriyor" "301" "$(code -I "http://$HOST/")"
check "HTTPS ana sayfa açılıyor"    "200" "$(code "$BASE/")"
check "API sağlık ucu"              "200" "$(code "$BASE/api/health")"

echo "── Genel araçlar (auth OLMADAN erişilebilmeli) ────────"
check "DNS Toolbox sorgusu" "200" \
  "$(code -X POST -H 'Content-Type: application/json' \
       -d '{"domain":"example.com","record_type":"A"}' \
       "$BASE/api/dns-toolbox/query")"
check "IP Sorgulama" "200" "$(code "$BASE/api/ip/lookup?q=8.8.8.8")"
check "Hazır Yanıtlar okunabiliyor" "200" "$(code "$BASE/api/hazir-yanitlar")"

# Hazır yanıt YAZMA uçlarının TEK koruması Nginx'teki `limit_except GET HEAD`
# bloğudur — uygulamada karşılığı yok (üyelik 3 Eylül 2026'da geri alındı).
# Burada 201/200/422 görürseniz kütüphane internete YAZILABİLİR durumdadır:
# 89 hazır metin müşterilere kopyalanıyor, yani kimlik avı bağlantısı
# dağıtmanın doğrudan yolu. deploy/nginx-hostcheck.conf ile karşılaştırın.
echo "── Hazır Yanıtlar YAZMA (auth OLMADAN 401 dönmeli) ────"
check "POST /api/hazir-yanitlar kilitli" "401" \
  "$(code -X POST -H 'Content-Type: application/json' \
       -d '{"title":"x","content":"x","category":"Genel"}' \
       "$BASE/api/hazir-yanitlar")"
check "DELETE /api/hazir-yanitlar/1 kilitli" "401" \
  "$(code -X DELETE "$BASE/api/hazir-yanitlar/1")"
check "PATCH .../1/pin kilitli" "401" \
  "$(code -X PATCH "$BASE/api/hazir-yanitlar/1/pin")"
check "POST .../kategoriler kilitli" "401" \
  "$(code -X POST -H 'Content-Type: application/json' \
       -d '{"name":"x","color":"#111111"}' \
       "$BASE/api/hazir-yanitlar/kategoriler")"

echo "── Kaldırılan üyelik uçları (404 dönmeli) ─────────────"
check "uyelik/kayit yok" "404" \
  "$(code -X POST -H 'Content-Type: application/json' -d '{}' "$BASE/api/uyelik/kayit")"
check "yonetim/kullanicilar yok" "404" "$(code "$BASE/api/yonetim/kullanicilar")"

echo "── Yönetici uçları (auth OLMADAN 401 dönmeli) ─────────"
check "admin/ping kilitli"   "401" "$(code "$BASE/api/admin/ping")"
check "SSH WS ucu kilitli"   "401" "$(code "$BASE/api/ssh/ws")"
check "RDP session kilitli"  "401" "$(code -X POST "$BASE/api/rdp/session")"
check "RDP guacd-status kilitli" "401" "$(code "$BASE/api/rdp/guacd-status")"
check "FTP session kilitli"  "401" "$(code -X POST "$BASE/api/ftp/session")"

echo
if [ "$fail" -eq 0 ]; then
  echo "SONUÇ: TÜM KONTROLLER GEÇTİ ($pass) — yönetici uçları güvende."
  exit 0
else
  echo "SONUÇ: $fail KONTROL BAŞARISIZ, $pass geçti."
  echo "DİKKAT: 401 beklenen yerde başka kod gördüyseniz yönetici uçları AÇIKTA olabilir."
  exit 1
fi
