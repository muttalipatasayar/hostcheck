"""Bloklayan iş VARSAYILAN thread havuzuna taşmamalı — ağsız.

Neden ayrı bir dosya: bu, "araç yanlış cevap veriyor" değil "araç ALAKASIZ
araçları düşürüyor" sınıfı. Ölçüm somuttu — DKIM otomatik keşfi batch başına
5 bloklayan sorgu açıyor ve `wait_for` dolduğunda thread iptal edilemiyor
(`run_in_executor` future'ı iptal edilse de thread çalışmaya devam eder).
İki eşzamanlı keşif, auth'suz bir uçta ve rate limitin çok altında, 10
thread'lik varsayılan havuzun tamamını tutuyordu; o havuzu SSRF kapısı
(`net_validation.resolve_public_ips_async`), whois, SSL el sıkışmaları ve
üyelik e-postaları paylaşıyor.

DNS burada taklit edilir; ölçülen şey ağ değil, hangi havuzun tutulduğu.
"""
import asyncio
import concurrent.futures
import inspect
import time

import pytest

import routers.dns_toolbox as dt


@pytest.fixture
def yavas_dns(monkeypatch):
    """Her DNS sorgusu 1 sn bloklar — sessiz bir resolver'ın taklidi."""
    def sahte(queried, rtype):
        time.sleep(1.0)
        raise Exception("no answer")
    monkeypatch.setattr(dt, '_query_sync', sahte)


def _kod_satirlari(modul) -> str:
    """Yorumları ve docstringleri ATAR — yalnızca çalışan kod kalır.

    Bu depo aynı tuzağa bir kez düştü (commit 610315c: unsafe-eval kontrolü
    yorumları da sayıyordu). Aşağıdaki kilidin arandığı desen bu dosyanın
    kendi açıklama yorumlarında da geçiyor.
    """
    import io as _io
    import tokenize
    parcalar = []
    okuyucu = _io.StringIO(inspect.getsource(modul)).readline
    onceki_tur = tokenize.INDENT
    for tok in tokenize.generate_tokens(okuyucu):
        if tok.type == tokenize.COMMENT:
            continue
        # Deyim başındaki string = docstring
        if tok.type == tokenize.STRING and onceki_tur in (
                tokenize.INDENT, tokenize.DEDENT, tokenize.NEWLINE, tokenize.NL):
            continue
        if tok.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            onceki_tur = tok.type
        parcalar.append(tok.string)
    # BOŞ string ile birleştir: "\n" ile birleştirmek `f(None` gibi çağrı
    # desenlerini token sınırlarında bölüyor ve aramayı sessizce etkisiz kılar.
    return "".join(parcalar)


def test_ayrilmis_havuz_kullaniliyor():
    """Yapısal kilit: birisi `run_in_executor(None, …)`'a geri dönerse yakala."""
    kod = _kod_satirlari(dt)
    assert 'run_in_executor(None' not in kod, (
        "DNS Toolbox varsayılan havuza iş vermemeli — o havuzu SSRF kapısı, "
        "whois, SSL ve mailer paylaşıyor (bkz. _DNS_EXECUTOR)"
    )
    assert '_DNS_EXECUTOR' in kod
    assert dt._DNS_EXECUTOR is not None


def test_kesif_batchinden_genis_havuz():
    """Keşif 5 thread alır; sıradan sorgulara pay kalmazsa kuyrukta bekleyen
    sorgu dış wait_for'u aşar ve sessizce 'kayıt yok' der."""
    assert dt._DNS_EXECUTOR._max_workers > 5


def test_kesif_varsayilan_havuzu_tikamiyor(yavas_dns):
    """Olayın ağsız yeniden üretimi: 2 eşzamanlı keşif sırasında ALAKASIZ bir
    işin varsayılan havuza girme süresi ölçülür."""
    async def senaryo():
        loop = asyncio.get_running_loop()
        loop.set_default_executor(
            concurrent.futures.ThreadPoolExecutor(max_workers=10))   # üretimdeki boyut

        async def alakasiz_isin_beklemesi():
            t = time.monotonic()
            await loop.run_in_executor(None, lambda: None)   # hiç iş yapmıyor
            return time.monotonic() - t

        assert await alakasiz_isin_beklemesi() < 0.2, "referans ölçüm kirli"

        gorevler = [asyncio.create_task(dt._dkim_auto_discover(f"x{i}.test"))
                    for i in range(2)]
        await asyncio.sleep(0.3)              # havuzlar dolsun
        bekleme = await alakasiz_isin_beklemesi()

        for g in gorevler:
            g.cancel()
        await asyncio.gather(*gorevler, return_exceptions=True)
        return bekleme

    bekleme = asyncio.run(senaryo())
    assert bekleme < 0.2, (
        f"DKIM keşfi varsayılan havuzu tıkadı ({bekleme:.3f}s bekleme). "
        f"SSRF doğrulaması ve üyelik e-postaları bu havuzda."
    )


