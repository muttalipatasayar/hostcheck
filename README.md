# HostCheck — Hosting Destek Paneli

Hosting destek uzmanları için geliştirilmiş, yerel çalışan kapsamlı bir **destek otomasyon paneli**. DNS sorgulama, SSL araçları, alan adı geçmişi, hızlı site kontrolü ve talep yönetimini tek bir arayüzde birleştirir.

---

## Özellikler

### Hızlı Kontrol
- Alan adı için A, MX, NS kayıtları ve SSL sertifika bilgisi
- Playwright (Microsoft Edge) ile anlık site önizlemesi
- Ping / HTTP durum kodu kontrolü

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
- **CSR Çözümle** — PEM formatındaki CSR'ı ayrıştırır; CN, O, SAN, key bilgisi gösterir
- **PFX Dönüştür** — CRT + Private Key + CA Chain → `.pfx` dosyası indir
- **CSR Oluştur** — 2048/4096-bit RSA, SAN desteği, Türkçe karakter otomatik dönüştürme

### Talep Yönetimi
- Talep oluşturma, listeleme, detay görüntüleme
- Durum takibi (Açık / Kapalı) ve öncelik seviyesi
- AI destekli hata analizi (Anthropic Claude)

---

## Teknoloji

| Katman    | Teknoloji |
|-----------|-----------|
| Frontend  | React 18 + Vite + Tailwind CSS |
| Backend   | FastAPI + Uvicorn |
| Veritabanı | SQLite + SQLAlchemy |
| DNS       | dnspython (8.8.8.8 / 1.1.1.1) |
| SSL/Crypto | cryptography |
| Ekran görüntüsü | Playwright (Microsoft Edge / Chromium) |
| AI        | Anthropic Claude API |

---

## Kurulum

### Gereksinimler
- Python 3.11+
- Node.js 18+
- Microsoft Edge (ekran görüntüsü için — Windows'ta hazır gelir)

### 1. Projeyi klonlayın
```bash
git clone https://github.com/KULLANICI_ADI/hostcheck.git
cd hostcheck
```

### 2. Backend kurulumu
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
```

`.env` dosyası oluşturun (`backend/.env.example` şablonuna bakın):
```env
ANTHROPIC_API_KEY=sk-ant-...          # Claude AI için (opsiyonel)
SECURITYTRAILS_API_KEY=...            # DNS History için (opsiyonel)
```

### 3. Frontend kurulumu
```bash
cd frontend
npm install
```

---

## Çalıştırma

**Terminal 1 — Backend:**
```bash
cd backend
venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Tarayıcıda açın: **http://localhost:5173**

---

## Ekran Görüntüleri

> Dashboard, DNS Toolbox ve SSL Araçları ekran görüntüleri buraya eklenebilir.

---

## Yapı

```
hostcheck/
├── backend/
│   ├── main.py              # FastAPI uygulaması
│   ├── database.py          # SQLAlchemy bağlantısı
│   ├── models.py            # Veritabanı modelleri
│   ├── schemas.py           # Pydantic şemaları
│   ├── rate_limiter.py      # slowapi rate limiting
│   ├── error_analysis.py    # AI hata analizi
│   ├── requirements.txt
│   └── routers/
│       ├── tickets.py       # Talep CRUD
│       ├── quick_check.py   # Hızlı kontrol
│       ├── screenshot.py    # Playwright ekran görüntüsü
│       ├── ssl_tools.py     # CSR / PFX / SSL araçları
│       ├── dns_toolbox.py   # DNS sorgu motoru
│       ├── dns_history.py   # WHOIS + NS geçmişi
│       ├── checks.py
│       └── ai.py
└── frontend/
    └── src/
        ├── App.jsx
        ├── components/
        │   ├── Sidebar.jsx
        │   ├── Dashboard.jsx
        │   ├── QuickCheck.jsx
        │   ├── SSLTools.jsx
        │   ├── DNSToolbox.jsx
        │   ├── DNSHistory.jsx
        │   ├── TicketList.jsx
        │   ├── TicketDetail.jsx
        │   └── NewTicketForm.jsx
        └── api/
            └── client.js
```

---

## API Dokümantasyonu

Backend çalışırken: **http://localhost:8000/docs** (Swagger UI)

---

## Lisans

MIT
