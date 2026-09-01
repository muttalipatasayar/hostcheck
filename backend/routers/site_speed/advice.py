"""Performans bulguları için Türkçe teknisyen önerileri.

`error_analysis.ERROR_DB`'nin performans karşılığıdır ve aynı şemayı kullanır:
teknisyen zaten Hızlı Kontrol ekranında bu üçlüyü okumaya alışkın.

    causes          — olası nedenler (teşhis için düşünme listesi)
    tech_steps      — teknisyenin sırayla yapacağı somut adımlar
    customer_action — çözüm müşterinin elindeyse True (site kodu/tema),
                      hosting tarafındaysa False. Arayüz başlığı buna göre
                      "Müşteri Yapacak" / "Müşteriye Yanıt Taslağı" değişir.
    draft           — müşteriye kopyalanabilir Türkçe metin

Anahtarlar `audits.py`'deki denetim `id`'leriyle birebir eşleşir.
"""

ADVICE_DB: dict[str, dict] = {

    "sunucu-yaniti": {
        "causes": [
            "Paylaşımlı sunucuda CPU/IO limiti doluyor (komşu hesap yükü ya da kendi trafiği)",
            "PHP-FPM havuzundaki tüm worker'lar meşgul, istekler kuyrukta bekliyor",
            "Veritabanı sorguları indekssiz çalışıyor veya yavaş sorgu birikmiş",
            "Sayfa önbelleği (LiteSpeed Cache, WP Rocket, Redis) kapalı ya da çalışmıyor",
            "Uygulama her istekte dış bir API'ye senkron çağrı yapıyor",
            "Disk yavaş ya da dolu; geçici dosya yazımı bekliyor",
        ],
        "tech_steps": [
            "TTFB dökümündeki 'Sunucu işleme' fazına bak — DNS/TCP/TLS küçükse yük kesinlikle sunucuda",
            "cPanel/Plesk → Resource Usage: son 24 saatte CPU, EP veya IO limiti aşılmış mı",
            "PHP-FPM durumunu kontrol et: aktif/boşta worker sayısı, listen queue dolu mu",
            "MySQL slow query log'unu aç ve 1 sn üstü sorguları çıkar",
            "Sitede önbellek eklentisi varsa gerçekten çalışıyor mu doğrula (yanıt başlığında x-cache / x-litespeed-cache)",
            "Aynı sunucudaki başka bir hesabın yük ürettiğini düşünüyorsan `top` / LVE istatistiklerine bak",
        ],
        "customer_action": False,
        "draft": (
            "Sitenizde sunucu yanıt süresinin yüksek olduğu tespit edildi. Teknik "
            "ekibimiz sunucu kaynaklarını ve uygulama tarafındaki sorgu sürelerini "
            "inceleyerek gerekli iyileştirmeleri yapacaktır. İşlem tamamlandığında "
            "tarafınıza bilgi verilecektir."
        ),
    },

    "sikistirma": {
        "causes": [
            "Web sunucusunda gzip/brotli modülü kurulu değil veya devre dışı",
            "Sıkıştırma yalnızca bazı MIME türleri için tanımlanmış, CSS/JS listede yok",
            "Önündeki bir proxy/CDN sıkıştırmayı kaldırıyor",
            "Dosyalar zaten sıkıştırılmış sanılıp `Content-Encoding` başlığı gönderilmiyor",
        ],
        "tech_steps": [
            "Apache: `mod_deflate` yüklü mü kontrol et, .htaccess'e AddOutputFilterByType DEFLATE satırlarını ekle",
            "Nginx: `gzip on; gzip_types text/css application/javascript application/json image/svg+xml; gzip_min_length 256;`",
            "LiteSpeed: WebAdmin → Tuning → Enable Compression + Compressible Types listesini genişlet",
            "Brotli varsa tercih et (Nginx `brotli on;`) — gzip'ten %15-20 daha iyi sıkıştırır",
            "Değişiklik sonrası doğrula: curl -sI -H 'Accept-Encoding: gzip, br' https://alanadi/dosya.css | grep -i content-encoding",
        ],
        "customer_action": False,
        "draft": (
            "Sitenizin dosyaları sıkıştırılmadan gönderiliyordu. Sunucu tarafında "
            "sıkıştırma etkinleştirilerek sayfa boyutu belirgin şekilde düşürülecek "
            "ve yükleme süresi kısalacaktır."
        ),
    },

    "cache-politikasi": {
        "causes": [
            "Statik dosyalar için `Cache-Control` / `Expires` başlığı hiç tanımlanmamış",
            "max-age çok kısa verilmiş (saatler yerine yıl olmalı)",
            "Dosya adlarında sürüm/hash yok, bu yüzden uzun önbellek riskli görülmüş",
            "Önbellek eklentisi başlıkları yazıyor ama sunucu üstüne yazıyor",
        ],
        "tech_steps": [
            "Apache: `mod_expires` ile ExpiresByType image/webp \"access plus 1 year\" benzeri kurallar ekle",
            "Nginx: `location ~* \\.(css|js|woff2|webp|avif|png|jpg)$ { expires 1y; add_header Cache-Control \"public, immutable\"; }`",
            "Dosya adlarında hash yoksa önce sürümleme kur (style.css?v=... yeterli değil, dosya adına gömülmeli)",
            "HTML belgesine uzun önbellek VERME — yalnızca statik varlıklara",
            "Doğrula: curl -sI https://alanadi/static/style.css | grep -i cache-control",
        ],
        "customer_action": False,
        "draft": (
            "Sitenizin görsel ve stil dosyaları ziyaretçinin tarayıcısında yeterince "
            "saklanmıyordu. Önbellek süreleri düzenlendi; tekrar eden ziyaretlerde "
            "sayfa gözle görülür şekilde daha hızlı açılacaktır."
        ),
    },

    "render-engelleme": {
        "causes": [
            "Tema veya eklentiler tüm CSS/JS dosyalarını <head> içine senkron ekliyor",
            "jQuery ve benzeri kütüphaneler sayfa başında yükleniyor",
            "Kritik olmayan stil dosyaları da ilk boyamayı bekletiyor",
            "Font dosyaları font-display tanımı olmadan yükleniyor",
        ],
        "tech_steps": [
            "Script etiketlerine `defer` (veya bağımsızsa `async`) ekle — sıralama önemliyse defer kullan",
            "Kritik CSS'i satır içi göm, kalanını `media=\"print\" onload=\"this.media='all'\"` ile ertele",
            "WordPress ise: WP Rocket / LiteSpeed Cache → 'JS'i ertele' ve 'Kritik CSS oluştur' seçeneklerini aç",
            "Kullanılmayan eklenti CSS/JS'ini ilgili sayfalarda kuyruğa alma (wp_dequeue_style / wp_dequeue_script)",
            "Fontlara `font-display: swap` ekle, tercihen self-host et",
        ],
        "customer_action": True,
        "draft": (
            "Sitenizin ilk görüntülenmesini geciktiren stil ve script dosyaları tespit "
            "edildi. Tema veya eklenti ayarlarından bu dosyaların ertelenmiş şekilde "
            "yüklenmesi sağlanırsa sayfanız belirgin şekilde daha hızlı açılacaktır. "
            "Bir önbellek/optimizasyon eklentisi kullanıyorsanız 'JavaScript'i ertele' "
            "ve 'Kritik CSS' seçenekleri bu iş için yeterlidir."
        ),
    },

    "gorsel-format": {
        "causes": [
            "Görseller JPEG/PNG olarak yüklenmiş, WebP/AVIF'e çevrilmemiş",
            "Tema veya galeri eklentisi modern format üretmiyor",
            "CDN üzerinde otomatik format dönüşümü kapalı",
        ],
        "tech_steps": [
            "WordPress: Imagify / ShortPixel / EWWW ile toplu WebP dönüşümü çalıştır",
            "Sunucuda toplu dönüşüm: `cwebp -q 80 girdi.jpg -o cikti.webp`",
            "Cloudflare kullanılıyorsa Polish + WebP dönüşümünü aç",
            "<picture> etiketiyle WebP'yi önce, JPEG'i yedek olarak sun",
            "Dönüşüm sonrası eski dosyaları hemen silme — yedek olarak bir süre tut",
        ],
        "customer_action": True,
        "draft": (
            "Sitenizdeki görseller güncel sıkıştırma formatlarında değil. Görsellerin "
            "WebP formatına dönüştürülmesi, görüntü kalitesinden ödün vermeden sayfa "
            "boyutunu belirgin şekilde küçültür. Sitenizde bir görsel optimizasyon "
            "eklentisi kurarak bu dönüşümü toplu şekilde yapabilirsiniz; dilerseniz "
            "kurulum konusunda destek sağlayabiliriz."
        ),
    },

    "gorsel-boyut": {
        "causes": [
            "Orijinal fotoğraf makinesi/telefon çıktısı doğrudan yüklenmiş",
            "Tema küçük alanlarda büyük görsel boyutunu çağırıyor",
            "srcset / sizes tanımlanmamış, tüm cihazlara aynı dosya gidiyor",
        ],
        "tech_steps": [
            "Görselleri gösterildikleri en büyük ölçünün 2 katına indir (retina payı)",
            "WordPress: Ayarlar → Medya'da boyutları düzelt, ardından Regenerate Thumbnails çalıştır",
            "Tema kodunda `wp_get_attachment_image` ile doğru boyut adını çağır (full yerine medium_large)",
            "srcset ekle: farklı genişlikler tanımlanıp tarayıcının seçmesine izin ver",
        ],
        "customer_action": True,
        "draft": (
            "Sitenizdeki bazı görseller ekranda kapladıkları alandan çok daha büyük "
            "çözünürlükte yükleniyor. Görsellerin kullanıldıkları ölçüye uygun şekilde "
            "yeniden boyutlandırılması, özellikle mobil ziyaretçiler için yükleme "
            "süresini kısaltacaktır."
        ),
    },

    "gorsel-lazy": {
        "causes": [
            "Ekran dışındaki görsellerde loading=\"lazy\" özniteliği yok",
            "Tema kendi lazy-load mekanizmasını kullanıyor ama JS ile geç devreye giriyor",
            "Slider/galeri eklentisi tüm kareleri baştan yüklüyor",
        ],
        "tech_steps": [
            "Ekran dışı <img> etiketlerine loading=\"lazy\" ekle",
            "İlk ekrandaki (LCP) görsele lazy EKLEME — aksi hâlde LCP kötüleşir",
            "WordPress 5.5+ bunu varsayılan yapar; tema geçersiz kılıyorsa filtreyi kontrol et",
            "Slider eklentilerinde 'yalnızca görünen slaytı yükle' seçeneğini aç",
        ],
        "customer_action": True,
        "draft": (
            "Sayfanızın alt kısımlarında yer alan görseller, ziyaretçi oraya gelmeden "
            "yükleniyor. Bu görsellerin gecikmeli yüklenecek şekilde ayarlanması ilk "
            "açılış süresini kısaltır. Kullandığınız tema veya optimizasyon eklentisinde "
            "'lazy load' seçeneğinin açık olması yeterlidir."
        ),
    },

    "ucuncu-taraf": {
        "causes": [
            "Analitik, reklam, canlı destek ve sosyal medya script'leri birikmiş",
            "Aynı işi yapan birden fazla izleme kodu kurulu",
            "Chat/pop-up widget'ı sayfa başında senkron yükleniyor",
            "Fontlar dış kaynaktan (Google Fonts vb.) çekiliyor",
        ],
        "tech_steps": [
            "Üçüncü taraf tablosunda en ağır alanı bul ve gerçekten gerekli mi sorgula",
            "İzleme kodlarını Google Tag Manager altında toplayıp tek noktadan yönet",
            "Chat widget'ını kullanıcı etkileşimine kadar geciktir (ilk scroll/click'te yükle)",
            "Google Fonts yerine fontları self-host et — bir DNS + TLS turu kazandırır",
            "Kalanlara `rel=preconnect` ekleyerek bağlantı kurulumunu öne al",
        ],
        "customer_action": True,
        "draft": (
            "Sitenizde dış kaynaklardan yüklenen script'lerin (analitik, reklam, canlı "
            "destek vb.) sayfa ağırlığında önemli yer tuttuğu görülüyor. Bu servislerin "
            "yükleme süreleri bizim sunucumuzun kontrolünde değildir. Kullanılmayan "
            "servislerin kaldırılması veya gecikmeli yüklenmesi hız açısından fayda sağlar."
        ),
    },

    "toplam-agirlik": {
        "causes": [
            "Optimize edilmemiş görseller sayfa ağırlığının çoğunu oluşturuyor",
            "Kullanılmayan eklenti CSS/JS dosyaları her sayfada yükleniyor",
            "Video veya animasyon dosyaları doğrudan gömülmüş",
            "Web font aileleri gereğinden fazla ağırlıkta yükleniyor",
        ],
        "tech_steps": [
            "Kaynak dağılımı tablosunda en ağır türü belirle, önce ona odaklan",
            "Görsel ağırsa: WebP dönüşümü + doğru ölçekleme (yukarıdaki iki denetim)",
            "JS ağırsa: kullanılmayan eklentileri kaldır, kalanları sayfa bazında kuyruğa al",
            "Video gömülüyse yerine kapak görseli + tıklamada yükleme koy",
            "Fontlarda yalnızca kullanılan ağırlıkları (400/700) ve latin-ext alt kümesini yükle",
        ],
        "customer_action": True,
        "draft": (
            "Sayfanızın toplam boyutu, özellikle mobil bağlantılarda yükleme süresini "
            "uzatacak düzeyde. Görsellerin optimize edilmesi ve kullanılmayan eklentilerin "
            "kaldırılması en hızlı sonucu verecektir. Detaylı raporu paylaşabiliriz."
        ),
    },

    "http-protokol": {
        "causes": [
            "Sunucuda HTTP/2 modülü etkin değil",
            "TLS sonlandırması yapan proxy yalnızca HTTP/1.1 konuşuyor",
            "Eski bir sunucu sürümü kullanılıyor",
        ],
        "tech_steps": [
            "Nginx: `listen 443 ssl; http2 on;` (1.25.1+) veya eski sürümde `listen 443 ssl http2;`",
            "Apache: `mod_http2` yükle, `Protocols h2 http/1.1` ekle, MPM event kullan",
            "LiteSpeed'de HTTP/2 varsayılan açıktır — kapatılmış mı kontrol et",
            "CDN önde ise CDN → origin bacağında da HTTP/2'yi aç",
            "Doğrula: curl -sI --http2 https://alanadi | head -1",
        ],
        "customer_action": False,
        "draft": (
            "Sunucunuz henüz HTTP/2 protokolünü kullanmıyordu. Bu protokol tek bağlantı "
            "üzerinden paralel dosya indirmeyi sağlar. Sunucu tarafında gerekli "
            "yapılandırma yapılarak sayfa yükleme süresi iyileştirilecektir."
        ),
    },

    "tls-surumu": {
        "causes": [
            "Sunucu yapılandırmasında eski TLS sürümleri hâlâ açık",
            "Uyumluluk kaygısıyla TLS 1.0/1.1 bilerek bırakılmış",
            "OpenSSL sürümü TLS 1.3'ü desteklemiyor",
        ],
        "tech_steps": [
            "Nginx: `ssl_protocols TLSv1.2 TLSv1.3;`",
            "Apache: `SSLProtocol -all +TLSv1.2 +TLSv1.3`",
            "TLS 1.3 çıkmıyorsa OpenSSL 1.1.1+ kurulu mu kontrol et",
            "Değişiklikten sonra SSL Araçları sekmesinden yeniden doğrula",
        ],
        "customer_action": False,
        "draft": (
            "Sunucunuzda kullanımdan kaldırılmış güvenlik protokolleri tespit edildi. "
            "Güncel TLS sürümlerine geçiş yapılarak hem güvenlik hem bağlantı kurulum "
            "hızı iyileştirilecektir."
        ),
    },

    "sunucu-teknolojisi": {
        "causes": [
            "Hesap eski bir PHP sürümünde bırakılmış",
            "Site kodu yeni PHP sürümünde uyarı ürettiği için yükseltilmemiş",
            "Sunucu yazılımı sürümünü başlıkta açıkça yayınlıyor",
        ],
        "tech_steps": [
            "cPanel → MultiPHP Manager / Plesk → PHP Settings ile sürümü kontrol et",
            "Yükseltmeden önce staging kopyada dene — eski eklentiler kırılabilir",
            "Yükseltme sonrası error_log'u izle, deprecated uyarılarını topla",
            "Sürüm bilgisini gizle: PHP `expose_php = Off`, Nginx `server_tokens off;`, Apache `ServerTokens Prod`",
            "PHP 8.x'e geçiş tek başına %20-30 civarında CPU kazancı sağlar",
        ],
        "customer_action": False,
        "draft": (
            "Sitenizin çalıştığı PHP sürümünün güncellenmesi gerekmektedir. Güncel "
            "sürümler hem güvenlik yamalarını alır hem belirgin şekilde daha hızlı "
            "çalışır. Yükseltme öncesi sitenizin uyumluluğu test edilecek, işlem "
            "planlanan bir zaman diliminde gerçekleştirilecektir."
        ),
    },

    "cdn": {
        "causes": [
            "Site tek bir sunucudan servis ediliyor",
            "Ziyaretçiler coğrafi olarak dağınık ama içerik tek noktadan gidiyor",
        ],
        "tech_steps": [
            "Ziyaretçi coğrafyasını kontrol et — tek şehirdeyse CDN'in katkısı sınırlı olur",
            "Cloudflare ücretsiz planı çoğu paylaşımlı hosting için yeterlidir",
            "DNS'i CDN'e taşırken mevcut kayıtları eksiksiz aktar (MX dahil!)",
            "CDN sonrası SSL modunu 'Full (strict)' seç — 'Flexible' döngü üretir",
        ],
        "customer_action": False,
        "draft": (
            "Siteniz şu anda içerik dağıtım ağı (CDN) kullanmıyor. Ziyaretçileriniz "
            "farklı şehir veya ülkelerden geliyorsa CDN kullanımı yükleme süresini "
            "belirgin şekilde kısaltır. Bu konuda destek sağlayabiliriz."
        ),
    },

    "dom-boyutu": {
        "causes": [
            "Sayfa builder (Elementor, WPBakery) çok katmanlı sarmalayıcı üretiyor",
            "Tek sayfada çok fazla ürün/yazı listeleniyor",
            "Gizli menü ve pop-up içerikleri DOM'da baştan duruyor",
        ],
        "tech_steps": [
            "Listeleme sayfalarında sayfalama (pagination) veya sonsuz kaydırma kullan",
            "Sayfa builder'da gereksiz section/column iç içeliğini azalt",
            "Gizli içerikleri ihtiyaç anında JS ile oluştur, HTML'de bekletme",
            "Mega menüleri ilk etkileşimde yükle",
        ],
        "customer_action": True,
        "draft": (
            "Sayfanızın HTML yapısı oldukça büyük. Bu durum tarayıcının sayfayı "
            "işlemesini yavaşlatır ve özellikle mobil cihazlarda tıklama gecikmesine "
            "yol açar. Sayfa içeriğinin bölünmesi veya sayfalama kullanılması önerilir."
        ),
    },

    "basarisiz-istekler": {
        "causes": [
            "Silinmiş veya taşınmış dosyalara referans kalmış",
            "Eklenti kaldırılmış ama tema hâlâ dosyalarını çağırıyor",
            "Dış servis kapanmış / adresi değişmiş",
            "Dosya izinleri hatalı, sunucu okuyamıyor",
        ],
        "tech_steps": [
            "Listedeki her URL'yi tarayıcıda aç, gerçekten yok mu doğrula",
            "Kendi alan adındakiler için dosya sisteminde ara: find /home/kullanici/public_html -name 'dosya*'",
            "Dosya izinlerini kontrol et (644 dosya / 755 dizin)",
            "Dış servisse referansı kaldır ya da yerel kopyaya çevir",
            "Sunucu error_log'unda ilgili 404 kayıtlarını doğrula",
        ],
        "customer_action": False,
        "draft": (
            "Sitenizde yüklenemeyen bazı dosyalar tespit edildi. Bu eksik dosyalar hem "
            "görünümü etkileyebilir hem sayfanın tamamlanmasını geciktirir. Teknik "
            "ekibimiz eksik kaynakları inceleyip düzeltecektir."
        ),
    },

    "konsol-hatalari": {
        "causes": [
            "Eklenti çakışması veya eksik bağımlılık",
            "Kaldırılmış bir kütüphane hâlâ çağrılıyor",
            "Dış script yüklenemediği için ona bağlı kod hata veriyor",
            "Tema güncellemesi sonrası eski kod kalmış",
        ],
        "tech_steps": [
            "Hata mesajındaki dosya ve satır numarasından kaynağı bul",
            "Eklentileri tek tek devre dışı bırakarak çakışmayı izole et",
            "Tema ve eklentileri güncelle, güncelleme öncesi yedek al",
            "Hata dış bir script'ten geliyorsa o servisin durumunu kontrol et",
        ],
        "customer_action": True,
        "draft": (
            "Sitenizde JavaScript hataları tespit edildi. Bu hatalar bazı işlevlerin "
            "çalışmamasına yol açıyor olabilir. Tema ve eklentilerinizin güncel "
            "olduğundan emin olun; sorun devam ederse ayrıntılı inceleme için "
            "bizimle iletişime geçebilirsiniz."
        ),
    },

    "yonlendirme": {
        "causes": [
            "http → https ve ardından alanadi → www zinciri iki ayrı adımda yapılıyor",
            "Eski URL yapısından yeni yapıya çift yönlendirme kalmış",
            "HSTS yerine 301 ile HTTPS'e taşınıyor",
        ],
        "tech_steps": [
            "Zinciri tek adıma indir: http://alanadi → https://www.alanadi (ara adım olmadan)",
            ".htaccess veya Nginx'te birden fazla RewriteRule/return varsa birleştir",
            "HSTS başlığı ekle — tarayıcı sonraki ziyaretlerde http'yi hiç denemez",
            "Sitedeki iç bağlantıları kanonik adrese göre güncelle",
        ],
        "customer_action": False,
        "draft": (
            "Sitenize yapılan istekler yönlendirme üzerinden karşılanıyor. Yönlendirme "
            "zincirinin kısaltılması her ziyarette küçük ama ölçülebilir bir hız kazancı "
            "sağlar. Sunucu tarafında gerekli düzenleme yapılacaktır."
        ),
    },
}


def oneri(audit_id: str) -> dict | None:
    """Denetim id'sine karşılık gelen öneriyi döndürür (yoksa None)."""
    return ADVICE_DB.get(audit_id)


def zenginlestir(denetimler: list[dict]) -> list[dict]:
    """Başarısız denetimlere Türkçe öneri bloğunu ekler.

    Sağlıklı denetimlere öneri eklenmez — teknisyenin ekranı zaten uzun,
    çözülmüş bir şey için "ne yapmalı" göstermek gürültüdür.
    """
    for d in denetimler:
        if d.get("durum") in ("warning", "error"):
            a = ADVICE_DB.get(d["id"])
            if a:
                d["oneri"] = {
                    "causes": a["causes"],
                    "tech_steps": a["tech_steps"],
                    "customer_action": a["customer_action"],
                    "draft": a["draft"],
                }
    return denetimler
