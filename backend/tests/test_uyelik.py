"""Üyelik sistemi — alan adı kapısı, doğrulama, oturum, CSRF, kaba kuvvet.

Bu dosyanın odağı KAPILAR. "Doğru kullanıcı doğru şeyi yapabiliyor mu"nun
yanında asıl soru "yanlış kullanıcı yapamıyor mu": panel internete açık
olduğu için her kapı bir güvenlik sınırı.
"""
import pytest

from conftest import giris_yap, son_mail_metni, son_token, uye_olustur

UYE = "ayse.yilmaz@natro.com"
UYE_TB = "jan@team.blue"
ADMIN = "yonetici@natro.com"
PAROLA = "Guclu-Parola-2026"


# ── Alan adı kapısı ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("eposta", [
    "kisi@gmail.com",              # tamamen yabancı
    "kisi@natro.com.saldirgan.net",  # sonek eşleşmesi tuzağı
    "kisi@evil-natro.com",         # önek tuzağı
    "kisi@mail.natro.com",         # alt alan adı — bilerek dışarıda
    "kisi@team.blue.evil.com",
    "kisi@teamblue.com",
    "kisi@nаtro.com",              # Kiril 'а' (U+0430) ile homograf
])
def test_izinsiz_alan_adi_reddedilir(istemci, eposta):
    r = istemci.post("/api/uyelik/kayit",
                     json={"ad_soyad": "Deneme Kisi", "email": eposta, "parola": PAROLA})
    assert r.status_code in (400, 403), r.text
    # Kullanıcı NEDEN reddedildiğini görmeli — ürün gereksinimi.
    if r.status_code == 403:
        assert "natro.com" in r.json()["detail"]


@pytest.mark.parametrize("eposta", [
    "kisi@natro.com\nBcc: kurban@baska.com",   # SMTP başlık enjeksiyonu
    "kisi@natro.com\r\nSubject: sahte",
    "kisi\x00@natro.com",
    "kisi@@natro.com",
    "kisi@natro.com " * 40,                    # 254 karakter sınırı
])
def test_bozuk_eposta_reddedilir(istemci, eposta):
    r = istemci.post("/api/uyelik/kayit",
                     json={"ad_soyad": "Deneme Kisi", "email": eposta, "parola": PAROLA})
    assert r.status_code in (400, 422), r.text


def test_izinli_alan_adlari_kabul_edilir(istemci):
    for eposta in ("kabul1@natro.com", "kabul2@team.blue"):
        r = istemci.post("/api/uyelik/kayit",
                         json={"ad_soyad": "Kabul Test", "email": eposta, "parola": PAROLA})
        assert r.status_code == 202, r.text


def test_eposta_buyuk_kucuk_harf_ayni_hesap(istemci):
    uye_olustur(istemci, "Karisik.Harf@Natro.Com")
    r = istemci.post("/api/uyelik/giris",
                     json={"email": "KARISIK.HARF@NATRO.COM", "parola": PAROLA})
    assert r.status_code == 200, r.text


# ── Parola politikası ────────────────────────────────────────────────────────

@pytest.mark.parametrize("parola", [
    "kisa1",              # 10 karakterden kısa
    "parolaparola",       # rakam yok
    "123456789012",       # harf yok
    "politika01xyz",      # e-postanın yerel adını içeriyor
])
def test_zayif_parola_reddedilir(istemci, parola):
    r = istemci.post("/api/uyelik/kayit",
                     json={"ad_soyad": "Parola Test", "email": "politika@natro.com",
                           "parola": parola})
    assert r.status_code == 400, r.text


@pytest.mark.parametrize("ad", ["A", "<script>alert(1)</script>", "Ad\nSoyad", "x" * 200])
def test_bozuk_ad_soyad_reddedilir(istemci, ad):
    r = istemci.post("/api/uyelik/kayit",
                     json={"ad_soyad": ad, "email": "adtest@natro.com", "parola": PAROLA})
    assert r.status_code in (400, 422), r.text


# ── Doğrulama akışı ──────────────────────────────────────────────────────────

def test_dogrulanmadan_giris_yapilamaz(istemci):
    uye_olustur(istemci, "bekleyen@natro.com", dogrula=False)
    r = istemci.post("/api/uyelik/giris",
                     json={"email": "bekleyen@natro.com", "parola": PAROLA})
    assert r.status_code == 403
    assert "doğrulan" in r.json()["detail"].lower()


