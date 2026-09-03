#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# HostCheck — Üyelik sistemini canlıdan kaldır
#
#   sudo bash deploy/uyelik-kaldir-dagit.sh
#
# `uyelik-dagit.sh`in tersi. Hazır Yanıtlar üyelik ÖNCESİNDEKİ erişim modeline
# döner: okuma anonim, YAZMA Nginx Basic Auth (`limit_except GET HEAD`).
#
# SIRA KRİTİK ve `uyelik-dagit.sh`in TERSİDİR. Nginx'teki `limit_except`
# koruması EN ÖNCE geri konur:
#
#   şimdi        yazma = üyelik (uygulama)
#   nginx sonrası yazma = Basic Auth VE üyelik  → kimse yazamaz (güvenli ara hâl)
#   backend sonrası yazma = Basic Auth           → hedef durum
#
# Ters sırada yapılsaydı, backend'in devreye girmesiyle Nginx'in korumaya
# başlaması arasındaki saniyelerde kütüphane internete YAZILABİLİR olurdu.
#
# Betik idempotenttir: yarıda kalırsa yeniden çalıştırılabilir.
# Geri alma: deploy/uyelik-geri-al.sh <yedek-dizini> (betiğin sonunda yazılır)
#
# DİKKAT: Üye hesapları, oturumlar ve denetim kayıtları SİLİNİR (migration
# 0004_uyelik_kaldir). Yedekteki .db dosyası bunları geri getirmenin tek yolu.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

BETIK_DIZINI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
YEREL="$BETIK_DIZINI/yerel.env"
if [ ! -f "$YEREL" ]; then
  printf '\033[0;31m✗ %s yok.\033[0m\n  Oluşturun:  cp %s/yerel.env.ornek %s\n' \
    "$YEREL" "$BETIK_DIZINI" "$YEREL" >&2
  exit 1
fi
# shellcheck disable=SC1090
. "$YEREL"

SRC=${SRC:-$(dirname "$BETIK_DIZINI")}
DST=/opt/hostcheck/backend
WEB=${WEB_KOKU:?yerel.env içinde WEB_KOKU tanımlı değil}
SVC=hostcheck-backend
NGINX_SITE=${NGINX_SITE:?yerel.env içinde NGINX_SITE tanımlı değil}
PANEL_URL=${PANEL_URL:?yerel.env içinde PANEL_URL tanımlı değil}
YEDEK=/opt/hostcheck/uyelik-yedek-$(date +%Y%m%d-%H%M%S)

