# HostCheck — Subdomain Yayına Alma Rehberi (Linux VPS)

Bu rehber HostCheck'i `dns.aipromt.com.tr` gibi bir subdomain'de,
**HTTPS** ve **iki katmanlı erişim** ile yayına almanız içindir.

## Güvenlik modeli (önce bunu okuyun)

HostCheck'in içinde kullanıcı girişi yoktur. Bunun yerine erişimi **reverse
proxy (Nginx)** katmanında ikiye ayırıyoruz:

| Bölüm | Erişim | Neden |
|---|---|---|
| Hızlı Kontrol, SSL, DNS Toolbox/History/Yayılma, Blacklist, Mail Sağlığı, IP Sorgulama, Hazır Yanıtlar | **Herkese açık** | Bu araçlar yalnızca dışarıya sorgu yapar; hedef sisteme bağlanmaz |
| **SSH, RDP, FTP** | **Yalnızca yönetici (Basic Auth)** | Bu üç araç sunucunuzu *herhangi bir hedefe bağlanmak için bir atlama noktası* yapar. Auth olmadan açık relay / SSRF açığıdır. |

> ⚠️ **Backend'i asla `0.0.0.0`'a bağlamayın.** Sunucu `127.0.0.1:8000`'de dinler,
> dış dünyaya yalnızca Nginx üzerinden HTTPS + Basic Auth ile açılır. Aksi hâlde
> SSH/RDP/FTP tünelleri kimlik doğrulamasız açığa çıkar.