def test_dogrulama_bagi_calisir_ve_tekrar_kullanilabilir(istemci):
    """İkinci çağrı da başarılı olmalı.

    natro.com Microsoft 365'te; Safe Links bağlantıyı kullanıcıdan ÖNCE açar.
    Katı tek kullanımlık davranış gerçek kullanıcıya "geçersiz bağlantı"
    gösterirdi — bu testin varlık sebebi o senaryo.
    """
    uye_olustur(istemci, "tarayici@natro.com", dogrula=False)
    tok = son_token()
    for _ in range(2):
        r = istemci.get(f"/api/uyelik/dogrula?token={tok}", follow_redirects=False)
        assert r.status_code == 303
        assert "dogrulama=ok" in r.headers["location"]


@pytest.mark.parametrize("tok", ["", "uydurma", "x" * 300])
def test_gecersiz_dogrulama_tokeni(istemci, tok):
    r = istemci.get(f"/api/uyelik/dogrula?token={tok}", follow_redirects=False)
    assert "dogrulama=ok" not in r.headers.get("location", "")


def test_dogrulama_hedefi_sabit_ic_yol(istemci):
    """Açık yönlendirme yok: hedefe kullanıcı girdisi karışmıyor."""
    r = istemci.get("/api/uyelik/dogrula?token=https://kotu.example/",
                    follow_redirects=False)
    assert r.headers["location"].startswith("/?dogrulama=")


def test_kayitli_adres_tekrar_kayitta_ayni_yaniti_verir(istemci):
    """Hesap sayımı kapalı: yanıt gövdesi ve durum kodu değişmemeli."""
    ilk = istemci.post("/api/uyelik/kayit",
                       json={"ad_soyad": "Sayim Test", "email": "sayim@natro.com",
                             "parola": PAROLA})
    istemci.get(f"/api/uyelik/dogrula?token={son_token()}", follow_redirects=False)
    ikinci = istemci.post("/api/uyelik/kayit",
                          json={"ad_soyad": "Sayim Test", "email": "sayim@natro.com",
                                "parola": PAROLA})
    assert ilk.status_code == ikinci.status_code == 202
    assert ilk.json() == ikinci.json()
    # Bilgi yalnızca adresin gerçek sahibine, e-posta ile gitmeli.
    assert "zaten" in son_mail_metni().lower()


# ── Oturum ve çerezler ───────────────────────────────────────────────────────

def test_giris_cerezleri_dogru_bayraklari_tasiyor(istemci):
    uye_olustur(istemci, UYE)
    r = istemci.post("/api/uyelik/giris", json={"email": UYE, "parola": PAROLA})
    assert r.status_code == 200
    cerezler = r.headers.get_list("set-cookie")
    oturum = next(s for s in cerezler if "hc_oturum" in s)
    csrf = next(s for s in cerezler if "hc_csrf" in s)
    assert "HttpOnly" in oturum                    # JavaScript okuyamamalı
    assert "HttpOnly" not in csrf                  # JavaScript OKUMALI
    assert "samesite=strict" in oturum.lower()
    assert "path=/;" in oturum.lower() or oturum.lower().rstrip().endswith("path=/")


def test_yanitlarda_parola_hashi_sizmaz(istemci):
    uye_olustur(istemci, UYE)
    giris_yap(istemci, UYE)
    for yol in ("/api/uyelik/ben", "/api/uyelik/oturumlarim"):
        assert "sifre_hash" not in istemci.get(yol).text


def test_her_giriste_yeni_oturum_tokeni(istemci):
    """Oturum sabitleme (session fixation) kapalı."""
    uye_olustur(istemci, UYE)
    giris_yap(istemci, UYE)
    ilk = istemci.cookies.get("hc_oturum")
    giris_yap(istemci, UYE)
    assert istemci.cookies.get("hc_oturum") != ilk


def test_cikis_oturumu_gercekten_dusurur(istemci):
    uye_olustur(istemci, UYE)
    basliklar = giris_yap(istemci, UYE)
    eski = istemci.cookies.get("hc_oturum")
    assert istemci.post("/api/uyelik/cikis", headers=basliklar).status_code == 200
    # Çerez elle geri konsa bile sunucudaki satır silindiği için geçersiz.
    istemci.cookies.set("hc_oturum", eski)
    assert istemci.get("/api/uyelik/ben").status_code == 401