bilgi() { printf '\n\033[1;34m▸ %s\033[0m\n' "$*"; }
tamam() { printf '  \033[0;32m✓\033[0m %s\n' "$*"; }
uyari() { printf '  \033[1;33m!\033[0m %s\n' "$*"; }
hata()  { printf '  \033[0;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ── 0. Ön koşullar ───────────────────────────────────────────────────────────
bilgi "Ön koşullar"
[ "$(id -u)" -eq 0 ] || hata "root olarak çalıştırın: sudo bash $0"
[ -d "$DST" ] || hata "Hedef yok: $DST"
[ -d "$WEB" ] || hata "Web kökü yok: $WEB"
[ -f "$NGINX_SITE" ] || hata "Nginx config yok: $NGINX_SITE"
systemctl cat "$SVC" >/dev/null 2>&1 || hata "systemd birimi yok: $SVC"
command -v rsync >/dev/null || hata "rsync kurulu değil"

# Kaynak GERÇEKTEN üyeliksiz mi. Bu kontrol olmadan betik, üyelik hâlâ duran
# bir ağacı dağıtıp Nginx korumasını da koyar; sonuç: kimse yazamaz.
[ -f "$SRC/backend/auth_core.py" ] && hata "Kaynakta üyelik kodu DURUYOR ($SRC/backend/auth_core.py) — yanlış ağaç"
[ -f "$SRC/backend/migrations/versions/0004_uyelik_kaldir.py" ] \
  || hata "Kaynakta 0004_uyelik_kaldir migration'ı yok: $SRC"
grep -q "auth_core" "$SRC/backend/routers/hazir_yanitlar.py" \
  && hata "hazir_yanitlar.py hâlâ auth_core kullanıyor — kaynak yarım"
[ -f "$SRC/frontend/dist/index.html" ] || hata "Frontend build yok: $SRC/frontend/dist (npm run build)"
grep -q 'auth_basic_user_file' "$NGINX_SITE" || hata "Nginx'te Basic Auth yapılandırması yok: $NGINX_SITE"
[ -f /etc/nginx/hostcheck.htpasswd ] || hata "htpasswd dosyası yok: /etc/nginx/hostcheck.htpasswd"
tamam "kaynak üyeliksiz, hedef/web/servis/nginx yerinde"

# ── 1. Yedek ─────────────────────────────────────────────────────────────────
bilgi "Yedek: $YEDEK"
mkdir -p "$YEDEK"
chmod 700 "$YEDEK"
tar czf "$YEDEK/backend.tgz" -C /opt/hostcheck --exclude=venv --exclude=__pycache__ backend
tar czf "$YEDEK/web.tgz" -C "$WEB" .
cp -a "$NGINX_SITE" "$YEDEK/nginx-site.conf"
if [ -f "$DST/.env" ]; then cp -a "$DST/.env" "$YEDEK/.env"; fi
# WAL'daki commit'ler .db dosyasında olmayabilir; checkpoint'siz kopya üye
# hesaplarını eksik yedekler ve geri alma yolunu sessizce bozar.
sudo -u hostcheck "$DST/venv/bin/python" -c "
import sqlite3, sys
c = sqlite3.connect('$DST/hostcheck.db')
c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
c.close()
" || uyari "WAL checkpoint başarısız — yedek yine de alınıyor"
cp -a "$DST/hostcheck.db" "$YEDEK/hostcheck.db"
tamam "backend, web, nginx, .env ve veritabanı yedeklendi"

# ── 2. Nginx ÖNCE: yazma korumasını geri koy ────────────────────────────────
bilgi "Nginx — hazır yanıt YAZMA koruması geri konuyor"
python3 - "$NGINX_SITE" <<'PYEOF'
import re, sys

yol = sys.argv[1]
s = open(yol, encoding="utf-8").read()
orig = s

# 2a. `location /api/hazir-yanitlar` içine limit_except bloğu.
if "limit_except" not in s:
    desen = re.compile(r"(location\s+/api/hazir-yanitlar\s*\{\n)")
    if not desen.search(s):
        sys.exit("HATA: `location /api/hazir-yanitlar {` bulunamadı — config elle düzenlenmeli")
    s = desen.sub(
        r"\1"
        "        limit_except GET HEAD {\n"
        "            auth_basic           $auth_realm;\n"
        "            auth_basic_user_file /etc/nginx/hostcheck.htpasswd;\n"
        "        }\n",
        s, count=1)

# 2b. Artık var olmayan doğrulama ucunun location bloğu — varsa hemen
# üstündeki açıklama satırıyla birlikte. Açıklama deseni bloğa BAĞLI:
# serbest bir `#.*token` deseni config'in başka yerindeki yorumları da silerdi.
s = re.sub(
    r"(?:[ \t]*#[^\n]*[Dd]o[gğ]rulama[^\n]*\n)?"
    r"[ \t]*location\s*=\s*/api/uyelik/dogrula\s*\{[^}]*\}\n",
    "", s)

if s != orig:
    open(yol, "w", encoding="utf-8").write(s)
    print("  config güncellendi")
else:
    print("  config zaten güncel (idempotent)")
PYEOF
nginx -t || hata "nginx -t başarısız — $YEDEK/nginx-site.conf dosyasından geri alın"
systemctl reload nginx
grep -q "limit_except" "$NGINX_SITE" || hata "limit_except bloğu yazılamadı"
tamam "yazma uçları Basic Auth arkasında (bu aşamada kimse yazamaz — beklenen)"

# ── 3. Backend dosyaları ─────────────────────────────────────────────────────
#
# AĞACIN TAMAMI KOPYALANMAZ. `/opt` bir dizi dosyada depodan İLERİDE
# (doğrudan üretime yazılmış sertleştirmeler: mail_health, rdp, ssh,
# ftp/session, dns_history, site_speed/engine …) ve depoda da commit edilmemiş
# başka işler duruyor. `rsync --delete` ile ağacı senkronlamak bu değişikliğin
# kapsamı DIŞINDAKİ dosyaları sessizce geri alırdı.
#
# Bu yüzden yalnızca üyelik kaldırmanın dokunduğu dosyalar kopyalanır. Liste
# büyürse buraya eklenmeli.
bilgi "Backend"

# Çalışma zamanına giren dosyalar. Bunlarda /opt ile depo arasında beklenmedik
# bir fark varsa dağıtım DURUR: üretimde ayrı bir düzenleme olabilir ve
# körlemesine kopyalamak onu siler.
CALISMA_ZAMANI=(
  main.py
  models.py
  routers/hazir_yanitlar.py
  migrations/versions/0004_uyelik_kaldir.py
  requirements.txt
)

# Çalışma zamanında OKUNMAYAN dosyalar: pytest fixture'ı (üretimde
# requirements-dev kurulu değil, hiç import edilmiyor) ve `.env` ŞABLONU
# (uygulama `.env`i okur, `.env.example`i değil). Bunlar da güncellenir ama
# farkları dağıtımı DURDURMAZ — yalnızca bilgi olarak yazılır.
#
# Bu ayrım bilinçli: ilk denemede betik tam da bu iki dosya yüzünden onay
# sorup iptal edildi ve dağıtım nginx adımından sonra yarıda kaldı. Üretim
# davranışını etkilemeyen bir fark, dağıtımı durdurmamalı.
BILGI_AMACLI=(
  .env.example
  tests/conftest.py
  tests/test_hazir_yanitlar_erisim.py
)

KOPYALANACAK=( "${CALISMA_ZAMANI[@]}" "${BILGI_AMACLI[@]}" )

# `git`, root olarak mahmut'un deposuna bakarken "dubious ownership" diyebilir;
# o durumda kontrol sessizce atlanır (aşağıdaki `if` false olur).
DOGRULA=0
if command -v git >/dev/null && git -C "$SRC" rev-parse --git-dir >/dev/null 2>&1; then
  fark_var() {   # $1 = dosya → /opt sürümü HEAD'den farklıysa 0
    [ -f "$DST/$1" ] || return 1
    git -C "$SRC" cat-file -e "HEAD:backend/$1" 2>/dev/null || return 1
    ! diff -q <(git -C "$SRC" show "HEAD:backend/$1" | tr -d '\r') \
              <(tr -d '\r' < "$DST/$1") >/dev/null
  }
  for f in "${BILGI_AMACLI[@]}"; do
    if fark_var "$f"; then
      uyari "$f üretimde depodakinden farklı (çalışma zamanına girmez, güncellenecek)"
    fi
  done
  for f in "${CALISMA_ZAMANI[@]}"; do
    if fark_var "$f"; then
      uyari "$f üretimde depodaki HEAD'den farklı — ÜZERİNE YAZILACAK"
      uyari "  incele: diff <(git -C $SRC show HEAD:backend/$f) $DST/$f"
      DOGRULA=1
    fi
  done
  if [ "$DOGRULA" = "1" ]; then
    if [ "${ONAY:-}" = "evet" ]; then
      uyari "ONAY=evet verildi — farklara rağmen devam ediliyor"
    else
      printf '\n  Üretimde bu değişikliğin dışında düzenleme var. Devam etmek\n'
      printf '  isterseniz tam olarak \033[1mevet\033[0m yazın (Enter iptal eder).\n'
      printf '  Sormadan geçmek için: ONAY=evet sudo -E bash %s\n\n' "$0"
      read -r -p "  Devam edilsin mi? (evet/hayır) " y
      [ "$y" = "evet" ] || hata "iptal edildi — farkları inceleyin"
    fi
  fi
fi

systemctl stop "$SVC"
for f in "${KOPYALANACAK[@]}"; do
  [ -f "$SRC/backend/$f" ] || hata "Kaynakta yok: backend/$f"
  install -D -o hostcheck -g hostcheck -m 644 "$SRC/backend/$f" "$DST/$f"
done
rm -f "$DST/auth_core.py" "$DST/mailer.py" \
      "$DST/routers/uyelik.py" "$DST/routers/yonetim.py" \
      "$DST/tests/test_uyelik.py" "$DST/tests/test_yetki.py"
find "$DST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
tamam "${#KOPYALANACAK[@]} dosya kopyalandı, üyelik modülleri silindi"

# ── 4. .env temizliği ────────────────────────────────────────────────────────
bilgi ".env — kullanılmayan üyelik/SMTP anahtarları"
if [ -f "$DST/.env" ]; then
  # SMTP_PASS artık HİÇBİR kod tarafından okunmuyor ama hâlâ geçerli bir
  # Brevo anahtarı; diskte bırakmanın faydası yok.
  sed -i -E '/^(IZINLI_MAIL_ALANLARI|ADMIN_EPOSTALARI|OTURUM_SURESI_SAAT|OTURUM_UZUN_SURE_GUN|PUBLIC_BASE_URL|SMTP_HOST|SMTP_PORT|SMTP_USER|SMTP_PASS|MAIL_FROM|MAIL_FROM_NAME|MAIL_CIKTI_DIZINI)=/d' "$DST/.env"
  chown hostcheck:hostcheck "$DST/.env"; chmod 600 "$DST/.env"
  tamam "üyelik anahtarları .env'den çıkarıldı (yedekte duruyor)"
fi

# Editör/betik artığı .env kopyaları da aynı sırları taşıyor. Silmiyoruz,
# yedeğe TAŞIYORUZ: içeriğini görmeden silmek geri dönüşü olmayan bir karar.
for artik in "$DST"/.env.save "$DST"/.env.bak "$DST"/.env.eski; do
  if [ -f "$artik" ]; then
    mv "$artik" "$YEDEK/$(basename "$artik")"
    uyari "$(basename "$artik") yedeğe taşındı — eski sırları taşıyor olabilir"
  fi
done

if [ -f "$YEDEK/.env" ]; then
  uyari "Brevo SMTP anahtarı artık HİÇBİR kod tarafından kullanılmıyor:"
  uyari "  • Brevo panelinden anahtarı İPTAL EDİN (yedeklerde açık metin duruyor)"
  uyari "  • Yedek dizini parola hash'leri ve üye e-postaları da içerir: $YEDEK (chmod 700)"
fi

# ── 5. Şema: üyelik tablolarını düşür ────────────────────────────────────────
bilgi "Veritabanı — 0004_uyelik_kaldir"
sudo -u hostcheck env -C "$DST" "$DST/venv/bin/alembic" upgrade head
tamam "üyelik tabloları düşürüldü"

# DROP TABLE sayfaları serbest listeye alır, İÇERİKLERİNİ SİLMEZ: bcrypt
# hash'leri ve e-posta adresleri dosyanın içinde okunabilir hâlde kalır.
# VACUUM dosyayı yeniden yazar. WAL de checkpoint'lenir; aksi hâlde silinen
# satırlar -wal dosyasında durur.
sudo -u hostcheck "$DST/venv/bin/python" -c "
import sqlite3
c = sqlite3.connect('$DST/hostcheck.db')
c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
c.execute('VACUUM')
c.close()
" && tamam "veritabanı VACUUM'landı (parola hash'leri serbest sayfalardan silindi)" \
  || uyari "VACUUM başarısız — silinen satırlar dosyada kalmış olabilir"