def test_kesif_sureç_genelinde_tek_calisir(yavas_dns):
    """Kelepçe olmadan farklı IP'lerden gelen keşifler havuzu yine doldururdu;
    rate limit IP başına sayar, süreç geneli tavanı yoktur."""
    async def senaryo():
        assert dt._KESIF_KELEPCE._value == 1
        g = asyncio.create_task(dt._dkim_auto_discover("a.test"))
        await asyncio.sleep(0.3)
        assert dt._KESIF_KELEPCE.locked(), "keşif kelepçeyi almamış"
        g.cancel()
        await asyncio.gather(g, return_exceptions=True)

    asyncio.run(senaryo())


def test_kelepce_wait_for_penceresinin_disinda(yavas_dns):
    """Sıra beklemek selector'ı zaman aşımına DÜŞÜRMEMELİ — düşerse araç
    'bu selector yok' der ve teknisyeni yanlış yere gönderir."""

    kaynak = inspect.getsource(dt._dkim_auto_discover)
    kelepce = kaynak.index('_KESIF_KELEPCE')
    batch = kaynak.index('for i in range(0, len(COMMON_SELECTORS)')
    assert kelepce < batch, "kelepçe fan-out'un TAMAMINI sarmalı"


# ── Hızlı Kontrol ─────────────────────────────────────────────────────────────
#
# Aynı sınıf, panelin en çok kullanılan aracında: tek istek WHOIS + NS + A
# (+gethostbyname) + MX + SSL el sıkışmasını `gather` ile aynı anda açıyor,
# yani ~6 bloklayan thread. İki eşzamanlı istek 10 thread'lik varsayılan
# havuzu dolduruyordu.

import routers.quick_check as qc


def test_quick_check_ayrilmis_havuz_kullaniyor():
    kod = _kod_satirlari(qc)
    assert 'run_in_executor(None' not in kod, (
        "Hızlı Kontrol varsayılan havuza iş vermemeli — istek başına ~6 thread "
        "açıyor ve o havuzda SSRF kapısı ile mailer var (bkz. _QC_EXECUTOR)"
    )
    assert qc._QC_EXECUTOR is not None


def test_quick_check_havuzu_kelepceyi_kuyruksuz_karsilar():
    """Kelepçeyi geçen her istek kendi thread'lerini KUYRUĞA GİRMEDEN bulmalı.

    Bulamazsa kontrolün kendi `wait_for` bütçesi thread beklerken işler ve
    araç sağlıklı bir sunucu için 'zaman aşımı' der — bu panelde yavaş cevap
    kabul edilebilir, yanlış cevap değildir.
    """
    assert qc._QC_EXECUTOR._max_workers >= (
        qc._QC_ISTEK_BASINA_THREAD * qc._QC_ESZAMANLI_ISTEK)


def test_quick_check_kelepcesi_gatherdan_once_alinir():
    """Sıra beklemek kontrollerin wait_for penceresinin DIŞINDA kalmalı."""
    import inspect as _i
    kaynak = _i.getsource(qc.quick_check)
    assert kaynak.index('_QC_KELEPCE') < kaynak.index('asyncio.gather'), (
        "kelepçe gather'ı sarmalı, içinde alınmamalı")


def test_quick_check_gorevleri_kelepceden_once_baslamiyor():
    """`do_whois(...)` gibi çağrılar COROUTINE döndürmeli (create_task DEĞİL) —
    aksi halde iş kelepçe alınmadan başlar ve kelepçe hiçbir şey korumaz."""
    import inspect as _i
    kaynak = _i.getsource(qc.quick_check)
    kelepce = kaynak.index('_QC_KELEPCE')
    assert 'create_task' not in kaynak[:kelepce], (
        "kontroller kelepçeden ÖNCE task'a çevrilirse hemen çalışmaya başlar")
