// Sayfaya navigasyondan ÖNCE enjekte edilir (add_init_script).
//
// Buraya kadar olan kısımda vendor'lanmış web-vitals "attribution" build'i
// yüklenmiştir ve `webVitals` global'i hazırdır. Elle PerformanceObserver
// yazmak yerine kütüphaneyi kullanıyoruz: LCP'nin ne zaman kesinleştiği,
// bfcache geri dönüşleri ve çoklu-frame durumları kütüphanede çözülmüş
// durumda — elle yazılan gözlemci bu kenar durumlarda sessizce yanlış
// değer verir.
//
// `attribution` build'i sayının yanında SEBEBİ de verir: LCP'yi hangi
// elementin geciktirdiği, kaymayı hangi düğümün yaptığı. Teknisyen için
// asıl değerli olan bu.

(function () {
  if (window.__hc) return;

  window.__hc = {
    lcp: null, lcpHam: null, cls: null, fcp: null, ttfb: null,
    longTasks: [],
    konsolHatalari: [],
    hazir: false,
  };

  var H = window.__hc;

  // ── Core Web Vitals ────────────────────────────────────────────────────
  // reportAllChanges: sayfa kapanmadan da güncel değeri görebilelim
  try {
    webVitals.onLCP(function (m) {
      var a = m.attribution || {};
      H.lcp = {
        deger: m.value,
        element: a.target || null,
        url: a.url || null,
        // LCP'nin dört fazı — hangisinin baskın olduğu doğrudan çözümü söyler
        ttfb_ms: a.timeToFirstByte || 0,
        kaynak_gecikmesi_ms: a.resourceLoadDelay || 0,
        kaynak_suresi_ms: a.resourceLoadDuration || 0,
        render_gecikmesi_ms: a.elementRenderDelay || 0,
      };
    }, { reportAllChanges: true });

    webVitals.onCLS(function (m) {
      var a = m.attribution || {};
      H.cls = {
        deger: m.value,
        en_buyuk_element: a.largestShiftTarget || null,
        en_buyuk_deger: a.largestShiftValue || 0,
        yukleme_durumu: a.loadState || null,
      };
    }, { reportAllChanges: true });

    webVitals.onFCP(function (m) { H.fcp = { deger: m.value }; });

    webVitals.onTTFB(function (m) {
      var a = m.attribution || {};
      H.ttfb = {
        deger: m.value,
        bekleme_ms: a.waitingDuration || 0,
        dns_ms: a.dnsDuration || 0,
        baglanti_ms: a.connectionDuration || 0,
        istek_ms: a.requestDuration || 0,
      };
    });
  } catch (e) { /* kütüphane yüklenemediyse metrikler null kalır */ }

  // ── LCP yedeği (ham gözlemci) ──────────────────────────────────────────
  // web-vitals'ın onLCP'si sayfa gizlenene kadar rapor etmeyebilir ve bazı
  // sitelerde hiç tetiklenmiyor (ölçümde python.org'da gözlendi). Ham
  // gözlemci her adayı anında yazar; attribution'ı yoktur ama SAYIYI
  // kaybetmeyiz. Motor, web-vitals değeri yoksa buna düşer.
  try {
    new PerformanceObserver(function (list) {
      var es = list.getEntries();
      var son = es[es.length - 1];
      if (son) {
        H.lcpHam = {
          deger: son.renderTime || son.loadTime || son.startTime,
          element: son.element ? son.element.tagName.toLowerCase() : null,
          url: son.url || null,
        };
      }
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  } catch (e) { /* Chromium dışında yok */ }

  // ── TBT için uzun görevler ─────────────────────────────────────────────
  // Total Blocking Time = FCP sonrası 50 ms'yi aşan her görevin aşan kısmı.
  // web-vitals TBT vermez (saha metriği değil), bu yüzden elle topluyoruz.
  try {
    new PerformanceObserver(function (list) {
      list.getEntries().forEach(function (e) {
        H.longTasks.push({ baslangic: e.startTime, sure: e.duration });
      });
    }).observe({ type: 'longtask', buffered: true });
  } catch (e) { /* longtask yalnızca Chromium'da var */ }

  // ── Konsol hataları ────────────────────────────────────────────────────
  // Sayfanın kendi JS hataları — çoğu zaman yavaşlığın değil bozukluğun
  // işareti, ama teknisyen aynı ekranda görsün.
  window.addEventListener('error', function (ev) {
    if (H.konsolHatalari.length < 50) {
      H.konsolHatalari.push({
        mesaj: String(ev.message || ev.type || 'hata').slice(0, 300),
        kaynak: String(ev.filename || '').slice(0, 300),
        satir: ev.lineno || 0,
      });
    }
  }, true);

  window.addEventListener('unhandledrejection', function (ev) {
    if (H.konsolHatalari.length < 50) {
      H.konsolHatalari.push({
        mesaj: ('İşlenmemiş promise reddi: ' + String(ev.reason)).slice(0, 300),
        kaynak: '', satir: 0,
      });
    }
  });

  H.hazir = true;
})();