def test_parola_degisince_diger_oturumlar_duser(istemci):
    from fastapi.testclient import TestClient
    import main

    uye_olustur(istemci, UYE)
    giris_yap(istemci, UYE)

    ikinci = TestClient(main.app, base_url="http://testserver")
    giris_yap(ikinci, UYE)
    assert ikinci.get("/api/uyelik/ben").status_code == 200

    basliklar = {"X-CSRF-Token": istemci.cookies.get("hc_csrf")}
    r = istemci.post("/api/uyelik/sifre-degistir", headers=basliklar,
                     json={"mevcut_parola": PAROLA, "yeni_parola": "Yeni-Parola-2026"})
    assert r.status_code == 200, r.text
    assert ikinci.get("/api/uyelik/ben").status_code == 401


# ── CSRF ─────────────────────────────────────────────────────────────────────

def test_csrf_basligi_olmadan_yazma_reddedilir(istemci):
    uye_olustur(istemci, ADMIN)
    giris_yap(istemci, ADMIN)
    r = istemci.post("/api/hazir-yanitlar",
                     json={"title": "X", "content": "Y", "category": "Genel"})
    assert r.status_code == 403


def test_yanlis_csrf_basligi_reddedilir(istemci):
    uye_olustur(istemci, ADMIN)
    giris_yap(istemci, ADMIN)
    r = istemci.post("/api/hazir-yanitlar", headers={"X-CSRF-Token": "yanlis-deger"},
                     json={"title": "X", "content": "Y", "category": "Genel"})
    assert r.status_code == 403


def test_okuma_istekleri_csrf_istemez(istemci):
    uye_olustur(istemci, UYE)
    giris_yap(istemci, UYE)
    assert istemci.get("/api/hazir-yanitlar").status_code == 200


def test_yabanci_origin_reddedilir(istemci):
    r = istemci.post("/api/uyelik/giris",
                     headers={"Origin": "https://kotu-site.example"},
                     json={"email": UYE, "parola": PAROLA})
    assert r.status_code == 403


# ── Kaba kuvvet ──────────────────────────────────────────────────────────────

def test_hesap_kilidi_yanlis_parolayi_frenler(istemci):
    """Kilit kurulur ama kendini ELE VERMEZ.

    Kilitli hesap 429, olmayan hesap 401 dönseydi kilit bir "bu adres kayıtlı
    mı" kâhinine dönüşürdü. Yanıt her durumda aynı.
    """
    from database import SessionLocal
    from models import Kullanici

    uye_olustur(istemci, "kilit@natro.com")
    yanitlar = [istemci.post("/api/uyelik/giris",
                             json={"email": "kilit@natro.com", "parola": "Yanlis-Parola-1"})
                for _ in range(6)]
    assert {r.status_code for r in yanitlar} == {401}, [r.status_code for r in yanitlar]
    assert {r.text for r in yanitlar} == {yanitlar[0].text}

    db = SessionLocal()
    try:
        k = db.query(Kullanici).filter(Kullanici.email == "kilit@natro.com").first()
        assert k.kilit_bitis is not None, "kilit kurulmadı"
    finally:
        db.close()


def test_kilit_dogru_parolayi_engellemez(istemci):
    """Hedefli servis dışı bırakma kapalı.

    Yönetici adresi kamuya açık; kilit doğru parolayı da bloklasaydı saldırgan
    15 dakikada bir 5 yanlış deneme yollayarak yöneticiyi kalıcı olarak dışarıda
    tutabilirdi.
    """
    from database import SessionLocal
    from models import Kullanici

    uye_olustur(istemci, "kilit2@natro.com")
    for _ in range(6):
        istemci.post("/api/uyelik/giris",
                     json={"email": "kilit2@natro.com", "parola": "Yanlis-Parola-1"})

    r = istemci.post("/api/uyelik/giris", json={"email": "kilit2@natro.com", "parola": PAROLA})
    assert r.status_code == 200, r.text

    # Başarılı giriş kilidi ve sayacı temizler.
    db = SessionLocal()
    try:
        k = db.query(Kullanici).filter(Kullanici.email == "kilit2@natro.com").first()
        assert k.kilit_bitis is None and k.basarisiz_giris == 0
    finally:
        db.close()


