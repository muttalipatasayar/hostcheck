#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# HostCheck — Üyelik dağıtımını geri al
#
#   sudo bash deploy/uyelik-geri-al.sh /opt/hostcheck/uyelik-yedek-YYYYmmdd-HHMMSS
#
# Backend dosyalarını, veritabanını, frontend build'ini, nginx config'ini ve
# .env'i yedekten geri yükler; ardından servisleri yeniden başlatır.
#
# Veritabanı geri yüklemesi ÜYELİK SONRASI AÇILAN HESAPLARI SİLER — yedek
# anındaki duruma döner. Hazır yanıtlar da o ana döner.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

YEDEK=${1:-}
DST=/opt/hostcheck/backend
WEB=/var/www/dns.aipromt.com.tr
SVC=hostcheck-backend
NGINX_SITE=/etc/nginx/sites-available/dns.aipromt.com.tr

bilgi() { printf '\n\033[1;34m▸ %s\033[0m\n' "$*"; }
tamam() { printf '  \033[0;32m✓\033[0m %s\n' "$*"; }
hata()  { printf '  \033[0;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || hata "root olarak çalıştırın: sudo bash $0 <yedek-dizini>"
[ -n "$YEDEK" ] || hata "Kullanım: sudo bash $0 /opt/hostcheck/uyelik-yedek-YYYYmmdd-HHMMSS"
[ -d "$YEDEK" ] || hata "Yedek dizini yok: $YEDEK"
[ -f "$YEDEK/backend.tgz" ] || hata "Yedek eksik: $YEDEK/backend.tgz"

printf '\n\033[1;33mDİKKAT\033[0m Bu işlem %s anındaki duruma döner.\n' "$(basename "$YEDEK")"
printf 'Yedekten SONRA açılan üye hesapları ve hazır yanıt değişiklikleri KAYBOLUR.\n'
read -r -p "Devam edilsin mi? (evet/hayır) " yanit
[ "$yanit" = "evet" ] || hata "iptal edildi"

bilgi "Servis durduruluyor"
systemctl stop "$SVC"
tamam "$SVC durdu"

bilgi "Backend dosyaları"
# Yeni gelen üyelik dosyaları yedekte YOK; tar açmak onları silmez, o yüzden
# elle kaldırılıyor. Kalsalardı eski main.py onları import etmeyeceği için
# zararsız olurdu ama şema/kod karışıklığı bırakmayalım.
rm -f "$DST/auth_core.py" "$DST/mailer.py" \
      "$DST/routers/uyelik.py" "$DST/routers/yonetim.py" \
      "$DST/migrations/versions/0003_uyelik.py"
find "$DST" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
tar xzf "$YEDEK/backend.tgz" -C /opt/hostcheck
chown -R hostcheck:hostcheck "$DST"
tamam "backend geri yüklendi"

bilgi "Veritabanı"
if [ -f "$YEDEK/hostcheck.db" ]; then
  rm -f "$DST/hostcheck.db-wal" "$DST/hostcheck.db-shm"
  install -o hostcheck -g hostcheck -m 640 "$YEDEK/hostcheck.db" "$DST/hostcheck.db"
  tamam "veritabanı yedekten geri yüklendi"
else
  # Yedek yoksa en azından şemayı geriye al.
  sudo -u hostcheck env -C "$DST" "$DST/venv/bin/alembic" downgrade 0002_site_hizi || true
  tamam "şema 0002_site_hizi'ye düşürüldü"
fi

bilgi ".env"
[ -f "$YEDEK/.env" ] && install -o hostcheck -g hostcheck -m 600 "$YEDEK/.env" "$DST/.env" \
  && tamam ".env geri yüklendi"

bilgi "Frontend"
if [ -f "$YEDEK/web.tgz" ]; then
  rm -rf "${WEB:?}"/*
  tar xzf "$YEDEK/web.tgz" -C "$WEB"
  chown -R www-data:www-data "$WEB"
  tamam "$WEB geri yüklendi"
fi

bilgi "Nginx"
if [ -f "$YEDEK/nginx-site.conf" ]; then
  cp -a "$YEDEK/nginx-site.conf" "$NGINX_SITE"
  nginx -t || hata "nginx -t başarısız — $NGINX_SITE dosyasını elle kontrol edin"
  systemctl reload nginx
  tamam "nginx config geri yüklendi ve yeniden yüklendi"
fi

bilgi "Servis"
systemctl start "$SVC"
sleep 4
systemctl is-active --quiet "$SVC" || { journalctl -u "$SVC" -n 40 --no-pager; hata "servis kalkmadı"; }
curl -fsS -m 8 http://127.0.0.1:8000/api/health >/dev/null || hata "sağlık ucu yanıt vermiyor"
tamam "servis ayakta"

bilgi "Doğrulama"
D=https://dns.aipromt.com.tr
printf '  GET /api/hazir-yanitlar (anonim, artık 200 olmalı) → %s\n' \
  "$(curl -s -o /dev/null -w '%{http_code}' -m 10 $D/api/hazir-yanitlar)"
printf '  GET /api/health → %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -m 10 $D/api/health)"

printf '\n\033[1;34m▸ Geri alma tamamlandı\033[0m\n  Kaynak yedek: %s\n\n' "$YEDEK"