Yönetici kilidi nasıl çalışır: SSH/RDP/FTP araçları bağlanmadan **önce**
`GET /api/admin/ping` çağırır. Nginx bu isteğe (ve WebSocket'lere) `auth_basic`
uygular; tarayıcı bir kez kimlik penceresi açar, sonra kimliği aynı origin için
önbelleğe alır ve WebSocket el sıkışmalarına otomatik ekler.

---

## Ön koşullar

- Ubuntu/Debian bir VPS + root (veya sudo) SSH erişimi
- `dns.aipromt.com.tr` için DNS **A kaydı** sunucunuzun IP'sine yönlenmiş olmalı
  (DNS Toolbox aracının kendisiyle yayıldığını doğrulayabilirsiniz)
- Açık portlar: **80** ve **443** (SSH için 22)

---

## 1) Sistem paketleri

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx apache2-utils \
                    git curl docker.io
sudo systemctl enable --now docker
```

## 2) Kodu sunucuya alın

```bash
sudo mkdir -p /opt/hostcheck
sudo useradd -r -m -d /opt/hostcheck hostcheck        # servis kullanıcısı (root DEĞİL)
# Depoyu /opt/hostcheck içine kopyalayın (git clone veya scp ile):
#   backend/  ve  frontend/  klasörleri /opt/hostcheck altında olmalı
sudo chown -R hostcheck:hostcheck /opt/hostcheck
```

## 3) Backend kurulumu

```bash
sudo -u hostcheck bash
cd /opt/hostcheck/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium     # Hızlı Kontrol ekran görüntüsü
cp /opt/hostcheck/deploy/.env.production.example .env
nano .env                                             # CORS_ORIGINS'i düzenleyin
exit
```

Alembic göçleri uygulama açılışında otomatik çalışır; ayrı adım gerekmez.

## 4) guacd (RDP için)

```bash
docker run -d --name hostcheck-guacd --restart unless-stopped \
  -p 127.0.0.1:4822:4822 guacamole/guacd
docker ps | grep guacd        # çalışıyor mu?
```

RDP kullanmayacaksanız bu adımı atlayabilirsiniz; araç formunda "guacd
çalışmıyor" uyarısı görünür ama diğer her şey çalışır.

## 5) Backend'i systemd ile başlatın

```bash
sudo cp /opt/hostcheck/deploy/hostcheck-backend.service /etc/systemd/system/
# Servis dosyasındaki yolları/kullanıcıyı kontrol edin (varsayılanlar /opt/hostcheck)
sudo systemctl daemon-reload
sudo systemctl enable --now hostcheck-backend
sudo systemctl status hostcheck-backend               # active (running) olmalı
curl -s http://127.0.0.1:8000/api/health              # {"status":"ok",...}
```

## 6) Frontend build'i

Build'i yerel makinenizde alıp `dist/` çıktısını sunucuya kopyalamak en
temizidir (Node sunucuda gerekmez):

```bash
# YEREL makinenizde:
cd frontend && npm install && npm run build
# Oluşan frontend/dist/ içeriğini sunucuya kopyalayın:
scp -r dist/* KULLANICI@SUNUCU:/tmp/hostcheck-dist/
```

```bash
# SUNUCUDA:
sudo mkdir -p /var/www/hostcheck
sudo cp -r /tmp/hostcheck-dist/* /var/www/hostcheck/
sudo chown -R www-data:www-data /var/www/hostcheck
```

> Not: Frontend hep göreli yollar (`/api/...`) ve `window.location` kullanır;
> subdomain'de ekstra ayar gerektirmez.

## 7) Yönetici parolası (SSH/RDP/FTP kilidi)

```bash
sudo htpasswd -c /etc/nginx/hostcheck.htpasswd admin      # parolayı sorar
# Ek yönetici eklemek için (-c OLMADAN, yoksa dosyayı sıfırlar):
# sudo htpasswd /etc/nginx/hostcheck.htpasswd ikinci_kullanici
```

## 8) Nginx reverse proxy

```bash
sudo cp /opt/hostcheck/deploy/nginx-hostcheck.conf /etc/nginx/sites-available/hostcheck
sudo nano /etc/nginx/sites-available/hostcheck        # dns.aipromt.com.tr yerlerini değiştirin
sudo ln -s /etc/nginx/sites-available/hostcheck /etc/nginx/sites-enabled/
sudo nginx -t                                         # sözdizimi testi
sudo systemctl reload nginx
```

## 9) HTTPS (Let's Encrypt)

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d dns.aipromt.com.tr
# certbot ssl_certificate satırlarını otomatik ayarlar ve yenilemeyi kurar.
sudo systemctl reload nginx
```

## 10) Güvenlik duvarı

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'      # 80 + 443
sudo ufw enable
```

---

## Doğrulama (yayın sonrası)

1. `https://dns.aipromt.com.tr` açılıyor, kilit (HTTPS) yeşil.
2. **Genel araç**: DNS Toolbox → `example.com` → A sorgusu çalışıyor (kimlik sorulmuyor).
3. **Yönetici araç**: SSH Erişimi → bir sunucuya Bağlan → tarayıcı **kimlik penceresi** açıyor;
   `admin` + parolanızla giriş → terminal geliyor. (İptal ederseniz "Yönetici erişimi gerekli" uyarısı.)
4. **RDP**: guacd rozeti yeşil → Windows sunucuya bağlan → pano senkronu çalışıyor.
5. Gizli pencerede SSH sekmesine gidip Bağlan deyin — kimlik sorulmalı (auth gerçekten aktif mi?).

---

## Sık karşılaşılan sorunlar

| Belirti | Neden / Çözüm |
|---|---|
| SSH/RDP/FTP'de kimlik penceresi çıkmıyor, WebSocket kapanıyor | `htpasswd` dosyası yok/yanlış yol, ya da Nginx bloklarında realm string'leri farklı. Hepsi aynı `$auth_realm` kullanmalı. |
| RDP "guacd çalışmıyor" | `docker ps` ile guacd'ı kontrol edin; `docker start hostcheck-guacd`. |
| RDP bağlanmıyor (Windows) | Araç formunda **Güvenlik Modu**'nu `NLA` yapın (modern Windows varsayılanı). |
| Ekran görüntüsü (Hızlı Kontrol) boş | `playwright install --with-deps chromium` çalıştırıldı mı? Servis `hostcheck` kullanıcısıyla mı koşuyor (root'ta sandbox çalışmaz)? |
| Büyük dosya yüklenmiyor | Nginx `client_max_body_size` (550M) ve backend `MAX_UPLOAD_BYTES` uyumlu mu? |
| 502 Bad Gateway | Backend düşmüş: `sudo systemctl status hostcheck-backend`, `journalctl -u hostcheck-backend -n 50`. |
| RDP/FTP oturumu rastgele kopuyor | systemd'de `--workers 1` olduğundan emin olun. Çoklu worker bilet/oturum deposunu böler. |

## Güncelleme

```bash
# Yeni kodu /opt/hostcheck'e çekin, sonra:
sudo -u hostcheck bash -c 'cd /opt/hostcheck/backend && source venv/bin/activate && pip install -r requirements.txt'
sudo systemctl restart hostcheck-backend
# Frontend değiştiyse: yerelde npm run build → dist'i /var/www/hostcheck'e kopyalayın
```

---

## Cloudflare kullanıyorsanız

- SSL/TLS modunu **Full (strict)** yapın (origin'de gerçek Let's Encrypt sertifikası var).
- WebSocket'ler (SSH/RDP/FTP) için Cloudflare'de **WebSocket** ayarı açık olmalı
  (Network sekmesi — genelde varsayılan açık).
- Büyük FTP yüklemelerinde Cloudflare'in 100 MB (ücretsiz plan) istek gövdesi
  sınırına takılabilirsiniz; bu durumda o subdomain'i "DNS only" (gri bulut)
  yapıp doğrudan origin'e bağlanın veya yükleme boyutunu bölün.