# ── 6. Servis ────────────────────────────────────────────────────────────────
bilgi "Servis"
systemctl start "$SVC"

# Sabit `sleep 4` YETMİYOR: açılışta Alembic migration'ları koşuyor, hazır
# yanıt tohumlaması yapılıyor ve Playwright/paramiko import ediliyor. İlk
# denemede servis 4 saniyede henüz dinlemiyordu ve betik sağlıklı bir
# dağıtımı "başarısız" sayıp durdu (frontend adımı hiç çalışmadı).
# Sabit bekleme yerine 60 saniyeye kadar YOKLA.
bilgi_yok=1
for _ in $(seq 1 60); do
  if ! systemctl is-active --quiet "$SVC"; then
    journalctl -u "$SVC" -n 40 --no-pager
    hata "servis kalkmadı"
  fi
  if curl -fsS -m 3 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    bilgi_yok=0
    break
  fi
  sleep 1
done
if [ "$bilgi_yok" = "1" ]; then
  journalctl -u "$SVC" -n 40 --no-pager
  hata "servis 60 sn içinde sağlık ucuna yanıt vermedi"
fi
tamam "servis ayakta"

# ── 7. Frontend ──────────────────────────────────────────────────────────────
bilgi "Frontend"
rsync -a --delete "$SRC/frontend/dist/" "$WEB/"
chown -R www-data:www-data "$WEB"
tamam "$WEB güncellendi"

