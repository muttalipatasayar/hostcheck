import axios from 'axios'

// Global axios ayarı — main.jsx'ten BİR KEZ çağrılır.
//
// Neden burada ve neden global: panelin 14 aracı `axios.get('/api/...')`
// biçiminde çıplak axios kullanıyor (CLAUDE.md'de yazılı konvansiyon). Ayrı
// bir API istemcisine geçmek hepsini dokunmayı gerektirirdi; oysa üyelik
// için gereken iki şey (çerez taşıma + CSRF başlığı) global varsayılanlarla
// çözülebiliyor.
//
// Fonksiyon olarak export ediliyor ve çağrılıyor: yalnızca yan etkili bir
// `import './lib/axiosKurulum'` satırını Rollup ölü kod sayıp eleyebilirdi.

// Üretimde çerez adı `__Host-` önekli (kardeş subdomain'in çerez gölgelemesine
// karşı); geliştirmede http üzerinde `__Host-` yazılamadığı için öneksiz.
const CSRF_ADLARI = ['__Host-hc_csrf', 'hc_csrf']

export function csrfJetonu() {
  for (const ad of CSRF_ADLARI) {
    const eslesme = document.cookie.match(
      new RegExp('(?:^|;\\s*)' + ad.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&') + '=([^;]*)')
    )
    if (eslesme) return decodeURIComponent(eslesme[1])
  }
  return ''
}

const GUVENLI_METOTLAR = ['get', 'head', 'options']

let oturumDustuCagrisi = null

/** AuthContext, oturum sunucu tarafında düştüğünde haberdar olmak için kaydolur. */
export function oturumDustuKaydet(fn) {
  oturumDustuCagrisi = fn
}

export function axiosKur() {
  // Çerezler aynı origin'de zaten gider; `withCredentials` geliştirmede
  // Vite proxy'si üzerinden de gitmesini garantiler.
  axios.defaults.withCredentials = true

  axios.interceptors.request.use((istek) => {
    const metot = (istek.method || 'get').toLowerCase()
    if (!GUVENLI_METOTLAR.includes(metot)) {
      const jeton = csrfJetonu()
      if (jeton) istek.headers['X-CSRF-Token'] = jeton
    }
    return istek
  })

  axios.interceptors.response.use(
    (yanit) => yanit,
    (hata) => {
      // 401 = oturum sunucuda yok (süresi doldu, çıkış yapıldı, hesap askıya
      // alındı). Arayüz hâlâ "giriş yapılmış" görünmesin.
      //
      // Yalnızca üyelik gerektiren uçlarda tetiklenir: /api/ssh, /api/rdp,
      // /api/ftp ve /api/admin Nginx Basic Auth ile korunuyor ve oradan gelen
      // 401 üyelikle ilgisizdir — onu da oturum düşmesi sayarsak teknisyen
      // Basic Auth penceresini iptal ettiğinde panelden atılırdı.
      const yol = hata?.config?.url || ''
      const uyelikUcu = /^\/api\/(uyelik|yonetim|hazir-yanitlar)/.test(yol)
      if (hata?.response?.status === 401 && uyelikUcu && oturumDustuCagrisi) {
        oturumDustuCagrisi()
      }
      return Promise.reject(hata)
    }
  )
}
