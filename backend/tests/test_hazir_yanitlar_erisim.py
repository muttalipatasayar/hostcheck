"""Hazır Yanıtlar'ın erişim modeli — üyelik geri alındıktan sonraki hâli.

3 Eylül 2026'da uygulama içi üyelik kaldırıldı. Model yeniden şu:

    okuma  → anonim, uygulamada hiçbir kapı yok
    yazma  → uygulamada DA kapı yok; TEK koruma Nginx'teki
             `location /api/hazir-yanitlar { limit_except GET HEAD { auth_basic } }`

Bu dosya iki şeyi birden sabitliyor:

1. Okumanın gerçekten anonim çalıştığı (regresyon: 401 dönerse üyelik geri
   sızmış demektir).
2. Yazmanın uygulamada AÇIK olduğu. Bu bir kusur değil, bilinçli bir sözleşme —
   ama sözleşmenin diğer yarısı Nginx'te. Testin adı ve mesajı, bu uçları
   Nginx'siz bir ortama (doğrudan 8000, ayrı bir vhost, farklı bir prefix)
   taşımanın kütüphaneyi internete yazılabilir bırakacağını söylüyor.

Ayrıca üyelikten kalan ve BİLEREK korunan sertleştirmeler doğrulanıyor:
içerik uzunluk sınırı, kategori rengi regex'i ve yazma uçlarındaki rate limit.
Bunlar erişim denetimi değil; kimlik doğrulamadan bağımsız kaynak ve
enjeksiyon korumalarıdır, üyelikle birlikte gitmemeleri gerekirdi.
"""
import pytest

YAZMA_ISTEKLERI = [
    ("post",   "/api/hazir-yanitlar",
     {"title": "T", "content": "C", "category": "Genel"}),
    ("post",   "/api/hazir-yanitlar/kategoriler",
     {"name": "Kapi Testi", "color": "#123456"}),
]


# ── Okuma anonim ─────────────────────────────────────────────────────────────

def test_liste_anonim_okunabilir(istemci):
    """Üyelik kapısı gerçekten kalktı mı."""
    r = istemci.get("/api/hazir-yanitlar")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_tohumlama_acilista_calisti(istemci):
    """Liste boş dönmemeli: tohumlama lifespan'da, GET ucunda değil.

    Üyelik döneminde tohumlama GET'ten açılışa taşınmıştı; uç anonime
    açıldıktan sonra da açılışta bırakıldı. Taşınırken unutulursa liste
    sessizce boş döner ve panel "kütüphane silinmiş" gibi görünür.
    """
    yanitlar = istemci.get("/api/hazir-yanitlar").json()
    assert len(yanitlar) > 50, f"tohumlama çalışmamış görünüyor ({len(yanitlar)} kayıt)"


def test_kategoriler_anonim_okunabilir(istemci):
    assert istemci.get("/api/hazir-yanitlar/kategoriler").status_code == 200


def test_kategoriler_rotasi_id_parametresinden_once_eslesir(istemci):
    """`/kategoriler` `/{yanit_id}`'den ÖNCE tanımlı kalmalı.

    Sıra bozulursa FastAPI `kategoriler`'i int yol parametresi sanar ve uç
    422 döndürür — CLAUDE.md'de yazılı, kolayca geri gelen bir tuzak.
    """
    assert istemci.get("/api/hazir-yanitlar/kategoriler").status_code != 422


def test_yanit_yoksa_404(istemci):
    assert istemci.put("/api/hazir-yanitlar/99999",
                       json={"title": "yok"}).status_code == 404


# ── Yazma: uygulamada kapı YOK (koruma Nginx'te) ─────────────────────────────

@pytest.mark.parametrize("metot,yol,govde", YAZMA_ISTEKLERI)
def test_yazma_uygulamada_acik_koruma_nginxte(istemci, metot, yol, govde):
    """Yazma uçları uygulamada kimlik SORMAZ — koruma Nginx'te.

    Bu test 401/403 görürse uygulamaya yeniden bir kimlik katmanı girmiş
    demektir; 200/201 görürse sözleşme yerinde ama Nginx'teki
    `limit_except GET HEAD { auth_basic }` bloğu ZORUNLUDUR. O blok olmadan
    bu uçlar internete yazılabilir olur.
    """
    r = getattr(istemci, metot)(yol, json=govde)
    assert r.status_code not in (401, 403), (
        "Hazır yanıt yazma ucuna uygulama içi kimlik kapısı geri gelmiş; "
        "üyelik geri alınmıştı (bkz. routers/hazir_yanitlar.py başlığı)."
    )
    assert r.status_code == 201, r.text


def test_uc_uctan_uca_yazma_dongusu(istemci):
    """Ekle → güncelle → sabitle → kullan → sil."""
    r = istemci.post("/api/hazir-yanitlar",
                     json={"title": "Döngü", "content": "gövde", "category": "SSL"})
    assert r.status_code == 201, r.text
    yid = r.json()["id"]

    r = istemci.put(f"/api/hazir-yanitlar/{yid}", json={"title": "Döngü v2"})
    assert r.status_code == 200 and r.json()["title"] == "Döngü v2"
    assert r.json()["content"] == "gövde", "kısmi güncelleme diğer alanları silmemeli"

    assert istemci.patch(f"/api/hazir-yanitlar/{yid}/pin").json()["is_pinned"] is True
    assert istemci.post(f"/api/hazir-yanitlar/{yid}/use").json()["use_count"] == 1

    assert istemci.delete(f"/api/hazir-yanitlar/{yid}").status_code == 204
    assert istemci.put(f"/api/hazir-yanitlar/{yid}", json={"title": "x"}).status_code == 404