# ── 8. Doğrulama ─────────────────────────────────────────────────────────────
bilgi "Doğrulama"
kod() { curl -s -o /dev/null -w '%{http_code}' -m 10 "$@"; }
BASARISIZ=0
bekle() {
  local ad=$1 beklenen=$2; shift 2
  local g; g=$(kod "$@")
  if [ "$g" = "$beklenen" ]; then
    printf '  \033[0;32m✓\033[0m %-46s %s\n' "$ad" "$g"
  else
    printf '  \033[0;31m✗\033[0m %-46s %s (beklenen %s)\n' "$ad" "$g" "$beklenen"
    BASARISIZ=1
  fi
}
bekle "GET  /api/hazir-yanitlar (anonim okuma)" 200 "$PANEL_URL/api/hazir-yanitlar"
bekle "POST /api/hazir-yanitlar (anonim YAZMA)" 401 \
      -X POST -H 'Content-Type: application/json' \
      -d '{"title":"x","content":"x","category":"Genel"}' "$PANEL_URL/api/hazir-yanitlar"
bekle "DELETE /api/hazir-yanitlar/1 (anonim)"   401 -X DELETE "$PANEL_URL/api/hazir-yanitlar/1"
bekle "POST /api/uyelik/kayit (kaldırıldı)"     404 \
      -X POST -H 'Content-Type: application/json' -d '{}' "$PANEL_URL/api/uyelik/kayit"
bekle "GET  /api/yonetim/kullanicilar (kaldırıldı)" 404 "$PANEL_URL/api/yonetim/kullanicilar"
bekle "GET  /api/health"                        200 "$PANEL_URL/api/health"

[ "$BASARISIZ" -eq 0 ] || hata "doğrulama BAŞARISIZ — geri alın: sudo bash $BETIK_DIZINI/uyelik-geri-al.sh $YEDEK"

printf '\n\033[1;32m▸ Üyelik kaldırıldı\033[0m\n'
printf '  Yedek       : %s\n' "$YEDEK"
printf '  Geri alma   : sudo bash %s/uyelik-geri-al.sh %s\n' "$BETIK_DIZINI" "$YEDEK"
printf '  Yazma erişimi: Nginx Basic Auth (/etc/nginx/hostcheck.htpasswd)\n\n'
