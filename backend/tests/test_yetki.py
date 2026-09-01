"""Yetkilendirme kapıları — hazır yanıtlar ve yönetim uçları.

Ayrım üç katmanlı: anonim → üye → yönetici. Her uç için "yetkisiz olan
yapamıyor" tarafı, "yetkili olan yapabiliyor" tarafı kadar önemli; panel
internete açık olduğu için bir kapının açık kalması doğrudan veri kaybı
ya da müşteriye giden metnin değiştirilmesi demek.
"""
import pytest

from conftest import giris_yap, uye_olustur

UYE = "uye@natro.com"
ADMIN = "yonetici@natro.com"
IKINCI_ADMIN = "ikinci@team.blue"


@pytest.fixture
def anonim(istemci):
    return istemci


@pytest.fixture
def uye(istemci):
    uye_olustur(istemci, UYE)
    return istemci, giris_yap(istemci, UYE)


@pytest.fixture
def admin(istemci):
    uye_olustur(istemci, ADMIN, ad="Yonetici Hesabi")
    return istemci, giris_yap(istemci, ADMIN)


# ── Anonim ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("metot,yol", [
    ("get",    "/api/hazir-yanitlar"),
    ("get",    "/api/hazir-yanitlar/kategoriler"),
    ("post",   "/api/hazir-yanitlar"),
    ("put",    "/api/hazir-yanitlar/1"),
    ("delete", "/api/hazir-yanitlar/1"),
    ("patch",  "/api/hazir-yanitlar/1/pin"),
    ("post",   "/api/hazir-yanitlar/1/use"),
    ("post",   "/api/hazir-yanitlar/kategoriler"),
    ("delete", "/api/hazir-yanitlar/kategoriler/1"),
    ("get",    "/api/yonetim/istatistik"),
    ("get",    "/api/yonetim/kullanicilar"),
    ("get",    "/api/yonetim/denetim"),
    ("patch",  "/api/yonetim/kullanicilar/1"),
    ("delete", "/api/yonetim/kullanicilar/1"),
])
def test_anonim_hicbir_seye_erisemez(anonim, metot, yol):
    # GET/DELETE bu istemci sürümünde gövde almıyor.
    ek = {"json": {}} if metot in ("post", "put", "patch") else {}
    r = getattr(anonim, metot)(yol, **ek)
    assert r.status_code == 401, f"{metot.upper()} {yol} → {r.status_code}"


def test_anonim_acik_araclari_kullanmaya_devam_eder(anonim):
    """Üyelik YALNIZCA hazır yanıtları kapatmalı; teşhis araçları açık kalır."""
    assert anonim.get("/api/health").status_code == 200
    # Hatalı alan adı → 400 bekleniyor; önemli olan 401 GELMEMESİ.
    assert anonim.post("/api/dns-toolbox/query",
                       json={"domain": "", "record_type": "A"}).status_code != 401


# ── Üye ──────────────────────────────────────────────────────────────────────

def test_uye_okuyabilir(uye):
    c, _ = uye
    r = c.get("/api/hazir-yanitlar")
    assert r.status_code == 200 and len(r.json()) > 0
    assert c.get("/api/hazir-yanitlar/kategoriler").status_code == 200


def test_uye_kullanim_sayacini_artirabilir(uye):
    c, h = uye
    yid = c.get("/api/hazir-yanitlar").json()[0]["id"]
    once = c.get("/api/hazir-yanitlar").json()[0]["use_count"]
    r = c.post(f"/api/hazir-yanitlar/{yid}/use", headers=h)
    assert r.status_code == 200
    assert r.json()["use_count"] == once + 1


@pytest.mark.parametrize("metot,yol,govde", [
    ("post",   "/api/hazir-yanitlar", {"title": "X", "content": "Y", "category": "Genel"}),
    ("put",    "/api/hazir-yanitlar/1", {"title": "X"}),
    ("delete", "/api/hazir-yanitlar/1", None),
    ("patch",  "/api/hazir-yanitlar/1/pin", None),
    ("post",   "/api/hazir-yanitlar/kategoriler", {"name": "Yeni", "color": "#3b7eff"}),
    ("delete", "/api/hazir-yanitlar/kategoriler/1", None),
])
def test_uye_yazamaz(uye, metot, yol, govde):
    c, h = uye
    r = getattr(c, metot)(yol, headers=h, **({"json": govde} if govde else {}))
    assert r.status_code == 403, f"{metot.upper()} {yol} → {r.status_code}"
    assert "yönetici" in r.json()["detail"].lower()


