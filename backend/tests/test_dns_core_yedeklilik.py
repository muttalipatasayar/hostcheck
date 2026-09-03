"""Public resolver listesinin GERÇEKTEN yedekli olduğunu doğrular — ağsız.

Bu dosyanın varlık sebebi somut bir olay: 8.8.8.8'e giden UDP/53 ağda
filtrelenince panelin TÜM DNS teşhisi çöktü. DNS Toolbox "Sorgu hatası:
LifetimeTimeout", Hızlı Kontrol ise gayet çözümlenen bir alan adı için
"NS yanıt vermiyor / Çözümlenemiyor" dedi. Oysa listedeki 1.1.1.1 ve 9.9.9.9
anında yanıtlıyordu.

Sebep: dnspython'da `timeout` TEK denemenin, `lifetime` ise sorgunun TAMAMININ
bütçesidir. İkisi eşit verilince ilk sunucu bütçenin hepsini yiyor ve resolver
ikinciye HİÇ geçemiyordu — PUBLIC_DNS listeleri yedeklilik sağlıyor görünüp
ölü koddu.

Bu, süitin hedeflediği sınıfın tam örneği: araç patlamıyor, sessizce YANLIŞ
cevap veriyor. O yüzden testler "sonuç doğru mu"dan çok "ikinci sunucuya
geçebiliyor mu" sorusunu ölçüyor.
"""
import pytest

import dns_core


PUBLIC_UCLU = ['8.8.8.8', '1.1.1.1', '9.9.9.9']
SESSIZ_SUNUCU = PUBLIC_UCLU[0]
BUTCE = 0.3          # testi hızlı tutar; ölçülen oran, mutlak süre değil


# ── Bütçe bölüşümü ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fabrika", [
    dns_core.make_resolver,
    dns_core.make_async_resolver,
])
def test_tek_deneme_toplam_butceden_kucuk_olmali(fabrika):
    """Regresyon kilidi: timeout == lifetime olursa yedeklilik ölür."""
    r = fabrika(PUBLIC_UCLU, 5.0)
    assert r.timeout < r.lifetime, (
        "timeout (tek deneme) lifetime'a (toplam) eşitse ilk sunucu bütçenin "
        "tamamını tüketir ve diğerleri hiç denenmez"
    )


@pytest.mark.parametrize("fabrika", [
    dns_core.make_resolver,
    dns_core.make_async_resolver,
])
def test_toplam_butce_korunur(fabrika):
    """Yedeklilik gecikme pahasına gelmemeli — uçların dış wait_for'ları
    bugünkü bütçeye göre ayarlı; lifetime büyürse `run_in_executor` thread'i
    wait_for döndükten SONRA da çalışmaya devam eder."""
    for ns, butce in [(PUBLIC_UCLU, 5.0), (['8.8.8.8', '1.1.1.1'], 3.0), (['1.1.1.1'], 4.0)]:
        r = fabrika(ns, butce)
        assert r.lifetime == pytest.approx(butce)


@pytest.mark.parametrize("fabrika", [
    dns_core.make_resolver,
    dns_core.make_async_resolver,
])
def test_her_sunucuya_pay_dusur(fabrika):
    """Listedeki her sunucu bütçe dolmadan sıraya gelebilmeli."""
    r = fabrika(PUBLIC_UCLU, 5.0)
    assert r.timeout * len(PUBLIC_UCLU) <= r.lifetime + 1e-9


def test_tek_sunucuda_davranis_degismez():
    """DNS Yayılma her coğrafi resolver'ı TEK BAŞINA sorgular ve onu bağımsız
    yargılar; oradaki timeout == lifetime doğrudur, bu düzeltme dokunmamalı."""
    r = dns_core.make_resolver(['1.1.1.1'], 4.0)
    assert r.timeout == pytest.approx(4.0)
    assert r.lifetime == pytest.approx(4.0)


def test_bos_liste_sifira_bolmez():
    pay, toplam = dns_core.sure_paylastir([], 3.0)
    assert pay == pytest.approx(3.0) and toplam == pytest.approx(3.0)


# ── Gerçekten sıradaki sunucuya geçiyor mu ───────────────────────────────────

def test_ilk_sunucu_sessizse_ikinciye_gecilir(monkeypatch):
    """Olayın ağsız yeniden üretimi: 1. sunucu UDP/53'te hiç yanıtlamıyor.

    Sahte soket kendisine verilen `timeout` kadar GERÇEKTEN bekler — olayın
    özü zamanlamaydı, anında fırlatan bir sahte istisna hatalı kodda da
    ikinci sunucuya geçer ve testi yalancı-yeşil bırakırdı.

    Bütçe milisaniyeler seviyesinde tutuldu; ölçülen oran, süre değil.
    """
    import time
    import dns.exception
    import dns.message
    import dns.query

    denenen: list[str] = []

    def sahte_udp(q, where, timeout=None, **kw):
        denenen.append(where)
        if where == SESSIZ_SUNUCU:
            time.sleep(timeout)                       # filtrelenmiş UDP/53
            raise dns.exception.Timeout(timeout=timeout)
        return dns.message.make_response(q)           # boş ama YANIT

    monkeypatch.setattr(dns.query, 'udp', sahte_udp, raising=True)

    r = dns_core.make_resolver(PUBLIC_UCLU, BUTCE)
    with pytest.raises(Exception):
        r.resolve('example.com', 'A')   # boş yanıt → NoAnswer; önemli olan SIRA

    assert denenen[0] == SESSIZ_SUNUCU, f"ilk sunucu denenmemiş: {denenen}"
    assert len(denenen) > 1, (
        f"ilk sunucu sustuğunda yedeğe HİÇ geçilmedi — denenen: {denenen}. "
        f"Bütçenin tamamı tek sunucuya gitmiş demektir."
    )