# ── Üyelikten kalan sertleştirmeler KORUNDU ──────────────────────────────────

def test_icerik_uzunluk_siniri_duruyor(istemci):
    """`content` üst sınırı erişim denetimi DEĞİL, disk doldurma korumasıdır.

    Uç auth'suz; sınır kalkarsa tek istekle SQLite dosyası şişirilebilir.
    """
    from routers.hazir_yanitlar import MAX_CONTENT_LEN

    r = istemci.post("/api/hazir-yanitlar", json={
        "title": "Uzun", "content": "a" * (MAX_CONTENT_LEN + 1), "category": "Genel"})
    assert r.status_code == 422

    r = istemci.post("/api/hazir-yanitlar", json={
        "title": "Sınırda", "content": "a" * MAX_CONTENT_LEN, "category": "Genel"})
    assert r.status_code == 201, "sınırın kendisi kabul edilmeli"
    istemci.delete(f"/api/hazir-yanitlar/{r.json()['id']}")


def test_baslik_ve_kategori_uzunluk_sinirlari(istemci):
    for alan, uzunluk in (("title", 201), ("category", 101)):
        govde = {"title": "T", "content": "C", "category": "Genel"}
        govde[alan] = "a" * uzunluk
        assert istemci.post("/api/hazir-yanitlar", json=govde).status_code == 422, alan


@pytest.mark.parametrize("renk", [
    "red",
    "#12345",                                    # 5 hane
    "#1234567",                                  # 7 hane
    "#123456; background:url(//evil/x)",         # CSS enjeksiyonu
    "javascript:alert(1)",
])
def test_kategori_rengi_serbest_metin_kabul_etmez(istemci, renk):
    """Renk doğrudan `style` özniteliğine giriyor — serbest metin CSS enjeksiyonu."""
    r = istemci.post("/api/hazir-yanitlar/kategoriler",
                     json={"name": f"K-{renk[:6]}", "color": renk})
    assert r.status_code == 422, f"{renk!r} kabul edildi"


def test_gecerli_renk_kabul_edilir(istemci):
    r = istemci.post("/api/hazir-yanitlar/kategoriler",
                     json={"name": "Gecerli Renk", "color": "#a1B2c3"})
    assert r.status_code == 201, r.text
    istemci.delete(f"/api/hazir-yanitlar/kategoriler/{r.json()['id']}")


def test_ayni_kategori_iki_kez_eklenemez(istemci):
    ilk = istemci.post("/api/hazir-yanitlar/kategoriler",
                       json={"name": "Tekil", "color": "#111111"})
    assert ilk.status_code == 201
    try:
        assert istemci.post("/api/hazir-yanitlar/kategoriler",
                            json={"name": "Tekil", "color": "#111111"}).status_code == 409
    finally:
        istemci.delete(f"/api/hazir-yanitlar/kategoriler/{ilk.json()['id']}")


def test_yazma_ucunda_rate_limit_var(istemci):
    """Sınır conftest'te kapalı; burada bilerek açılıyor.

    Yazma ucu auth'suz: sınır kalkarsa tek istemci kütüphaneyi sınırsız
    büyütebilir. `create_kategori` 20/dakika.
    """
    from rate_limiter import limiter
    limiter.enabled = True
    try:
        kodlar = [
            istemci.post("/api/hazir-yanitlar/kategoriler",
                         json={"name": "Limit", "color": "#222222"}).status_code
            for _ in range(26)
        ]
    finally:
        limiter.enabled = False
        for k in istemci.get("/api/hazir-yanitlar/kategoriler").json():
            if k["name"] == "Limit":
                istemci.delete(f"/api/hazir-yanitlar/kategoriler/{k['id']}")
    assert 429 in kodlar, "20/dakika sınırı tetiklenmedi"


# ── Üyelik gerçekten gitti ───────────────────────────────────────────────────

@pytest.mark.parametrize("yol", [
    "/api/uyelik/kayit", "/api/uyelik/giris", "/api/uyelik/dogrula",
    "/api/uyelik/ben", "/api/uyelik/cikis", "/api/uyelik/sifre-unuttum",
    "/api/yonetim/kullanicilar", "/api/yonetim/denetim",
])
def test_uyelik_uclari_kaldirildi(istemci, yol):
    """Router'lar silindi; uçlar 404 vermeli.

    405 de kabul: bazı yollar başka bir router'ın yol parametresine düşebilir.
    Kabul EDİLMEYEN 200/401/403 — bunlar ucun hâlâ ayakta olduğunu gösterir.
    """
    for metot in ("get", "post"):
        kod = getattr(istemci, metot)(yol).status_code
        assert kod in (404, 405), f"{metot.upper()} {yol} → {kod}"


def test_uyelik_tablolari_semadan_dusuruldu():
    """0004_uyelik_kaldir uygulandı mı."""
    import sqlalchemy as sa
    from database import engine

    tablolar = set(sa.inspect(engine).get_table_names())
    assert not tablolar & {"kullanicilar", "oturumlar",
                           "eposta_tokenleri", "denetim_kayitlari"}
    assert "hazir_yanitlar" in tablolar, "hazır yanıt tablosu düşürülmemeli"


def test_oturum_cerezi_set_edilmiyor(istemci):
    """Hiçbir uç artık oturum/CSRF çerezi yazmamalı."""
    r = istemci.get("/api/hazir-yanitlar")
    assert "set-cookie" not in {k.lower() for k in r.headers}


def test_modelde_uyelik_sinifi_kalmadi():
    import models

    for ad in ("Kullanici", "Oturum", "EpostaTokeni", "DenetimKaydi"):
        assert not hasattr(models, ad), f"models.{ad} hâlâ duruyor"
