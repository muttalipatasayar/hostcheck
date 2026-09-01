# Üyelik Sistemi — Kurulum ve İşletme

Panelin Hazır Yanıtlar bölümü artık üyelik ister; ekleme/düzenleme/silme
yalnızca yöneticiye açıktır. Diğer araçlar (DNS, SSL, Site Hızı, IP…) eskisi
gibi herkese açık kalır; SSH/RDP/FTP ise Nginx Basic Auth ile korunmaya
devam eder.

---

## 1. Brevo SMTP hesabı (bir kerelik, ~10 dakika)

Doğrulama ve parola sıfırlama e-postaları buradan gider. Ücretsiz katman
**günde 300 mail** — panelin ihtiyacının kat kat üstünde.

1. https://www.brevo.com üzerinden ücretsiz hesap açın.
2. **Senders, Domains & Dedicated IPs → Domains → Add a domain** ile
   **kendi kontrol ettiğiniz** bir alan adını ekleyin (örn. `aipromt.com.tr`)
   ve Brevo'nun verdiği **DKIM + SPF (Brevo code)** kayıtlarını DNS'e girin.

   > **`natro.com` KULLANMAYIN.** O alan adının DNS'i sizde değil; SPF/DKIM
   > kuramazsınız ve Microsoft 365 mailleri doğrudan karantinaya atar —
   > doğrulama e-postası hiç ulaşmaz. Gönderen adres kontrol ettiğiniz bir
   > alan adına ait olmalı; **alıcılar** yine yalnızca `@natro.com` /
   > `@team.blue` olur.

3. **SMTP & API → SMTP** sekmesinden bir **SMTP key** üretin.
4. Sunucuda `/opt/hostcheck/backend/.env` içine yazın:

```ini
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=hesabinizin@giris-adresi     # Brevo'nun "Login" olarak gösterdiği değer
SMTP_PASS=xsmtpsib-…                   # üretilen SMTP key (hesap parolası DEĞİL)
MAIL_FROM=hostcheck@aipromt.com.tr     # Brevo'da DOĞRULANMIŞ gönderici
MAIL_FROM_NAME=HostCheck Destek Paneli
PUBLIC_BASE_URL=https://dns.aipromt.com.tr
```

Dosya `hostcheck` kullanıcısına ait ve `600` izinli olmalı:
```bash
sudo chown hostcheck:hostcheck /opt/hostcheck/backend/.env
sudo chmod 600 /opt/hostcheck/backend/.env
```

---

## 2. Dağıtım

```bash
sudo bash /path/to/hostcheck-src/deploy/uyelik-dagit.sh
```

Betik sırayla: `.env` anahtarlarını tamamlar → backend + veritabanı + web kökü +
nginx config yedeği alır → dosyaları kopyalar → `main.py`'nin CSP
sertleştirmelerini taşıdığını **doğrular** → `alembic upgrade head` →
`import main` duman testi → servisi yeniden başlatır → frontend'i derleyip
yayına alır → **en son** Nginx'teki eski `limit_except` korumasını kaldırır.

**Sıra neden böyle:** Nginx koruması önce kaldırılsaydı, yeni backend devreye
girene kadar hazır yanıt kütüphanesi internetteki herkese yazılabilir olurdu.

Betik `SMTP_USER`/`MAIL_FROM` boşsa **durur** — kimse üye olamayacağı için.
Bilerek geçmek isterseniz: `SMTP_ZORUNLU=0 sudo bash …`

### Geri alma

```bash
sudo bash /path/to/hostcheck-src/deploy/uyelik-geri-al.sh /opt/hostcheck/uyelik-yedek-YYYYmmdd-HHMMSS
```

Yedek yolu dağıtım betiğinin sonunda yazılır. Geri alma, yedekten sonra açılan
üye hesaplarını ve hazır yanıt değişikliklerini siler; betik onay ister.

---

## 3. İlk yönetici hesabı

Yönetici, veritabanına elle eklenmez — normal kayıt akışından geçer ve
`.env`'deki `ADMIN_EPOSTALARI` listesinde olduğu için doğrulandığı anda
yönetici olur.

