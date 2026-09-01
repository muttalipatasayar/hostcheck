import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { oturumDustuKaydet } from '../lib/axiosKurulum'

// Üyelik durumu. Panelin geri kalanı kimlik doğrulamasız çalışmaya devam
// eder; bu bağlam yalnızca Hazır Yanıtlar ve Yönetim sekmelerini kapılar.

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [kullanici, setKullanici] = useState(null)
  const [yukleniyor, setYukleniyor] = useState(true)
  const [ayarlar, setAyarlar] = useState({ izinli_alanlar: [], parola_min: 10 })
  // StrictMode geliştirmede efektleri iki kez çalıştırıyor; ilk yoklamayı
  // tekrarlamamak için.
  const yoklandi = useRef(false)

  const yenile = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/uyelik/ben')
      setKullanici(data)
      return data
    } catch {
      setKullanici(null)
      return null
    } finally {
      setYukleniyor(false)
    }
  }, [])

  useEffect(() => {
    if (yoklandi.current) return
    yoklandi.current = true
    // Oturum sunucuda düştüğünde (süre doldu, hesap askıya alındı) arayüz
    // kendini toparlasın — axios interceptor'ı buraya haber veriyor.
    oturumDustuKaydet(() => setKullanici(null))
    yenile()
    axios.get('/api/uyelik/ayarlar')
      .then(({ data }) => setAyarlar(data))
      .catch(() => {})
  }, [yenile])

  const girisYap = useCallback(async (email, parola, beniHatirla) => {
    const { data } = await axios.post('/api/uyelik/giris', {
      email, parola, beni_hatirla: !!beniHatirla,
    })
    setKullanici(data)
    return data
  }, [])

  const kayitOl = useCallback(async (adSoyad, email, parola) => {
    const { data } = await axios.post('/api/uyelik/kayit', {
      ad_soyad: adSoyad, email, parola,
    })
    return data
  }, [])

  const cikisYap = useCallback(async () => {
    try {
      await axios.post('/api/uyelik/cikis')
    } finally {
      // Sunucu hata verse bile arayüz oturumu bırakmalı.
      setKullanici(null)
    }
  }, [])

  const deger = {
    kullanici,
    yukleniyor,
    ayarlar,
    girisli: !!kullanici,
    admin: kullanici?.rol === 'admin',
    girisYap,
    kayitOl,
    cikisYap,
    yenile,
    setKullanici,
  }

  return <AuthContext.Provider value={deger}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth yalnızca AuthProvider altında kullanılabilir')
  return ctx
}
