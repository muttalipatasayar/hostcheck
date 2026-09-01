#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# HostCheck — Üyelik sistemini canlıya al
#
#   sudo bash deploy/uyelik-dagit.sh
#
# Betik idempotenttir: yarıda kalırsa yeniden çalıştırılabilir.
# Geri alma: deploy/uyelik-geri-al.sh (betiğin sonunda yedek yolunu yazar)
#
# SIRA KRİTİK. Nginx'teki `limit_except` koruması EN SON kaldırılır: önce
# kaldırılsaydı, uygulama katmanı devreye girene kadar hazır yanıt kütüphanesi
# internetteki herkese YAZILABİLİR olurdu.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# Kuruluma özgü değerler (alan adı, yönetici adresi, yollar) depoda DEĞİL:
# deploy/yerel.env .gitignore'da. Depo herkese açık olsa bile altyapı bilgisi
# dışarı sızmaz. Şablon: deploy/yerel.env.ornek
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
PY=$DST/venv/bin/python
# SMTP yapılandırılmamışsa hiç kimse üye olamaz. Bilerek atlamak için: SMTP_ZORUNLU=0
SMTP_ZORUNLU=${SMTP_ZORUNLU:-1}

bilgi() { printf '\n\033[1;34m▸ %s\033[0m\n' "$*"; }
tamam() { printf '  \033[0;32m✓\033[0m %s\n' "$*"; }
uyari() { printf '  \033[1;33m!\033[0m %s\n' "$*"; }
hata()  { printf '  \033[0;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ── 0. Ön koşullar ───────────────────────────────────────────────────────────
bilgi "Ön koşullar"
[ "$(id -u)" -eq 0 ] || hata "root olarak çalıştırın: sudo bash $0"
[ -f "$SRC/backend/auth_core.py" ] || hata "Kaynakta üyelik kodu yok: $SRC"
[ -d "$DST" ] || hata "Hedef yok: $DST"
[ -d "$WEB" ] || hata "Web kökü yok: $WEB"
[ -f "$NGINX_SITE" ] || hata "Nginx config yok: $NGINX_SITE"
systemctl cat "$SVC" >/dev/null 2>&1 || hata "systemd birimi yok: $SVC"
command -v rsync >/dev/null || hata "rsync kurulu değil"
SAHIP=$(stat -c %U "$SRC")
tamam "kaynak ($SAHIP), hedef, web kökü, servis ve nginx yerinde"

# ── 1. .env kontrolü ─────────────────────────────────────────────────────────
bilgi ".env — üyelik anahtarları"
ENVF=$DST/.env
[ -f "$ENVF" ] || hata ".env yok: $ENVF"
cp -a "$ENVF" "/tmp/hostcheck-env-yedek-$(date +%s)"

ekle_yoksa() {   # anahtar  varsayılan
  if ! grep -qE "^$1=" "$ENVF"; then
    printf '%s=%s\n' "$1" "$2" >> "$ENVF"
    uyari "$1 eklendi (varsayılan: '${2:-boş}')"
  fi
}
# Yönetici adresi ZORUNLU. Kodda varsayılanı yok (fail-closed): boş kalırsa
# hiç yönetici olmaz ve panelin yönetim tarafı kimseye açılmaz.
[ -n "${ADMIN_EPOSTALARI:-}" ] || hata "yerel.env içinde ADMIN_EPOSTALARI boş — yönetici hesabı açılamaz"
ekle_yoksa IZINLI_MAIL_ALANLARI "${IZINLI_MAIL_ALANLARI:-}"
ekle_yoksa ADMIN_EPOSTALARI     "$ADMIN_EPOSTALARI"
ekle_yoksa OTURUM_SURESI_SAAT   "12"
ekle_yoksa OTURUM_UZUN_SURE_GUN "30"
ekle_yoksa PUBLIC_BASE_URL      "$PANEL_URL"
ekle_yoksa SMTP_HOST            "smtp-relay.brevo.com"
ekle_yoksa SMTP_PORT            "587"
ekle_yoksa SMTP_USER            ""
ekle_yoksa SMTP_PASS            ""
ekle_yoksa MAIL_FROM            ""
ekle_yoksa MAIL_FROM_NAME       "HostCheck Destek Paneli"
chown hostcheck:hostcheck "$ENVF"; chmod 600 "$ENVF"

if ! grep -qE '^SMTP_USER=.+' "$ENVF" || ! grep -qE '^MAIL_FROM=.+' "$ENVF"; then
  if [ "$SMTP_ZORUNLU" = "1" ]; then
    hata "SMTP_USER / SMTP_PASS / MAIL_FROM boş — kimse üye OLAMAZ.
     Brevo panelinden SMTP anahtarı alıp $ENVF içine yazın, sonra tekrar çalıştırın.
     Bilerek atlamak için: SMTP_ZORUNLU=0 sudo bash $0"
  fi
  uyari "SMTP boş — kayıt ucu 503 döndürecek (SMTP_ZORUNLU=0 ile geçildi)"
fi
grep -qE '^ENV=production' "$ENVF" || uyari "ENV=production değil — çerezler Secure olmayabilir!"
tamam ".env hazır (izinler 600 hostcheck)"

# ── 2. Yedek ─────────────────────────────────────────────────────────────────
bilgi "Yedek: $YEDEK"
install -d -o hostcheck -g hostcheck "$YEDEK"
tar czf "$YEDEK/backend.tgz" -C /opt/hostcheck backend \
    --exclude='backend/venv' --exclude='backend/__pycache__' \
    --exclude='*/__pycache__' 2>/dev/null || true
# SQLite yedeği: WAL'a geçiş dosya biçimini KALICI değiştirir, canlı kopya şart.
sudo -u hostcheck env YEDEK_DIR="$YEDEK" "$DST/venv/bin/python" - <<'PYBACKUP'
import sqlite3, os
kaynak = "/opt/hostcheck/backend/hostcheck.db"
hedef = os.environ["YEDEK_DIR"] + "/hostcheck.db"
a = sqlite3.connect(kaynak); b = sqlite3.connect(hedef)
with b: a.backup(b)
a.close(); b.close()
print("  veritabanı tutarlı biçimde yedeklendi:", hedef)
PYBACKUP
tar czf "$YEDEK/web.tgz" -C "$WEB" . 2>/dev/null || true
cp -a "$NGINX_SITE" "$YEDEK/nginx-site.conf"
cp -a "$ENVF" "$YEDEK/.env"
chown -R hostcheck:hostcheck "$YEDEK"; chmod 700 "$YEDEK"
tamam "backend, veritabanı, web kökü, nginx config ve .env yedeklendi"

# ── 3. Backend dosyaları ─────────────────────────────────────────────────────
bilgi "Backend dosyaları"
# Yalnızca bu işin dokunduğu dosyalar. Diğerlerinde /opt kaynaktan İLERİDE
# olabilir (elle yapılmış sertleştirmeler) — toptan rsync onları geri alırdı.
YENI=(auth_core.py mailer.py routers/uyelik.py routers/yonetim.py
      routers/genel_bakis.py migrations/versions/0003_uyelik.py)
DEGISEN=(main.py models.py database.py dns_core.py
         routers/hazir_yanitlar.py requirements.txt)
for f in "${YENI[@]}" "${DEGISEN[@]}"; do
  [ -f "$SRC/backend/$f" ] || hata "kaynakta yok: $f"
  install -D -o hostcheck -g hostcheck -m 644 "$SRC/backend/$f" "$DST/$f"
done
# Mimari kılavuz: /opt'taki kopya "kimlik doğrulama yok" diyor, artık yanlış.
install -o hostcheck -g hostcheck -m 644 "$SRC/CLAUDE.md" /opt/hostcheck/CLAUDE.md
install -D -o hostcheck -g hostcheck -m 644 "$SRC/deploy/UYELIK.md" /opt/hostcheck/deploy/UYELIK.md
install -D -o hostcheck -g hostcheck -m 640 "$SRC/sast/uyelik-results.md" /opt/hostcheck/sast/uyelik-results.md
tamam "${#YENI[@]} yeni + ${#DEGISEN[@]} güncellenen dosya + belgeler kopyalandı"

# main.py'nin üretim sertleştirmelerini TAŞIDIĞINI doğrula. Kaynak ağacı
# geçmişte bu satırlarda geriydi; sessizce geri almak istemiyoruz.
for imza in "object-src 'none'" "base-uri 'self'" "form-action 'self'" \
            'X-XSS-Protection"] = "0"' "no-store, private"; do
  grep -qF "$imza" "$DST/main.py" || hata "main.py sertleştirmesi kayıp: $imza — $YEDEK/backend.tgz'den geri alın"
done
grep -qF "unsafe-eval" "$DST/main.py" && hata "main.py'de 'unsafe-eval' geri gelmiş — dağıtımı durdurdum"
tamam "CSP ve güvenlik başlığı sertleştirmeleri yerinde"

# ── 4. Bağımlılık ────────────────────────────────────────────────────────────
bilgi "Python bağımlılıkları"
sudo -u hostcheck "$DST/venv/bin/pip" install --quiet 'bcrypt>=4.1'
tamam "bcrypt kurulu ($(sudo -u hostcheck "$PY" -c 'import bcrypt;print(bcrypt.__version__)'))"

# ── 5. Migration — RESTART'TAN ÖNCE ──────────────────────────────────────────
bilgi "Veritabanı şeması"
# Elle çalıştırılıyor: main.py import anında da migration koşuyor, ama orada
# patlarsa servis hiç açılmaz ve DNS/SSL dahil TÜM panel düşer. Burada
# başarısız olursa dağıtım durur, servis eski kodla ayakta kalır.
sudo -u hostcheck env -C "$DST" "$DST/venv/bin/alembic" upgrade head
sudo -u hostcheck env -C "$DST" "$DST/venv/bin/alembic" current
sudo -u hostcheck "$PY" - <<'PYCHK'
import sqlite3
c = sqlite3.connect("/opt/hostcheck/backend/hostcheck.db")
t = {r[0] for r in c.execute("select name from sqlite_master where type='table'")}
eksik = {"kullanicilar","oturumlar","eposta_tokenleri","denetim_kayitlari"} - t
assert not eksik, f"tablo eksik: {eksik}"
print("  journal_mode:", c.execute("pragma journal_mode").fetchone()[0])
PYCHK
chown hostcheck:hostcheck "$DST"/hostcheck.db* 2>/dev/null || true
chmod 640 "$DST"/hostcheck.db 2>/dev/null || true
tamam "üyelik tabloları yerinde, WAL etkin"

# ── 6. Duman testi ───────────────────────────────────────────────────────────
bilgi "Import duman testi"
sudo -u hostcheck env -C "$DST" "$PY" -c "import main; print('  route sayısı:', len(main.app.routes))" \
  || hata "import main başarısız — $YEDEK/backend.tgz'den geri alın"
tamam "uygulama import ediliyor"

# ── 7. Servis ────────────────────────────────────────────────────────────────
bilgi "Servis"
if ! grep -q "forwarded-allow-ips" /etc/systemd/system/$SVC.service 2>/dev/null; then
  cp -a "$SRC/deploy/hostcheck-backend.service" /etc/systemd/system/$SVC.service
  systemctl daemon-reload
  tamam "systemd birimi güncellendi (--forwarded-allow-ips)"
fi
systemctl restart "$SVC"
sleep 4
systemctl is-active --quiet "$SVC" || { journalctl -u "$SVC" -n 40 --no-pager; hata "servis ayağa kalkmadı"; }
curl -fsS -m 8 http://127.0.0.1:8000/api/health >/dev/null || hata "sağlık ucu yanıt vermiyor"
curl -fsS -m 8 http://127.0.0.1:8000/api/uyelik/ayarlar | grep -q izinli_alanlar || hata "üyelik uçları yok"
[ "$(curl -s -o /dev/null -w '%{http_code}' -m 8 http://127.0.0.1:8000/api/hazir-yanitlar)" = "401" ] \
  || hata "hazır yanıtlar anonim erişime AÇIK — dağıtımı durdurdum"
tamam "servis ayakta; hazır yanıtlar anonime kapalı (401)"

# ── 8. Frontend ──────────────────────────────────────────────────────────────
bilgi "Frontend derleme"
# npm nvm altında; sudo secure_path onu PATH'ten siler, login kabuğu şart.
if ! sudo -u "$SAHIP" bash -lc "cd '$SRC/frontend' && npm run build"; then
  hata "npm run build başarısız. Elle: cd $SRC/frontend && npm run build, sonra betiği tekrar çalıştırın"
fi
rsync -a --delete "$SRC/frontend/dist/" "$WEB/"
chown -R www-data:www-data "$WEB"
tamam "dist → $WEB"

# ── 9. Nginx — EN SON ────────────────────────────────────────────────────────
bilgi "Nginx"
"$PY" - "$NGINX_SITE" <<'PYNGINX'
import re, sys, pathlib
p = pathlib.Path(sys.argv[1]); s = p.read_text(encoding="utf-8"); once = s

# 9a. hazir-yanitlar üzerindeki limit_except bloğunu kaldır — yetkilendirme
#     artık uygulamada. Kalsaydı yöneticiye ikinci bir Basic Auth penceresi
#     açardı ve tarayıcı XHR'de o pencereyi gösteremediği için yazma sessizce
#     401 olurdu.
s = re.sub(r"\n[ \t]*limit_except GET HEAD \{[^}]*\}\n", "\n", s)

# 9b. Doğrulama bağlantısı token'ı URL'de taşıyor; access log'a düşmesin.
if "location = /api/uyelik/dogrula" not in s:
    blok = """    # Doğrulama bağlantısı URL'de tek kullanımlık token taşır — log'a yazma.
    location = /api/uyelik/dogrula {
        access_log off;
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }

"""
    s = s.replace("    location /api/ {", blok + "    location /api/ {", 1)

if s != once:
    p.write_text(s, encoding="utf-8")
    print("  nginx config güncellendi")
else:
    print("  nginx config zaten güncel")
PYNGINX
nginx -t || hata "nginx -t başarısız — $YEDEK/nginx-site.conf dosyasını geri koyun"
systemctl reload nginx
tamam "nginx yeniden yüklendi"

# ── 10. Doğrulama ────────────────────────────────────────────────────────────
bilgi "Canlı doğrulama"
D=$PANEL_URL
k() { curl -s -o /dev/null -w '%{http_code}' -m 10 "$@"; }
say() { printf '  %-46s %s\n' "$1" "$2"; }
say "GET /api/health"                   "$(k $D/api/health)  (200)"
say "GET /api/hazir-yanitlar (anonim)"  "$(k $D/api/hazir-yanitlar)  (401)"
say "POST /api/hazir-yanitlar (anonim)" "$(k -X POST -H 'Content-Type: application/json' -d '{}' $D/api/hazir-yanitlar)  (401)"
say "GET /api/yonetim/istatistik"       "$(k $D/api/yonetim/istatistik)  (401)"
say "GET /api/uyelik/ayarlar"           "$(k $D/api/uyelik/ayarlar)  (200)"
say "GET /api/ip/lookup (açık kalmalı)" "$(k "$D/api/ip/lookup?q=1.1.1.1")  (200)"
say "GET /openapi.json (kapalı olmalı)" "$(k $D/openapi.json)  (404)"
say "GET /docs (kapalı olmalı)"         "$(k $D/docs)  (404)"
say "GET /api/ssh/ (Basic Auth sürsün)" "$(k $D/api/ssh/)  (401)"
say "GET / (SPA)"                       "$(k $D/)  (200)"
echo
curl -sI -m 10 $D/api/uyelik/ayarlar | grep -iE 'cache-control|vary' | sed 's/^/  /'

bilgi "Bitti"
cat <<SON
  Yedek     : $YEDEK
  Geri alma : sudo bash $BETIK_DIZINI/uyelik-geri-al.sh $YEDEK

  SIRADAKİ ADIM — yönetici hesabını açın:
    1) $D adresine gidin, kenar çubuğunun altındaki "Üye Ol"a basın
    2) $ADMIN_EPOSTALARI adresiyle kaydolun
    3) Gelen doğrulama e-postasındaki bağlantıya tıklayın
    4) Giriş yapın — rol otomatik "Yönetici" olur (.env: ADMIN_EPOSTALARI)

  E-posta gelmezse: journalctl -u $SVC -n 50 --no-pager | grep -i smtp
SON
