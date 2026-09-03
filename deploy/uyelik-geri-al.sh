#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# HostCheck — bir dağıtımı yedekten geri al
#
#   sudo bash deploy/uyelik-geri-al.sh /opt/hostcheck/uyelik-yedek-YYYYmmdd-HHMMSS
#
# Backend dosyalarını, veritabanını, frontend build'ini, nginx config'ini ve
# .env'i yedekten geri yükler; ardından servisleri yeniden başlatır.
#
# HER İKİ YÖNDE de çalışır: yedek tarball'ı o anki backend ağacının tamamıdır,
# yani üyeliğin açıldığı ya da KALDIRILDIĞI dağıtımın öncesine döndürür.
# Yedeği üreten betik: `uyelik-kaldir-dagit.sh` (yolu sonunda yazar).
#
# Veritabanı geri yüklemesi YEDEKTEN SONRAKİ HER DEĞİŞİKLİĞİ SİLER — hazır
# yanıt düzenlemeleri ve (varsa) üye hesapları yedek anındaki duruma döner.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

BETIK_DIZINI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
YEREL="$BETIK_DIZINI/yerel.env"
[ -f "$YEREL" ] || { echo "✗ $YEREL yok (bkz. yerel.env.ornek)" >&2; exit 1; }
# shellcheck disable=SC1090
. "$YEREL"

YEDEK=${1:-}
DST=/opt/hostcheck/backend
WEB=${WEB_KOKU:?yerel.env içinde WEB_KOKU tanımlı değil}
SVC=hostcheck-backend
NGINX_SITE=${NGINX_SITE:?yerel.env içinde NGINX_SITE tanımlı değil}

bilgi() { printf '\n\033[1;34m▸ %s\033[0m\n' "$*"; }
tamam() { printf '  \033[0;32m✓\033[0m %s\n' "$*"; }
uyari() { printf '  \033[1;33m!\033[0m %s\n' "$*"; }
hata()  { printf '  \033[0;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || hata "root olarak çalıştırın: sudo bash $0 <yedek-dizini>"
[ -n "$YEDEK" ] || hata "Kullanım: sudo bash $0 /opt/hostcheck/uyelik-yedek-YYYYmmdd-HHMMSS"
[ -d "$YEDEK" ] || hata "Yedek dizini yok: $YEDEK"
[ -f "$YEDEK/backend.tgz" ] || hata "Yedek eksik: $YEDEK/backend.tgz"

printf '\n\033[1;33mDİKKAT\033[0m Bu işlem %s anındaki duruma döner.\n' "$(basename "$YEDEK")"
printf 'Yedekten SONRAKİ tüm hazır yanıt değişiklikleri KAYBOLUR.\n'
read -r -p "Devam edilsin mi? (evet/hayır) " yanit
[ "$yanit" = "evet" ] || hata "iptal edildi"

bilgi "Servis durduruluyor"
systemctl stop "$SVC"
tamam "$SVC durdu"

bilgi "Backend dosyaları"
# Dağıtımın EKLEDİĞİ dosyalar yedekte yoktur ve `tar x` onları silmez; elle
# kaldırılıyor. Her iki yön de listede:
#
#   üyelik açılışını geri alırken  → auth_core/mailer/uyelik/yonetim + 0003
#   üyelik kaldırışını geri alırken → 0004_uyelik_kaldir
#
# 0004 KRİTİK: kalırsa `head` yine 0004 olur ve servis açılışındaki
# `run_migrations()` az önce geri yüklenen üyelik tablolarını sessizce
# yeniden düşürür — geri alma başarılı görünür ama çalışmamıştır.
rm -f "$DST/auth_core.py" "$DST/mailer.py" \
      "$DST/routers/uyelik.py" "$DST/routers/yonetim.py" \
      "$DST/migrations/versions/0003_uyelik.py" \
      "$DST/migrations/versions/0004_uyelik_kaldir.py"
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
  # Yedekte .db yoksa şemanın hangi revizyona çekilmesi gerektiğini betik
  # BİLEMEZ: yön, yedeğin ne zaman alındığına bağlı. Körlemesine downgrade
  # etmek (eski davranış) yanlış yönde çalıştığında tablo siler.
  uyari "Yedekte hostcheck.db YOK — şemaya DOKUNULMADI."
  uyari "Gereken revizyonu elle seçin:"
  uyari "  sudo -u hostcheck env -C $DST $DST/venv/bin/alembic history"
  uyari "  sudo -u hostcheck env -C $DST $DST/venv/bin/alembic downgrade <revizyon>"
fi

bilgi ".env"
if [ -f "$YEDEK/.env" ]; then
  install -o hostcheck -g hostcheck -m 600 "$YEDEK/.env" "$DST/.env"
  tamam ".env geri yüklendi"
else
  uyari "Yedekte .env yok — mevcut .env korundu"
fi

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
D=${PANEL_URL:?}
printf '  GET /api/hazir-yanitlar (anonim, artık 200 olmalı) → %s\n' \
  "$(curl -s -o /dev/null -w '%{http_code}' -m 10 $D/api/hazir-yanitlar)"
printf '  GET /api/health → %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -m 10 $D/api/health)"

printf '\n\033[1;34m▸ Geri alma tamamlandı\033[0m\n  Kaynak yedek: %s\n\n' "$YEDEK"
