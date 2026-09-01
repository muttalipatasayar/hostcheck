import { useEffect, useRef, useState } from 'react'
import axios from 'axios'

// Backend'in gerçekten ayakta olup olmadığını yoklar.
//
// Kenar çubuğundaki gösterge daha önce SABİT metindi: backend çökmüş olsa bile
// "Sistem Sağlıklı" yazıyor ve yeşil nokta yanıp sönüyordu. Teşhis panelinde
// yanlış bir sağlık göstergesi, teşhis edilen sorunun kendisi olabilir —
// teknisyen "API çalışıyor" görüp hatayı müşterinin sitesinde arar.
//
// Yoklama aralığı bilinçli olarak seyrek (20 sn): /api/health rate limit'siz
// ama bedava değil ve panel tek worker üstünde dönüyor.
const ARALIK_MS = 20000
const ZAMAN_ASIMI_MS = 6000

export function useApiHealth() {
  const [durum, setDurum] = useState('bilinmiyor')   // bilinmiyor | saglikli | kopuk
  const [gecikmeMs, setGecikmeMs] = useState(null)
  const canliRef = useRef(true)

  useEffect(() => {
    canliRef.current = true

    const yokla = async () => {
      const t0 = performance.now()
      try {
        const r = await axios.get('/api/health', { timeout: ZAMAN_ASIMI_MS })
        if (!canliRef.current) return
        setDurum(r.data?.status === 'ok' ? 'saglikli' : 'kopuk')
        setGecikmeMs(Math.round(performance.now() - t0))
      } catch {
        if (!canliRef.current) return
        setDurum('kopuk')
        setGecikmeMs(null)
      }
    }

    yokla()
    const t = setInterval(yokla, ARALIK_MS)

    // Sekme arka plandayken yoklamayı sürdürmenin anlamı yok; öne gelince
    // beklemeden tazele — teknisyen sekmeye döndüğünde güncel durumu görsün.
    const gorunurluk = () => { if (document.visibilityState === 'visible') yokla() }
    document.addEventListener('visibilitychange', gorunurluk)

    return () => {
      canliRef.current = false
      clearInterval(t)
      document.removeEventListener('visibilitychange', gorunurluk)
    }
  }, [])

  return { durum, gecikmeMs }
}