@pytest.mark.parametrize("yol", [
    "/api/yonetim/istatistik", "/api/yonetim/kullanicilar",
    "/api/yonetim/denetim", "/api/yonetim/denetim/eylemler",
])
def test_uye_yonetime_giremez(uye, yol):
    c, _ = uye
    assert c.get(yol).status_code == 403


def test_uye_baska_kullaniciyi_degistiremez(uye, istemci):
    c, h = uye
    assert c.patch("/api/yonetim/kullanicilar/1", headers=h,
                   json={"rol": "admin"}).status_code == 403
    assert c.delete("/api/yonetim/kullanicilar/1", headers=h).status_code == 403


# ── Yönetici ─────────────────────────────────────────────────────────────────

def test_admin_rolu_env_listesinden_gelir(admin):
    c, _ = admin
    assert c.get("/api/uyelik/ben").json()["rol"] == "admin"


def test_admin_crud_yapabilir(admin):
    c, h = admin
    r = c.post("/api/hazir-yanitlar", headers=h,
               json={"title": "Test Yanıt", "content": "İçerik metni", "category": "Genel"})
    assert r.status_code == 201, r.text
    yid = r.json()["id"]

    assert c.put(f"/api/hazir-yanitlar/{yid}", headers=h,
                 json={"title": "Güncellendi"}).json()["title"] == "Güncellendi"
    assert c.patch(f"/api/hazir-yanitlar/{yid}/pin", headers=h).json()["is_pinned"] is True
    assert c.delete(f"/api/hazir-yanitlar/{yid}", headers=h).status_code == 204
    assert c.put(f"/api/hazir-yanitlar/{yid}", headers=h, json={"title": "X"}).status_code == 404


def test_admin_kategori_yonetebilir(admin):
    c, h = admin
    r = c.post("/api/hazir-yanitlar/kategoriler", headers=h,
               json={"name": "Fatura", "color": "#22c55e"})
    assert r.status_code == 201, r.text
    kid = r.json()["id"]
    # Aynı ad ikinci kez eklenemez.
    assert c.post("/api/hazir-yanitlar/kategoriler", headers=h,
                  json={"name": "Fatura", "color": "#22c55e"}).status_code == 409
    assert c.delete(f"/api/hazir-yanitlar/kategoriler/{kid}", headers=h).status_code == 204


@pytest.mark.parametrize("renk", ["javascript:alert(1)", "red; background:url(x)", "#zzzzzz", "#fff"])
def test_kategori_rengi_dogrulanir(admin, renk):
    """Renk doğrudan `style` özniteliğine giriyor; serbest metin olmamalı."""
    c, h = admin
    r = c.post("/api/hazir-yanitlar/kategoriler", headers=h,
               json={"name": "RenkTest", "color": renk})
    assert r.status_code == 422, r.text


def test_icerik_ust_siniri_uygulanir(admin):
    c, h = admin
    r = c.post("/api/hazir-yanitlar", headers=h,
               json={"title": "Büyük", "content": "x" * 20_001, "category": "Genel"})
    assert r.status_code == 422


def test_admin_kendini_koruyan_kurallar(admin):
    c, h = admin
    ben = c.get("/api/uyelik/ben").json()["id"]
    assert c.patch(f"/api/yonetim/kullanicilar/{ben}", headers=h,
                   json={"rol": "uye"}).status_code == 400
    assert c.patch(f"/api/yonetim/kullanicilar/{ben}", headers=h,
                   json={"aktif": False}).status_code == 400
    assert c.delete(f"/api/yonetim/kullanicilar/{ben}", headers=h).status_code == 400


def test_kurucu_admin_baska_yoneticiden_de_korunur(admin, istemci):
    """`.env`'deki yönetici, panelden yönetici yapılmış biri tarafından bile düşürülemez."""
    c, h = admin
    uye_olustur(c, IKINCI_ADMIN, ad="Ikinci Yonetici")
    liste = c.get("/api/yonetim/kullanicilar").json()["kayitlar"]
    ikinci_id = next(k["id"] for k in liste if k["email"] == IKINCI_ADMIN)
    kurucu_id = next(k["id"] for k in liste if k["email"] == ADMIN)
    assert c.patch(f"/api/yonetim/kullanicilar/{ikinci_id}", headers=h,
                   json={"rol": "admin"}).status_code == 200

    from fastapi.testclient import TestClient
    import main
    c2 = TestClient(main.app, base_url="http://testserver")
    h2 = giris_yap(c2, IKINCI_ADMIN)
    assert c2.patch(f"/api/yonetim/kullanicilar/{kurucu_id}", headers=h2,
                    json={"rol": "uye"}).status_code == 400
    assert c2.delete(f"/api/yonetim/kullanicilar/{kurucu_id}", headers=h2).status_code == 400


