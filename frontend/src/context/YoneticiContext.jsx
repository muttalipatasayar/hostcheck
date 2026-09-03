import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { yoneticiMi } from '../lib/adminAuth'

// Yönetici oturumu = TARAYICININ Nginx Basic Auth'a kimlik doğrulamış olması.
//
// Uygulamada kullanıcı tablosu, parola ya da oturum satırı YOKTUR; tek kimlik
// /etc/nginx/hostcheck.htpasswd içindeki `admin`. Bu context sadece "tarayıcı
// o kimliği taşıyor mu" sorusunun cevabını tutar.
//
// YETKİLENDİRME BURADA DEĞİL. Yazma uçlarını Nginx koruyor (`limit_except
// GET HEAD`); buradaki bayrak yalnızca kullanıcıya çalışmayacak düğme
// göstermemek için. Bayrağı elle `true` yapmak hiçbir kapı açmaz — istek yine
// 401 döner.
//
// Neden localStorage: tarayıcı Basic Auth kimliğini kendi saklıyor ama bunu
// JavaScript'e SÖYLEMİYOR. Sayfa yenilenince "bu kişi yönetici arayüzü
// istiyordu" bilgisini biz hatırlamazsak, ya herkese pencere açtırmamız ya da
// yöneticinin her yenilemede tekrar giriş yapması gerekirdi.

const YoneticiContext = createContext(null)
const ANAHTAR = 'hc_yonetici'

function bayragiOku() {
  try { return localStorage.getItem(ANAHTAR) === '1' } catch { return false }
}
function bayragiYaz(deger) {
  try {
    if (deger) localStorage.setItem(ANAHTAR, '1')
    else localStorage.removeItem(ANAHTAR)
  } catch { /* gizli sekme / depolama kapalı — bayrak yalnızca bu sayfa ömrü kadar yaşar */ }
}

export function YoneticiProvider({ children }) {
  // İyimser başlangıç: bayrak varsa arayüz yönetici modunda açılır ve doğrulama
  // arkada koşar. Aksi hâlde her yenilemede düğmeler bir an kaybolup geri
  // gelirdi.
  const [yonetici, setYonetici] = useState(bayragiOku)

  // Yalnızca daha önce giriş yapmış olan için sessiz doğrulama. Kimlik hâlâ
  // tarayıcının önbelleğindeyse pencere AÇILMAZ, 200 döner. Anonim ziyaretçi
  // bu isteği hiç atmaz.
  useEffect(() => {
    if (!bayragiOku()) return
    let iptal = false
    yoneticiMi().then(sonuc => {
      if (iptal) return
      setYonetici(sonuc)
      if (!sonuc) bayragiYaz(false)      // kimlik düşmüş; bayrağı taşıma
    })
    return () => { iptal = true }
  }, [])

  // Kullanıcı düğmeye bastığında: 401 → tarayıcı kendi penceresini açar,
  // kullanıcı adı/parola oraya girilir. Bizim bir giriş formumuz YOK; parola
  // hiçbir zaman uygulamanın eline geçmez, dolayısıyla saklanamaz da.
  const girisYap = useCallback(async () => {
    const sonuc = await yoneticiMi()
    setYonetici(sonuc)
    bayragiYaz(sonuc)
    return sonuc
  }, [])

  // DİKKAT: Bu yalnızca ARAYÜZÜ kapatır. Basic Auth kimliğini tarayıcı
  // saklıyor ve JavaScript onu silemez — kimlik tarayıcı kapanana kadar
  // gönderilmeye devam eder. Yani ortak kullanılan bir makinede "Çıkış"
  // yetmez, tarayıcının kapatılması gerekir. Düğmenin yanında bu yazıyor.
  const cikisYap = useCallback(() => {
    setYonetici(false)
    bayragiYaz(false)
  }, [])

  return (
    <YoneticiContext.Provider value={{ yonetici, girisYap, cikisYap }}>
      {children}
    </YoneticiContext.Provider>
  )
}

export function useYonetici() {
  const ctx = useContext(YoneticiContext)
  if (!ctx) throw new Error('useYonetici yalnızca YoneticiProvider altında kullanılabilir')
  return ctx
}
