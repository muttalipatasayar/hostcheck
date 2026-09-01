// Backend hatalarını teknisyenin okuyacağı Türkçe mesaja çevirir.
//
// Neden ortak bir yardımcı: FastAPI `HTTPException` gövdeyi {"detail": "..."}
// olarak döndürür, ama slowapi'nin rate limit yanıtı {"error": "Rate limit
// exceeded: 5 per 1 minute"} biçimindedir — farklı ALAN adı. Tüm bileşenler
// yalnızca `detail` okuduğu için 429 yediklerinde mesaj `undefined` oluyor ve
// kullanıcı "backend çalışıyor mu?" gibi alakasız bir yedek metin görüyordu.
// Teknisyen gerçekte kotayı doldurmuşken bağlantı sorunu arıyordu.

export function apiHataMesaji(err, yedek = 'İşlem tamamlanamadı') {
  // Ağ / zaman aşımı — yanıt hiç gelmemiş
  if (err?.code === 'ECONNABORTED') return 'İstek zaman aşımına uğradı.'
  if (!err?.response) return 'Sunucuya ulaşılamadı — backend çalışıyor mu?'

  const { status, data } = err.response

  if (status === 429) {
    const ham = typeof data?.error === 'string' ? data.error : ''
    const m = ham.match(/(\d+)\s*per\s*(\d+)?\s*(second|minute|hour)/i)
    if (m) {
      // Ek yerine tam biçim: "dakika"+"de" ünlü uyumunu bozup "dakikade" veriyordu
      const birim = { second: 'saniyede', minute: 'dakikada', hour: 'saatte' }[m[3].toLowerCase()]
      return `Hız sınırına takıldınız (${birim} ${m[1]} istek). Biraz bekleyip tekrar deneyin.`
    }
    return 'Çok sık istek gönderildi. Biraz bekleyip tekrar deneyin.'
  }

  // FastAPI'nin doğrulama hatası: detail bir liste olabilir
  const d = data?.detail
  if (typeof d === 'string' && d.trim()) return d
  if (Array.isArray(d) && d.length) {
    const ilk = d[0]
    if (typeof ilk?.msg === 'string') return ilk.msg
  }
  if (typeof data?.error === 'string' && data.error.trim()) return data.error

  if (status === 401 || status === 403) return 'Yetki gerekiyor — oturum bilgileriniz kabul edilmedi.'
  if (status === 404) return 'İstenen kayıt bulunamadı.'
  if (status >= 500) return `Sunucu hatası (${status}). Kayıtlara bakılması gerekiyor.`
  return yedek
}
