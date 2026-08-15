# HostCheck — Hosting Destek Paneli

Hosting destek uzmanları için geliştirilmiş, yerel çalışan kapsamlı bir **destek otomasyon paneli**. DNS sorgulama, SSL araçları, alan adı geçmişi, hızlı site kontrolü, SSH/RDP erişimi ve hazır yanıt kütüphanesini tek bir arayüzde birleştirir.

---

## ⚠️ Güvenlik Notu — Önce Bunu Okuyun

**Panelde kimlik doğrulama yoktur.** SSH ve RDP terminalleri, DNS/SSL araçları ve hazır yanıt veritabanı, API'ye ulaşabilen herkese açıktır.

Bu nedenle sunucu varsayılan olarak **yalnızca `127.0.0.1` üzerinde** dinler. `--host 0.0.0.0` yaparsanız aynı ağdaki herkes sizin makinenizi SSH/RDP atlama noktası olarak kullanabilir. Paneli başka bir makineden kullanmanız gerekiyorsa, doğrudan açmak yerine SSH tüneli veya VPN arkasına alın.

---

## Özellikler

### Hızlı Kontrol
- Alan adı için WHOIS (EPP durum kodları dahil), A / NS / MX kayıtları ve SSL sertifika bilgisi
- Playwright (Microsoft Edge / Chromium) ile anlık site önizlemesi
- HTTP durum kodu kontrolü + yaygın hatalar için otomatik analiz ve müşteri yanıtı taslağı

### DNS Toolbox
- **A, AAAA, CNAME, MX, NS, TXT, SOA, PTR** kayıt sorguları
- **SPF** — politika analizi (sıkı / yumuşak / açık)
- **DMARC** — p= / sp= / pct= etiket ayrıştırma
- **DKIM** — selector girerek veya 20 yaygın selector'ı otomatik deneyerek sorgulama; key boyutu ve sağlık durumu analizi
- **DNSSEC** — DS + DNSKEY + RRSIG kontrol
- CNAME sorgusunda kök domain girilince `www.` otomatik ekleme
- Tam DKIM adresi (`ntr._domainkey.example.com`) girilince otomatik ayrıştırma