def test_askiya_alinan_uyenin_oturumu_aninda_duser(admin, istemci):
    from fastapi.testclient import TestClient
    import main

    c, h = admin
    uye_olustur(c, UYE)
    kurban = TestClient(main.app, base_url="http://testserver")
    giris_yap(kurban, UYE)
    assert kurban.get("/api/hazir-yanitlar").status_code == 200

    uid = next(k["id"] for k in c.get("/api/yonetim/kullanicilar").json()["kayitlar"]
               if k["email"] == UYE)
    assert c.patch(f"/api/yonetim/kullanicilar/{uid}", headers=h,
                   json={"aktif": False}).status_code == 200
    # Çerez hâlâ tarayıcıda ama sunucu tarafı oturum silindi.
    assert kurban.get("/api/hazir-yanitlar").status_code == 401


def test_yonetici_kullanici_oturumlarini_kapatabilir(admin):
    from fastapi.testclient import TestClient
    import main

    c, h = admin
    uye_olustur(c, UYE)
    kurban = TestClient(main.app, base_url="http://testserver")
    giris_yap(kurban, UYE)
    uid = next(k["id"] for k in c.get("/api/yonetim/kullanicilar").json()["kayitlar"]
               if k["email"] == UYE)
    r = c.post(f"/api/yonetim/kullanicilar/{uid}/oturumlari-kapat", headers=h)
    assert r.status_code == 200 and r.json()["kapatilan"] >= 1
    assert kurban.get("/api/uyelik/ben").status_code == 401


# ── Denetim kaydı ────────────────────────────────────────────────────────────

def test_denetim_kaydi_crud_izini_tutar(admin):
    c, h = admin
    r = c.post("/api/hazir-yanitlar", headers=h,
               json={"title": "İzlenen Yanıt", "content": "İçerik", "category": "Genel"})
    yid = r.json()["id"]
    c.delete(f"/api/hazir-yanitlar/{yid}", headers=h)

    kayitlar = c.get("/api/yonetim/denetim").json()["kayitlar"]
    eylemler = {k["eylem"] for k in kayitlar}
    assert {"yanit_ekle", "yanit_sil", "giris", "kayit"} <= eylemler, eylemler
    ekleme = next(k for k in kayitlar if k["eylem"] == "yanit_ekle")
    assert ekleme["eposta"] == ADMIN
    assert ekleme["hedef"] == f"yanit:{yid}"


def test_basarisiz_girisler_denetime_dusuyor(admin):
    c, h = admin
    c.post("/api/uyelik/giris", json={"email": "sahte@natro.com", "parola": "Yanlis-Parola-1"})
    kayitlar = c.get("/api/yonetim/denetim?eylem=giris_basarisiz").json()
    assert kayitlar["toplam"] >= 1


def test_denetim_kaydinda_satir_sonu_enjeksiyonu_yok(admin):
    """Ad/e-posta ham `\\n` taşırsa denetim tablosunda sahte satır üretirdi."""
    c, h = admin
    c.post("/api/uyelik/giris",
           json={"email": "sahte@natro.com", "parola": "Yanlis-Parola-1"})
    for k in c.get("/api/yonetim/denetim").json()["kayitlar"]:
        for alan in ("eposta", "hedef", "detay"):
            assert "\n" not in (k[alan] or "") and "\r" not in (k[alan] or "")


# ── İstatistikler ────────────────────────────────────────────────────────────

def test_istatistikler_tutarli(admin):
    c, h = admin
    uye_olustur(c, UYE)
    j = c.get("/api/yonetim/istatistik").json()
    assert j["toplam_uye"] == 2
    assert j["yonetici"] == 1
    assert j["toplam_yanit"] > 0
    assert isinstance(j["en_cok_kullanilan"], list)


def test_kullanici_aramasi_joker_karakter_sizdirmaz(admin):
    """`%` kullanıcıdan gelirse tüm tabloyu döndüren desen yazılabilirdi."""
    c, h = admin
    uye_olustur(c, UYE)
    assert c.get("/api/yonetim/kullanicilar?arama=%").json()["toplam"] == 0
    assert c.get("/api/yonetim/kullanicilar?arama=uye").json()["toplam"] == 1


def test_sayfalama_siniri_zorlanamaz(admin):
    c, _ = admin
    assert c.get("/api/yonetim/kullanicilar?limit=100000").json()["limit"] == 100
    assert c.get("/api/yonetim/denetim?sayfa=-5").json()["sayfa"] == 1
