# Hata kodu analiz veritabanı
# Her hata için: olası nedenler, teknisyen adımları, müşteri mesajı tonu

ERROR_DB = {

    # ─── WINDOWS / IIS ───────────────────────────────────────────────────────

    "403": {
        "platform": "Windows/IIS",
        "title": "403 Forbidden — Erişim Engellendi",
        "causes": [
            "Dizin listeleme (Directory Browsing) kapalı ve index dosyası yok",
            "IIS_IUSRS veya IUSR kullanıcısının klasör/dosya okuma izni yok",
            "web.config içinde IP kısıtlaması tanımlanmış",
            "Request Filtering kuralı isteği engelliyor",
        ],
        "tech_steps": [
            "IIS Manager → Site → Authentication: Anonymous Authentication aktif mi kontrol et",
            "Klasör izinlerini kontrol et: IIS_IUSRS grubuna Read & Execute izni ver",
            "web.config içinde <authorization> veya <ipSecurity> bloğu var mı bak",
            "IIS Manager → Request Filtering → Hidden Segments / File Extensions kontrol et",
            "Event Viewer → Windows Logs → Application altında hata kaydı var mı bak",
        ],
        "customer_action": False,
        "draft": "Sitenizde erişim kısıtlaması tespit edildi. Sunucu tarafında gerekli izin düzenlemeleri yapılacaktır.",
    },

    "503": {
        "platform": "Windows/IIS",
        "title": "503 Service Unavailable — Servis Kullanılamıyor",
        "causes": [
            "IIS Application Pool durdurulmuş veya çökmüş",
            "Application Pool kimliği (identity) hatalı şifre nedeniyle çalışamıyor",
            "Sunucuda kaynak tükenmesi (RAM/CPU limiti)",
            "Rapid-Fail Protection devreye girmiş (uygulama art arda çökmüş)",
        ],
        "tech_steps": [
            "IIS Manager → Application Pools → ilgili pool'u bul → durumunu kontrol et",
            "Pool durdurulmuşsa: sağ tık → Start",
            "Pool kimlik bilgilerini kontrol et: Advanced Settings → Identity",
            "Event Viewer → Windows Logs → System: 'WAS' kaynaklı hata var mı bak",
            "Rapid-Fail Protection devredeyse: Advanced Settings → Rapid-Fail Protection → False yap, pool'u başlat",
        ],
        "customer_action": False,
        "draft": "Sunucunuzda uygulama havuzu durma sorunu tespit edildi. Teknik ekibimiz gerekli işlemleri gerçekleştiriyor.",
    },

    "503.3": {
        "platform": "Windows/IIS",
        "title": "503.3 — ASP.NET Core Uygulama Başlatma Hatası",
        "causes": [
            "ASP.NET Core uygulaması başlatma sırasında hata aldı (startup exception)",
            "App_Data veya logs klasörüne yazma izni yok",
            ".NET Core runtime sürüm uyumsuzluğu",
            "Bağlantı dizesi (connection string) hatası",
            "Eksik environment variable veya appsettings.json hatası",
        ],
        "tech_steps": [
            "IIS Manager → Application Pools → ilgili pool'un .NET CLR Version: 'No Managed Code' olduğunu doğrula",
            "web.config içinde <aspNetCore> bloğunda stdoutLogEnabled='true' yap",
            "Uygulama kök dizininde 'logs' klasörü oluştur, altında 'stdout' klasörü oluştur",
            "logs klasörüne IIS_IUSRS için Full Control izni ver",
            "Siteyi yeniden başlat, logs/stdout içindeki log dosyasını oku",
            "Hata koduna göre müşteriye döndür: runtime eksikse yükle, config hatasıysa müşteriyi bilgilendir",
        ],
        "customer_action": False,
        "draft": "ASP.NET Core uygulamanızın başlatılmasında sorun tespit edildi. Detaylı hata günlüğü inceleniyor.",
    },

    "500.19": {
        "platform": "Windows/IIS",
        "title": "500.19 — web.config Okuma Hatası",
        "causes": [
            "web.config dosyasında sözdizimi hatası",
            "IIS'in desteklemediği bir modül veya handler tanımlı",
            "web.config dosyasına okuma izni yok",
        ],
        "tech_steps": [
            "web.config dosyasını XML editörde aç, sözdizimi hatası var mı kontrol et",
            "Hata mesajındaki satır numarasına git",
            "IIS Manager → Modules: ilgili modül yüklü mü kontrol et",
            "Dosya izinlerini kontrol et: IIS_IUSRS Read izni var mı",
        ],
        "customer_action": True,
        "draft": "web.config dosyanızda yapılandırma hatası tespit edildi. Lütfen dosyayı kontrol ediniz veya teknik ekibinizle iletişime geçiniz.",
    },

    # ─── LINUX / Apache / Nginx ──────────────────────────────────────────────

    "404_linux": {
        "platform": "Linux",
        "title": "404 Not Found — Sayfa Bulunamadı",
        "causes": [
            ".htaccess dosyası eksik veya hatalı (WordPress, Laravel vb.)",
            "mod_rewrite aktif değil (Apache)",
            "Dosya gerçekten yok — yanlış dizine yüklenmiş olabilir",
            "Nginx'te try_files direktifi eksik",
            "DocumentRoot yanlış dizini gösteriyor",
        ],
        "tech_steps": [
            "Dosyanın fiziksel olarak var olup olmadığını kontrol et: ls -la /var/www/html/",
            "Apache: a2enmod rewrite → AllowOverride All ayarını kontrol et",
            ".htaccess dosyası var mı, içeriği doğru mu kontrol et",
            "Nginx: /etc/nginx/sites-available/ → try_files $uri $uri/ /index.php?$args; satırı var mı",
            "Apache error log: tail -50 /var/log/apache2/error.log",
        ],
        "customer_action": True,
        "draft": "Erişmeye çalıştığınız sayfa sunucumuzda bulunamadı. Dosyaların doğru dizine yüklendiğini ve .htaccess dosyanızın eksiksiz olduğunu kontrol ediniz.",
    },

    "403_linux": {
        "platform": "Linux",
        "title": "403 Forbidden — Erişim Engellendi",
        "causes": [
            "Klasör veya dosya izinleri çok kısıtlayıcı (chmod 700 gibi)",
            "index dosyası yok, dizin listeleme kapalı",
            ".htaccess içinde Deny from all veya Options -Indexes var",
            "SELinux veya AppArmor politikası engelliyor",
            "Sahiplik (ownership) hatası: www-data değil farklı kullanıcıya ait",
        ],
        "tech_steps": [
            "Dosya izinlerini kontrol et: ls -la /var/www/html/",
            "Klasör izni 755, dosya izni 644 olmalı: chmod -R 755 /var/www/html/ && chmod -R 644 /var/www/html/*.php",
            "Sahipliği düzelt: chown -R www-data:www-data /var/www/html/",
            ".htaccess içinde 'Deny from all' veya 'Require all denied' var mı bak",
            "Apache error log: tail -50 /var/log/apache2/error.log",
        ],
        "customer_action": False,
        "draft": "Sunucunuzda dosya erişim izni sorunu tespit edildi. Teknik ekibimiz gerekli düzenlemeleri yapacaktır.",
    },

    "500_linux": {
        "platform": "Linux",
        "title": "500 Internal Server Error — Sunucu İç Hatası",
        "causes": [
            "PHP sözdizimi hatası (syntax error)",
            ".htaccess sözdizimi hatası",
            "PHP memory_limit veya max_execution_time aşıldı",
            "WordPress plugin/tema çakışması",
            "Veritabanı bağlantı hatası",
            "Dosya izinleri çok geniş (777 gibi) — güvenlik reddi",
        ],
        "tech_steps": [
            "Apache error log oku: tail -100 /var/log/apache2/error.log",
            "PHP error log oku: tail -100 /var/log/php_errors.log",
            ".htaccess'i geçici olarak yeniden adlandır: mv .htaccess .htaccess.bak — hata geçtiyse .htaccess sorunu",
            "WordPress ise: wp-config.php içinde define('WP_DEBUG', true) yap",
            "PHP syntax kontrol: php -l /var/www/html/index.php",
            "Bellek limitini artır: php.ini → memory_limit = 256M",
        ],
        "customer_action": True,
        "draft": "Uygulamanızda bir hata tespit edildi. Hata günlüğü inceleniyor. Sonuç hakkında sizi bilgilendireceğiz.",
    },

    "503_linux": {
        "platform": "Linux",
        "title": "503 Service Unavailable — Servis Kullanılamıyor",
        "causes": [
            "Apache veya Nginx servisi durmuş",
            "PHP-FPM servisi durmuş veya yanıt vermiyor",
            "Sunucu kaynak limiti aşılmış (RAM/CPU)",
            "Upstream backend (Node.js, Python vb.) çalışmıyor",
            "Rate limiting veya DDoS koruması devreye girmiş",
        ],
        "tech_steps": [
            "Servis durumunu kontrol et: systemctl status apache2 / systemctl status nginx",
            "Durdurulmuşsa başlat: systemctl start apache2 / systemctl start nginx",
            "PHP-FPM kontrol et: systemctl status php8.x-fpm",
            "Sunucu kaynakları: top veya htop ile RAM/CPU kontrol et",
            "Nginx upstream hatası varsa: /var/log/nginx/error.log oku",
        ],
        "customer_action": False,
        "draft": "Sunucunuzda servis kesintisi tespit edildi. Teknik ekibimiz müdahale ediyor.",
    },

    # ─── DNS ─────────────────────────────────────────────────────────────────

    "dns_ns": {
        "platform": "DNS",
        "title": "NS Kaydı Çalışmıyor — Alan Adı Çözümlenemiyor",
        "causes": [
            "Alan adı registrar'da NS adresleri yanlış tanımlanmış",
            "DNS sunucusu çalışmıyor veya yanıt vermiyor",
            "Alan adı süresi dolmuş, NS yanıt vermiyor",
            "NS değişikliği henüz yayılmamış (propagation sürüyor)",
        ],
        "tech_steps": [
            "whois sorgusu yap — alan adı aktif mi, NS adresleri ne?",
            "Registrar paneline gir — NS adresleri doğru mu kontrol et",
            "DNS propagation kontrol et: whatsmydns.net üzerinden global yayılım durumuna bak",
            "NS sunucusuna direkt sorgu at: nslookup -type=NS domain.com 8.8.8.8",
            "Alan adı süresi dolduysa yenileme için müşteriyi yönlendir",
        ],
        "customer_action": True,
        "draft": "Alan adınızın DNS sunucuları yanıt vermiyor. Registrar panelinizden NS adreslerini kontrol etmenizi öneririz.",
    },

    "dns_a": {
        "platform": "DNS",
        "title": "A Kaydı Aktif Değil veya Yanlış",
        "causes": [
            "A kaydı hiç tanımlanmamış",
            "A kaydı yanlış IP adresine yönlendiriyor",
            "DNS değişikliği henüz yayılmamış",
            "TTL süresi dolmamış, eski kayıt hâlâ geçerli",
        ],
        "tech_steps": [
            "Mevcut A kaydını sorgula: nslookup domain.com 8.8.8.8",
            "Sunucu IP'siyle karşılaştır — eşleşiyor mu?",
            "DNS yönetim panelinde A kaydını kontrol et",
            "Yanlışsa düzelt, TTL'i 300 saniyeye indir (hızlı yayılım için)",
            "Propagation: whatsmydns.net üzerinden takip et",
        ],
        "customer_action": True,
        "draft": "Alan adınızın A kaydı sunucumuza doğru yönlendirilmemiş. DNS yönetim panelinizden A kaydını güncelleyiniz.",
    },

    "dns_expired": {
        "platform": "DNS",
        "title": "Alan Adı Süresi Dolmuş",
        "causes": [
            "Alan adı yenilenmemiş",
            "Otomatik yenileme başarısız olmuş (ödeme yöntemi sorunu)",
            "Alan adı redemption period'da (kurtarılabilir süre)",
        ],
        "tech_steps": [
            "whois ile son geçerlilik tarihini doğrula",
            "Alan adı registrar'ı belirle",
            "Müşteriyi bilgilendir: yenileme için registrar paneline yönlendir",
            "Redemption period'daysa (genellikle 30 gün): ek ücretle kurtarılabilir",
            "Süresi çok geçtiyse alan adı başkası tarafından alınabilir — acil uyar",
        ],
        "customer_action": True,
        "draft": "Alan adınızın süresi dolmuş. Hizmet kesintisini gidermek için alan adınızı bir an önce yenilemeniz gerekmektedir.",
    },

    # ─── MAIL ────────────────────────────────────────────────────────────────

    "mail_mx": {
        "platform": "Mail",
        "title": "MX Kaydı Eksik veya Yanlış",
        "causes": [
            "MX kaydı DNS'te tanımlanmamış",
            "MX kaydı yanlış mail sunucusuna yönlendiriyor",
            "Alan adı değişikliğinde MX taşınmamış",
        ],
        "tech_steps": [
            "MX kaydını sorgula: nslookup -type=MX domain.com 8.8.8.8",
            "Doğru mail sunucusu adresini öğren (hosting panelinden)",
            "DNS panelinde MX kaydını ekle/düzelt",
            "Priority değeri: genellikle 10",
            "Propagation sonrası test et: mail gönder/al",
        ],
        "customer_action": False,
        "draft": "E-posta hizmetinize ait DNS kaydında sorun tespit edildi. Gerekli düzenlemeler yapılıyor.",
    },

    "mail_send_receive": {
        "platform": "Mail",
        "title": "Mail Gönderme / Alma Sorunu",
        "causes": [
            "Mail sunucusu çalışmıyor (Postfix/Exim/hMailServer)",
            "Port engeli: 25, 465, 587 portları ISP tarafından kapalı",
            "SPF/DKIM/DMARC kaydı eksik — spam olarak işaretleniyor",
            "Mail kutusu dolmuş (disk kotası)",
            "SSL/TLS sertifika sorunu",
        ],
        "tech_steps": [
            "Mail sunucusu portlarını test et: telnet mail.domain.com 587",
            "Mail log oku: tail -100 /var/log/mail.log (Linux) veya Event Viewer (Windows)",
            "SPF kaydını kontrol et: nslookup -type=TXT domain.com",
            "Mail kutusunun dolup dolmadığını kontrol et",
            "Test maili gönder/al, bounce mesajını oku",
            "MXToolbox üzerinden kapsamlı mail sağlığı kontrolü yap",
        ],
        "customer_action": False,
        "draft": "E-posta hizmetinizde sorun tespit edildi. Teknik ekibimiz inceleme yapıyor.",
    },

    "blacklist": {
        "platform": "Mail",
        "title": "IP Adresi Kara Listede (RBL)",
        "causes": [
            "Sunucudan spam gönderilmiş (ele geçirilmiş hesap veya zararlı script)",
            "Aynı IP'yi paylaşan başka bir müşteri spam göndermiş (paylaşımlı hosting)",
            "PHP mail() ile korumasız iletişim formu kötüye kullanılmış",
            "IP dinamik/ev tipi aralıkta olduğu için politika gereği listelenmiş (PBL)",
            "Yanlış yapılandırılmış sunucu açık relay olarak kullanılmış",
        ],
        "tech_steps": [
            "Hangi listelerde olduğunu ve dönen kodu not et — kod, listelenme NEDENİNİ söyler",
            "Mail kuyruğunu incele: spam kalıntısı var mı? (postqueue -p / exim -bp)",
            "Mail loglarında olağan dışı gönderim hacmi ara: kim, ne zaman, nereye?",
            "Ele geçirilmiş hesap/script varsa önce onu temizle — temizlemeden delist isteme",
            "Her listenin kendi delist (kaldırma) formundan talep aç; Spamhaus/PBL için ISP tipine dikkat",
            "24-48 saat sonra tekrar kontrol et; tekrarlıyorsa kaynağı bulunamamış demektir",
        ],
        "customer_action": False,
        "draft": "Sunucu IP adresinizin bazı spam kara listelerinde yer aldığını tespit ettik. Kaynağı tespit edip temizliyor, ardından listelerden kaldırma sürecini başlatıyoruz. E-posta gönderimlerinizde geçici gecikmeler yaşanabilir.",
    },

    # ─── WORDPRESS ───────────────────────────────────────────────────────────

    "wp_db": {
        "platform": "WordPress",
        "title": "WordPress Veritabanı Bağlantı Hatası",
        "causes": [
            "wp-config.php içinde DB_HOST, DB_NAME, DB_USER veya DB_PASSWORD yanlış",
            "MySQL/MariaDB servisi durmuş",
            "Veritabanı kullanıcısının izinleri yetersiz",
            "Hosting paket değişikliğinde veritabanı bilgileri değişmiş",
            "Veritabanı sunucusu farklı host'ta ve bağlantıya izin verilmemiş",
        ],
        "tech_steps": [
            "wp-config.php dosyasını oku: DB_HOST, DB_NAME, DB_USER, DB_PASSWORD değerlerini kontrol et",
            "MySQL çalışıyor mu: systemctl status mysql",
            "Bağlantıyı test et: mysql -u DB_USER -p -h DB_HOST DB_NAME",
            "Kullanıcı izinleri: SHOW GRANTS FOR 'db_user'@'localhost';",
            "Hosting panelinden DB kullanıcı şifresini sıfırla, wp-config.php'yi güncelle",
        ],
        "customer_action": True,
        "draft": "WordPress siteniz veritabanına bağlanamıyor. wp-config.php dosyanızdaki veritabanı bilgilerini kontrol etmenizi öneririz. Yardıma ihtiyaç duyarsanız bizimle iletişime geçebilirsiniz.",
    },

    "wp_plugin": {
        "platform": "WordPress",
        "title": "WordPress Plugin / Tema Çakışması",
        "causes": [
            "Son yüklenen/güncellenen plugin PHP hatası veriyor",
            "Tema uyumsuzluğu",
            "PHP sürümü plugin ile uyumsuz",
        ],
        "tech_steps": [
            "Tüm pluginleri devre dışı bırak: /wp-content/plugins klasörünü yeniden adlandır",
            "Hata geçtiyse pluginleri tek tek aktif ederek sorumluyu bul",
            "Temayı varsayılana çevir: /wp-content/themes/aktif-tema klasörünü yeniden adlandır",
            "PHP sürümünü kontrol et, plugin gereksinimiyle karşılaştır",
            "WP_DEBUG aktif et: wp-config.php → define('WP_DEBUG', true)",
        ],
        "customer_action": True,
        "draft": "WordPress sitenizde plugin veya tema kaynaklı bir sorun tespit edildi. Son yüklediğiniz veya güncellediğiniz eklentiyi geçici olarak devre dışı bırakmanızı öneririz.",
    },
}


def analyze_error(http_status: int | None, platform: str = "auto", domain: str = "") -> dict | None:
    """HTTP status koduna ve platforma göre hata analizi döndür"""

    if http_status == 403:
        return ERROR_DB.get("403")
    elif http_status == 503:
        return ERROR_DB.get("503")
    elif http_status == 500:
        return ERROR_DB.get("500_linux")
    elif http_status == 404:
        return ERROR_DB.get("404_linux")
    return None


def get_error_by_key(key: str) -> dict | None:
    return ERROR_DB.get(key)


def get_all_categories() -> list[str]:
    return list(ERROR_DB.keys())