### DNS History
- WHOIS üzerinden kayıt tarihi, bitiş tarihi ve registrar bilgisi
- `.tr` dahil tüm yaygın TLD desteği (trabis.gov.tr, verisign, pir.org vb.)
- Mevcut NS sunucuları (canlı DNS sorgusu)
- [SecurityTrails API](https://securitytrails.com/) ile tam NS değişim geçmişi (opsiyonel)

### SSL Araçları
- **SSL Checker** — canlı sertifika sorgusu; DV/OV/EV tespiti, wildcard, SAN listesi, kalan gün
- **CSR Çözümle** — PEM formatındaki CSR'ı ayrıştırır; CN, O, SAN, key bilgisi gösterir
- **PFX Dönüştür** — CRT + Private Key + CA Chain → `.pfx` dosyası indir
- **CSR Oluştur** — 2048/4096-bit RSA, SAN desteği, Türkçe karakter otomatik dönüştürme

### SSH / RDP Erişimi
- Tarayıcı içi SSH terminali (xterm.js + paramiko)
- Guacamole (`guacd`) üzerinden tarayıcı içi RDP oturumu
- Kimlik bilgileri POST gövdesinde iletilir, URL'de veya loglarda görünmez

### IP Sorgulama
- IP veya alan adı için ülke, şehir, ISP, ASN, proxy/hosting tespiti

### Hazır Yanıtlar
- Kategorili yanıt kütüphanesi, arama, sabitleme, kullanım sayacı
- SQLite'ta saklanır; ilk açılışta `backend/data/hazirYanitlar.json` ile doldurulur

---

## Teknoloji

| Katman     | Teknoloji |
|------------|-----------|
| Frontend   | React 18 + Vite + Tailwind CSS |
| Backend    | FastAPI + Uvicorn |
| Veritabanı | SQLite + SQLAlchemy + Alembic |
| DNS        | dnspython (8.8.8.8 / 1.1.1.1 / 9.9.9.9) |
| SSL/Crypto | cryptography |
| Terminal   | paramiko (SSH) + guacamole-common-js (RDP) |
| Ekran görüntüsü | Playwright (Microsoft Edge / Chromium) |

---

## Kurulum

### Gereksinimler
- Python 3.11+
- Node.js 18+
- Microsoft Edge veya Chromium (ekran görüntüsü için — Playwright kurulumu hallediyor)
- Docker (yalnızca RDP kullanacaksanız — `guacd` için)

### 1. Projeyi klonlayın
```bash
git clone https://github.com/muttalipatasayar/hostcheck.git
cd hostcheck
```

### 2. Backend kurulumu
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
python -m playwright install chromium
```

`.env` dosyası oluşturun (`backend/.env.example` şablonuna bakın):
```env
ENV=development
CORS_ORIGINS=http://localhost:5173
SECURITYTRAILS_API_KEY=          # DNS History için (opsiyonel)
```

### 3. Frontend kurulumu
```bash
cd frontend
npm install
```

### 4. RDP için guacd (opsiyonel)
```bash
docker run -d -p 4822:4822 guacamole/guacd
```

---

## Çalıştırma

Tek tıkla: **`start.bat`** (backend + frontend + tarayıcı)

Veya elle:

**Terminal 1 — Backend:**
```bash
cd backend
venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Tarayıcıda açın: **http://localhost:5173**

---

## Veritabanı

Şema Alembic ile yönetilir ve uygulama her açılışta migration'ları otomatik çalıştırır — ayrıca bir komut vermenize gerek yoktur. Mevcut `hostcheck.db` dosyaları sorunsuz yükseltilir.

Elle çalıştırmak isterseniz:
```bash
cd backend
venv\Scripts\activate
alembic upgrade head
```

Model değiştirdikten sonra yeni migration üretmek için:
```bash
alembic revision --autogenerate -m "aciklama"
```

---

## Yapı

```
hostcheck/
├── backend/
│   ├── main.py              # FastAPI uygulaması
│   ├── database.py          # SQLAlchemy bağlantısı
│   ├── models.py            # Veritabanı modelleri
│   ├── db_migrate.py        # Açılışta Alembic upgrade
│   ├── rate_limiter.py      # slowapi rate limiting
│   ├── error_analysis.py    # HTTP hata analizi veritabanı
│   ├── alembic.ini
│   ├── migrations/          # Alembic migration'ları
│   ├── data/
│   │   └── hazirYanitlar.json   # Hazır yanıt seed verisi
│   └── routers/
│       ├── quick_check.py   # Hızlı kontrol (WHOIS + DNS + SSL + HTTP)
│       ├── screenshot.py    # Playwright ekran görüntüsü
│       ├── ssl_tools.py     # CSR / PFX / SSL checker
│       ├── dns_toolbox.py   # DNS sorgu motoru
│       ├── dns_history.py   # WHOIS + NS geçmişi
│       ├── ssh.py           # SSH WebSocket köprüsü
│       ├── rdp.py           # Guacamole RDP köprüsü
│       ├── ip_lookup.py     # IP / ASN sorgulama
│       └── hazir_yanitlar.py
└── frontend/
    └── src/
        ├── App.jsx
        └── components/
            ├── Sidebar.jsx
            ├── QuickCheck.jsx
            ├── SSLTools.jsx
            ├── DNSToolbox.jsx
            ├── DNSHistory.jsx
            ├── SSHAccess.jsx
            ├── RDPAccess.jsx
            ├── IPLookup.jsx
            └── HazirYanitlar.jsx
```

---

## API Dokümantasyonu

Backend çalışırken (`ENV=development` iken): **http://127.0.0.1:8000/docs**

---

## Lisans

MIT
