#!/usr/bin/env bash
# HostCheck — yayın sonrası güvenlik doğrulaması.
# Kullanım:  bash verify-deployment.sh dns.aipromt.com.tr
#
# Doğrular:
#   • HTTPS ayakta ve HTTP→HTTPS yönleniyor
#   • Genel araçlar auth'suz erişilebilir (200)
#   • SSH/RDP/FTP/admin uçları auth ZORUNLU kılıyor (401)  ← en kritik
#
# 401 beklenen yerde 200/404 görürseniz: YÖNETİCİ UÇLARI AÇIKTA. Nginx
# auth_basic yapılandırmasını ve htpasswd yolunu düzeltin.

set -u
HOST="${1:-}"
if [ -z "$HOST" ]; then
  echo "Kullanım: bash verify-deployment.sh dns.aipromt.com.tr"
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