1. https://dns.aipromt.com.tr — kenar çubuğunun altındaki **Üye Ol**
2. `yonetici@sirketiniz.com`, ad soyad, en az 10 karakterli parola
3. Gelen doğrulama e-postasındaki bağlantıya tıklayın
4. Giriş yapın → kenar çubuğunda **Yönetim** sekmesi belirir

Bu hesap panelden **düşürülemez ve silinemez** (`.env`'de sabit). Rolü
değiştirmek için `.env`'i düzenleyip servisi yeniden başlatmak gerekir.

---

## 4. Günlük işletme

| İş | Nerede |
|---|---|
| Üye listesi, askıya alma, yönetici yapma, silme | Yönetim → Kullanıcılar |
| Hazır yanıt ekle/düzenle/sil | Hazır Yanıtlar sekmesi **veya** Yönetim → Hazır Yanıtlar |
| Kim ne zaman ne yaptı | Yönetim → Denetim Kaydı |
| Üye sayısı, hatalı giriş, en çok kullanılan yanıtlar | Yönetim → İstatistikler |
| Parolasını unutan üye | Giriş ekranı → "Şifremi unuttum" (kendi halleder) |
| Şüpheli hesabı anında kesmek | Kullanıcılar → **Askıya al** (açık oturumları da düşer) |

Yeni bir üye e-postasını doğruladığında `ADMIN_EPOSTALARI`'ndaki adreslere
bilgilendirme maili gider.

---

## 5. Sorun giderme

**Doğrulama e-postası gelmiyor**
```bash
sudo journalctl -u hostcheck-backend -n 80 --no-pager | grep -i smtp
```
`SMTP yapılandırılmamış` → `.env` eksik. `SMTP hatası: SMTPAuthenticationError`
→ `SMTP_USER`/`SMTP_PASS` yanlış (key mi, hesap parolası mı?). Mail gidiyor ama
ulaşmıyorsa Brevo panelindeki **Logs** bölümüne bakın — çoğunlukla SPF/DKIM
eksikliğinden reddedilmiştir.

**Giriş yapılıyor ama sayfa yenilenince oturum düşüyor**
Çerezler `Secure` işaretli; site HTTPS'ten servis edilmeli ve `.env`'de
`ENV=production` olmalı. `ENV` yanlışsa çerez adı da değişir (`__Host-` öneki).

**"Oturum doğrulaması başarısız" (403)**
CSRF çerezi okunamıyor. Tarayıcı çerezleri engelliyor olabilir; sekmeyi
yenileyip tekrar giriş yapın. Sürüyorsa `Set-Cookie` başlığında `Path=/`
olduğunu doğrulayın.

**Hesabım kilitlendi**
5 hatalı denemeden sonra 15 dakika. Beklemek yeterli; acele varsa yönetici
Kullanıcılar sekmesinden hesabı askıya alıp geri açtığında sayaç sıfırlanmaz —
en hızlısı "Şifremi unuttum" akışıdır (kilidi de sıfırlar).

**Panel tamamen açılmıyor (dağıtımdan sonra)**
```bash
sudo systemctl status hostcheck-backend
sudo journalctl -u hostcheck-backend -n 60 --no-pager
```
Migration hatasıysa geri alma betiğini çalıştırın.

---

## 6. Bilinmesi gerekenler

- **Üyelikten çıkış, Basic Auth'u temizlemez.** SSH/RDP/FTP hâlâ ayrı bir
  katman; panelden çıkış yapan birinin tarayıcısında o kimlik önbellekte
  kalır. Tam çıkış için tarayıcının kapatılması gerekir.
- **Tek worker zorunluluğu sürüyor** (RDP bileti, FTP oturumu, Site Hızı
  kuyruğu süreç içi). Üyelik oturumları veritabanında olduğu için bu kısıtı
  üyelik getirmedi, ama kaldırmıyor da.
- **Denetim kaydı 20.000 satırda dönüyor.** Uzun süreli saklama gerekiyorsa
  düzenli dışa aktarım gerekir.
- **Alan adı listesi tam eşleşmedir.** `natro.com` yazmak
  `mail.natro.com` adresini KABUL ETMEZ; gerekiyorsa `IZINLI_MAIL_ALANLARI`
  listesine ayrıca eklenmeli.
