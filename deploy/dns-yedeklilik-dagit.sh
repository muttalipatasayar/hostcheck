#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# HostCheck — DNS yedeklilik düzeltmesini canlıya al
#
#   sudo bash deploy/dns-yedeklilik-dagit.sh
#
# Ne düzeltiyor:
#   1) dns_core        — resolver'da timeout == lifetime olduğu için listedeki
#                        İLK sunucu bütçenin tamamını yiyordu; 8.8.8.8'e giden
#                        UDP/53 bu ağda filtreli olduğundan panelin TÜM DNS
#                        teşhisi sessizce yanlış cevap veriyordu.
#   2) dns_toolbox     — bloklayan DNS işi ayrılmış havuza alındı; DKIM
#                        otomatik keşfi varsayılan havuzu (SSRF kapısı, mailer)
#                        tıkıyordu.
#   3) quick_check     — aynı sınıf: istek başına ~6 thread, 2 eşzamanlı istek
#                        varsayılan havuzu dolduruyordu.
#   4) blacklist       — alan adı özel/yerel adrese çözülünce RBL sorgusu
#                        yapılıyordu (127.0.0.1 literal'i engelli, takma adı
#                        değil).
#
# Betik idempotenttir. Geri alma yolu sonda yazdırılır.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

SRC=${SRC:-/home/mahmut/hostcheck-src/backend}
DST=/opt/hostcheck/backend
SVC=hostcheck-backend
YEDEK=/opt/hostcheck/dns-yedek-$(date +%Y%m%d-%H%M%S)

DOSYALAR=(
  dns_core.py
  routers/dns_toolbox.py
  routers/quick_check.py
  routers/dns_history.py
  routers/blacklist.py
)

bilgi() { printf '\n\033[1;34m▸ %s\033[0m\n' "$*"; }
ok()    { printf '\033[0;32m  ✓ %s\033[0m\n' "$*"; }
hata()  { printf '\033[0;31m  ✗ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || hata "sudo ile çalıştırın"
[ -d "$SRC" ] || hata "kaynak yok: $SRC"

# Kaynak GERÇEKTEN düzeltmeyi içeriyor mu. Bu kontrol olmadan eski bir
# checkout sessizce dağıtılır ve betik "başarılı" der.
grep -q "sure_paylastir" "$SRC/dns_core.py" \
  || hata "kaynakta düzeltme yok ($SRC/dns_core.py içinde sure_paylastir bulunamadı)"
grep -q "_DNS_EXECUTOR" "$SRC/routers/dns_toolbox.py" \
  || hata "kaynakta ayrılmış havuz yok: routers/dns_toolbox.py"

bilgi "Yedek alınıyor → $YEDEK"
mkdir -p "$YEDEK/routers"
for f in "${DOSYALAR[@]}"; do
  cp -p "$DST/$f" "$YEDEK/$f"
done
ok "$(printf '%s ' "${DOSYALAR[@]}")yedeklendi"

bilgi "Söz dizimi kaynakta doğrulanıyor (kopyalamadan ÖNCE)"
for f in "${DOSYALAR[@]}"; do
  "$DST/venv/bin/python" -m py_compile "$SRC/$f" || hata "$f derlenmedi"
done
ok "hepsi derlendi"

bilgi "Dosyalar kopyalanıyor"
for f in "${DOSYALAR[@]}"; do
  install -o hostcheck -g hostcheck -m 644 "$SRC/$f" "$DST/$f"
  ok "$f"
done

bilgi "Uygulama import ediliyor (servisi yeniden başlatmadan önce)"
( cd "$DST" && sudo -u hostcheck "$DST/venv/bin/python" -c "import main" ) \
  || { bilgi "GERİ ALINIYOR"; for f in "${DOSYALAR[@]}"; do cp -p "$YEDEK/$f" "$DST/$f"; done; hata "import başarısız — geri alındı"; }
ok "import temiz"

bilgi "Servis yeniden başlatılıyor"
systemctl restart "$SVC"

# Sabit `sleep 3` YETMİYOR: yalnızca `import main` ~2.6 sn sürüyor, üstüne
# uvicorn açılışı, Alembic ve hazır yanıt tohumlaması biniyor. Ölçümde servis
# 4 sn'de henüz dinlemiyordu; sabit bekleme, SAĞLIKLI bir dağıtımı
# "başarısız" gösterip aşağıdaki duman testini ham bir traceback ile
# patlatıyordu. 60 sn'ye kadar yokla.
hazir=0
for _ in $(seq 1 60); do
  systemctl is-active --quiet "$SVC" \
    || { journalctl -u "$SVC" -n 50 --no-pager; hata "servis ayağa kalkmadı"; }
  if curl -fsS -m 3 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then hazir=1; break; fi
  sleep 1
done
[ "$hazir" = "1" ] || { journalctl -u "$SVC" -n 50 --no-pager; hata "servis 60 sn içinde sağlık ucuna yanıt vermedi"; }
ok "$SVC çalışıyor ve yanıt veriyor"

bilgi "Duman testi — DNS artık yedeğe düşebiliyor mu?"
for tip in A NS MX; do
  yanit=$(curl -s -m 30 -X POST http://127.0.0.1:8000/api/dns-toolbox/query \
    -H 'Content-Type: application/json' \
    -d "{\"domain\":\"example.com\",\"record_type\":\"$tip\"}")
  # `|| true`: yanıt boş ya da JSON değilse `set -e` betiği ham bir
  # JSONDecodeError ile düşürüyordu; hangi adımda ne olduğu görünmüyordu.
  durum=$(printf '%s' "$yanit" | "$DST/venv/bin/python" -c \
    'import sys,json
try:
    print(json.load(sys.stdin).get("status","<status yok>"))
except Exception:
    print("<JSON değil>")' 2>/dev/null || true)
  [ "$durum" = "found" ] || hata "$tip sorgusu '$durum' döndü (beklenen: found) — geri al: $YEDEK"
  ok "$tip → found"
done

printf '\n\033[0;32m✔ Dağıtım tamam.\033[0m\n'
printf '  Geri alma:\n'
printf '    sudo cp -p %s/dns_core.py %s/\n' "$YEDEK" "$DST"
printf '    sudo cp -p %s/routers/*.py %s/routers/\n' "$YEDEK" "$DST"
printf '    sudo systemctl restart %s\n' "$SVC"