def test_kilitli_hesap_ile_olmayan_hesap_ayirt_edilemez(istemci):
    uye_olustur(istemci, "kilit3@natro.com")
    for _ in range(6):
        istemci.post("/api/uyelik/giris",
                     json={"email": "kilit3@natro.com", "parola": "Yanlis-Parola-1"})
    kilitli = istemci.post("/api/uyelik/giris",
                           json={"email": "kilit3@natro.com", "parola": "Yanlis-Parola-2"})
    yok = istemci.post("/api/uyelik/giris",
                       json={"email": "hicyok@natro.com", "parola": "Yanlis-Parola-2"})
    assert kilitli.status_code == yok.status_code == 401
    assert kilitli.json() == yok.json()


def test_bilinmeyen_adres_ve_yanlis_parola_ayni_yaniti_verir(istemci):
    uye_olustur(istemci, UYE)
    yok = istemci.post("/api/uyelik/giris",
                       json={"email": "hicyok@natro.com", "parola": PAROLA})
    yanlis = istemci.post("/api/uyelik/giris", json={"email": UYE, "parola": "Yanlis-Parola-1"})
    assert yok.status_code == yanlis.status_code == 401
    assert yok.json() == yanlis.json()


def test_ip_rate_limit_acikken_calisir(istemci):
    """Autouse fixture limiti kapatıyor; burada bilerek geri açılıyor."""
    from rate_limiter import limiter
    limiter.enabled = True
    try:
        kodlar = [istemci.post("/api/uyelik/kayit",
                               json={"ad_soyad": "Limit Test",
                                     "email": f"limit{i}@natro.com", "parola": PAROLA}
                               ).status_code for i in range(6)]
    finally:
        limiter.enabled = False
    assert 429 in kodlar, kodlar


# ── Parola sıfırlama ─────────────────────────────────────────────────────────

def test_sifre_sifirlama_akisi(istemci):
    uye_olustur(istemci, "sifirla@natro.com")
    r = istemci.post("/api/uyelik/sifre-unuttum", json={"email": "sifirla@natro.com"})
    assert r.status_code == 202
    tok = son_token("sifre")
    assert tok

    r = istemci.post("/api/uyelik/sifre-sifirla",
                     json={"token": tok, "yeni_parola": "Bambaska-Parola-99"})
    assert r.status_code == 200, r.text
    assert istemci.post("/api/uyelik/giris",
                        json={"email": "sifirla@natro.com",
                              "parola": "Bambaska-Parola-99"}).status_code == 200

    # Token tek kullanımlık.
    r = istemci.post("/api/uyelik/sifre-sifirla",
                     json={"token": tok, "yeni_parola": "Ucuncu-Parola-77"})
    assert r.status_code == 400


def test_sifre_unuttum_hesap_varligini_sizdirmaz(istemci):
    var = istemci.post("/api/uyelik/sifre-unuttum", json={"email": "sifirla@natro.com"})
    yok = istemci.post("/api/uyelik/sifre-unuttum", json={"email": "hicyok@natro.com"})
    assert var.status_code == yok.status_code == 202
    assert var.json() == yok.json()


# ── Yapılandırma güvenliği ───────────────────────────────────────────────────

def test_izinli_alan_listesi_bossa_kayit_kapanir(istemci, monkeypatch):
    """Boş liste "herkes girebilir" DEĞİL "kimse giremez" demeli.

    Bozuk ya da eksik bir `.env` kaydı, aksi hâlde paneli internete açardı.
    """
    monkeypatch.setenv("IZINLI_MAIL_ALANLARI", "")
    r = istemci.post("/api/uyelik/kayit",
                     json={"ad_soyad": "Yapilandirma Testi",
                           "email": "kimse@natro.com", "parola": PAROLA})
    assert r.status_code == 503, r.text
    assert "yapılandırılmamış" in r.json()["detail"].lower()


def test_yonetici_listesi_kodda_gomulu_degil(monkeypatch):
    """Varsayılan BOŞ: depo herkese açık olduğunda kaynak kod kimin
    hedefleneceğini söylememeli, yapılandırmayı unutan kurulumda da kimse
    kendiliğinden yönetici olmamalı."""
    import auth_core as ac
    monkeypatch.delenv("ADMIN_EPOSTALARI", raising=False)
    assert ac.kurucu_adminler() == set()
