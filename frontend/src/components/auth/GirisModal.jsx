import { forwardRef, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, ArrowLeft, CheckCircle2, Eye, EyeOff, Loader2, Lock,
  Mail, ShieldCheck, User, X,
} from 'lucide-react'
import axios from 'axios'
import toast from 'react-hot-toast'
import { useAuth } from '../../context/AuthContext'
import { useHotkeys } from '../../hooks/useHotkeys'
import { apiHataMesaji } from '../../lib/apiHata'

// Giriş / üye ol / parola sıfırlama — tek modal, dört kip.
//
// Alan adı uyarısı SUNUCUYU BEKLEMEZ: kullanıcı @gmail.com yazdığı anda
// görünür. Sunucu tarafı yine de otoritedir (auth_core.alan_kontrol);
// buradaki kontrol yalnızca boşuna bir tur atmayı önler.

const KIP_BASLIK = {
  giris:   { baslik: 'Giriş Yap',        alt: 'Hazır Yanıtlar kütüphanesine erişmek için giriş yapın' },
  kayit:   { baslik: 'Üye Ol',           alt: 'Kurumsal e-posta adresinizle hesap oluşturun' },
  unuttum: { baslik: 'Parolamı Unuttum', alt: 'Sıfırlama bağlantısı e-posta adresinize gönderilir' },
  sifirla: { baslik: 'Yeni Parola',      alt: 'Hesabınız için yeni bir parola belirleyin' },
}

function alanAdi(eposta) {
  const i = (eposta || '').lastIndexOf('@')
  return i === -1 ? '' : eposta.slice(i + 1).trim().toLowerCase()
}

// forwardRef şart: açılışta ilk alana odaklanmak için ref geçiliyor ve düz bir
// fonksiyon bileşeni onu yutar.
const Alan = forwardRef(function Alan({ ikon: Ikon, ...props }, ref) {
  return (
    <div className="relative">
      <Ikon className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
        style={{ color: '#9da5be' }} />
      <input ref={ref} {...props} className="input-field"
        style={{ paddingLeft: 38, ...(props.style || {}) }} />
    </div>
  )
})

export default function GirisModal({ acilisKipi = 'giris', sifirlamaTokeni = '', onKapat }) {
  const { girisYap, kayitOl, ayarlar } = useAuth()
  const [kip, setKip] = useState(acilisKipi)
  const [adSoyad, setAdSoyad] = useState('')
  const [eposta, setEposta] = useState('')
  const [parola, setParola] = useState('')
  const [parolaGorunur, setParolaGorunur] = useState(false)
  const [beniHatirla, setBeniHatirla] = useState(false)
  const [gonderiliyor, setGonderiliyor] = useState(false)
  const [basari, setBasari] = useState(null)   // { baslik, metin }
  // Giriş "doğrulanmadı" diye reddedildiğinde beliren kurtarma yolu. Bu
  // olmadan kaydolup bağlantıya tıklamamış biri tamamen sıkışıyordu: giriş
  // 403, şifremi unuttum sessiz, yeni bağlantı isteme yolu yok.
  const [dogrulamaGerek, setDogrulamaGerek] = useState(false)
  const ilkAlanRef = useRef(null)

  // Modal açıkken Escape yalnızca modalı kapatsın (scope yığınının tepesi).
  // Bu çağrı olmasaydı Ctrl+K modalın üstünde komut paletini açardı.
  useHotkeys({
    escape: () => onKapat(),
    'ctrl+k': () => {},
    'ctrl+alt+k': () => {},
  })

  useEffect(() => { ilkAlanRef.current?.focus() }, [kip])

  const izinli = ayarlar.izinli_alanlar || []
  const izinliMetin = izinli.map(a => '@' + a).join(' ve ')

  const alanHatasi = useMemo(() => {
    const alan = alanAdi(eposta)
    if (!alan || !izinli.length) return ''
    // Yazım sürerken uyarma: "@na" henüz bir alan adı değil.
    if (izinli.some(a => a === alan || a.startsWith(alan))) return ''
    return `@${alan} uzantılı adresler kabul edilmiyor. Yalnızca ${izinliMetin} adresleriyle üye olunabilir.`
  }, [eposta, izinli, izinliMetin])

  const alanTam = izinli.includes(alanAdi(eposta))

  const gonderilebilir = (() => {
    if (gonderiliyor) return false
    if (kip === 'giris')   return eposta.trim() && parola
    if (kip === 'kayit')   return adSoyad.trim().length >= 2 && alanTam && parola.length >= (ayarlar.parola_min || 10)
    if (kip === 'unuttum') return !!eposta.trim()
    if (kip === 'sifirla') return parola.length >= (ayarlar.parola_min || 10)
    return false
  })()

  const kipDegistir = (yeni) => {
    setKip(yeni)
    setParola('')
    setBasari(null)
    setDogrulamaGerek(false)
  }

  const dogrulamaTekrarGonder = async () => {
    setGonderiliyor(true)
    try {
      const { data } = await axios.post('/api/uyelik/dogrulama-tekrar',
        { email: eposta.trim() })
      setDogrulamaGerek(false)
      setBasari({ baslik: 'Doğrulama bağlantısı yeniden gönderildi', metin: data.mesaj })
    } catch (err) {
      toast.error(apiHataMesaji(err, 'Bağlantı gönderilemedi'))
    } finally {
      setGonderiliyor(false)
    }
  }

  const gonder = async (e) => {
    e?.preventDefault()
    if (!gonderilebilir) return
    setGonderiliyor(true)
    try {
      if (kip === 'giris') {
        const k = await girisYap(eposta.trim(), parola, beniHatirla)
        toast.success(`Hoş geldiniz, ${k.ad_soyad}`)
        onKapat()
      } else if (kip === 'kayit') {
        const y = await kayitOl(adSoyad.trim(), eposta.trim(), parola)
        setBasari({ baslik: 'Doğrulama e-postası gönderildi', metin: y.mesaj })
      } else if (kip === 'unuttum') {
        const { data } = await axios.post('/api/uyelik/sifre-unuttum', { email: eposta.trim() })
        setBasari({ baslik: 'Bağlantı gönderildi', metin: data.mesaj })
      } else if (kip === 'sifirla') {
        const { data } = await axios.post('/api/uyelik/sifre-sifirla', {
          token: sifirlamaTokeni, yeni_parola: parola,
        })
        toast.success(data.mesaj)
        kipDegistir('giris')
      }
    } catch (err) {
      // 403 + "doğrulan…" = hesap var, parola doğru, ama e-posta doğrulanmamış.
      // Kullanıcıya çıkış yolunu göster.
      const detay = err?.response?.data?.detail || ''
      if (err?.response?.status === 403 && detay.toLocaleLowerCase('tr-TR').includes('doğrulan')) {
        setDogrulamaGerek(true)
      }
      toast.error(apiHataMesaji(err, 'İşlem tamamlanamadı'))
    } finally {
      setGonderiliyor(false)
    }
  }

  const meta = KIP_BASLIK[kip]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,6,30,0.4)', backdropFilter: 'blur(6px)' }}
      onClick={onKapat}>
      <div className="w-full max-w-md rounded-xl overflow-hidden animate-slide-up"
        style={{ background: '#ffffff', boxShadow: '0 24px 64px rgba(0,6,30,0.18)' }}
        onClick={e => e.stopPropagation()}
        role="dialog" aria-modal="true" aria-label={meta.baslik}>

        {/* Başlık */}
        <div className="px-6 pt-6 pb-4 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="w-9 h-9 rounded-btn flex items-center justify-center flex-shrink-0"
              style={{ background: 'linear-gradient(135deg, rgba(59,127,255,0.18) 0%, rgba(37,99,235,0.12) 100%)' }}>
              <ShieldCheck style={{ color: '#2563eb', width: 18, height: 18 }} />
            </div>
            <div className="min-w-0">
              <h2 className="text-title-lg font-semibold leading-snug" style={{ color: '#1a1d2e' }}>
                {meta.baslik}
              </h2>
              <p className="text-label-md mt-0.5" style={{ color: '#6b7388' }}>{meta.alt}</p>
            </div>
          </div>
          <button onClick={onKapat} aria-label="Kapat"
            className="p-1.5 rounded-btn flex-shrink-0 hover:opacity-70"
            style={{ color: '#9da5be', background: 'rgba(0,6,30,0.05)' }}>
            <X className="w-4 h-4" />
          </button>
        </div>

        {basari ? (
          <div className="px-6 pb-6">
            <div className="rounded-card px-4 py-4 flex items-start gap-3"
              style={{ background: 'rgba(34,197,94,0.07)', border: '1px solid rgba(34,197,94,0.18)' }}>
              <CheckCircle2 className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: '#16a34a' }} />
              <div className="min-w-0">
                <p className="text-body-sm font-semibold mb-1" style={{ color: '#15803d' }}>{basari.baslik}</p>
                <p className="text-body-sm leading-relaxed" style={{ color: '#4a5068' }}>{basari.metin}</p>
              </div>
            </div>
            <button onClick={() => kipDegistir('giris')} className="btn-primary w-full justify-center mt-4">
              Giriş ekranına dön
            </button>
          </div>
        ) : (
          <form onSubmit={gonder}>
            {/* Sekmeler — yalnızca giriş/kayıt arasında */}
            {(kip === 'giris' || kip === 'kayit') && (
              <div className="px-6 pb-4">
                <div className="flex p-1 rounded-btn" style={{ background: '#f0f2f8' }}>
                  {[['giris', 'Giriş Yap'], ['kayit', 'Üye Ol']].map(([id, etiket]) => (
                    <button key={id} type="button" onClick={() => kipDegistir(id)}
                      className="flex-1 py-2 rounded text-body-sm font-medium transition-all duration-150"
                      style={kip === id
                        ? { background: '#ffffff', color: '#2563eb', boxShadow: '0 1px 3px rgba(0,6,30,0.10)' }
                        : { color: '#6b7388' }}>
                      {etiket}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="px-6 pb-2 flex flex-col gap-3">
              {kip === 'kayit' && (
                <div>
                  <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>
                    Ad Soyad
                  </label>
                  <Alan ikon={User} ref={ilkAlanRef} type="text" value={adSoyad} autoComplete="name"
                    onChange={e => setAdSoyad(e.target.value)} placeholder="Adınız Soyadınız" maxLength={120} />
                </div>
              )}

              {kip !== 'sifirla' && (
                <div>
                  <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>
                    Kurumsal E-posta
                  </label>
                  <Alan ikon={Mail} ref={kip === 'kayit' ? undefined : ilkAlanRef}
                    type="email" value={eposta} autoComplete="email"
                    onChange={e => setEposta(e.target.value)}
                    placeholder={izinli.length ? `adiniz@${izinli[0]}` : 'adiniz@sirket.com'}
                    maxLength={254}
                    style={alanHatasi ? { borderColor: 'rgba(239,68,68,0.45)', background: 'rgba(239,68,68,0.04)' } : undefined} />
                  {alanHatasi ? (
                    <p className="mt-1.5 flex items-start gap-1.5 text-label-md leading-relaxed"
                      style={{ color: '#dc2626' }}>
                      <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                      <span>{alanHatasi}</span>
                    </p>
                  ) : kip === 'kayit' && izinli.length > 0 && (
                    <p className="mt-1.5 text-label-md" style={{ color: '#9da5be' }}>
                      Yalnızca {izinliMetin} adresleri kabul edilir.
                    </p>
                  )}
                </div>
              )}

              {kip !== 'unuttum' && (
                <div>
                  <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>
                    {kip === 'sifirla' ? 'Yeni Parola' : 'Parola'}
                  </label>
                  <div className="relative">
                    <Alan ikon={Lock} ref={kip === 'sifirla' ? ilkAlanRef : undefined}
                      type={parolaGorunur ? 'text' : 'password'} value={parola}
                      autoComplete={kip === 'giris' ? 'current-password' : 'new-password'}
                      onChange={e => setParola(e.target.value)}
                      placeholder={kip === 'giris' ? 'Parolanız' : `En az ${ayarlar.parola_min || 10} karakter`}
                      maxLength={200} style={{ paddingRight: 40 }} />
                    <button type="button" onClick={() => setParolaGorunur(v => !v)}
                      aria-label={parolaGorunur ? 'Parolayı gizle' : 'Parolayı göster'}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded hover:opacity-70"
                      style={{ color: '#9da5be' }}>
                      {parolaGorunur ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  {(kip === 'kayit' || kip === 'sifirla') && (
                    <p className="mt-1.5 text-label-md" style={{ color: '#9da5be' }}>
                      En az {ayarlar.parola_min || 10} karakter, bir harf ve bir rakam içermeli.
                    </p>
                  )}
                </div>
              )}

              {dogrulamaGerek && (
                <div className="rounded-card px-3.5 py-3 flex items-start gap-2.5"
                  style={{ background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.22)' }}>
                  <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: '#d97706' }} />
                  <div className="min-w-0">
                    <p className="text-body-sm font-medium mb-1" style={{ color: '#b45309' }}>
                      E-posta adresiniz henüz doğrulanmadı
                    </p>
                    <p className="text-label-md leading-relaxed mb-2" style={{ color: '#6b7388' }}>
                      Gelen kutunuzdaki bağlantıya tıklamanız gerekiyor. Bağlantı
                      elinizde yoksa yenisini isteyin.
                    </p>
                    <button type="button" onClick={dogrulamaTekrarGonder} disabled={gonderiliyor}
                      className="btn-secondary text-label-md py-1.5 px-3">
                      {gonderiliyor && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                      Yeni doğrulama bağlantısı gönder
                    </button>
                  </div>
                </div>
              )}

              {kip === 'giris' && (
                <div className="flex items-center justify-between pt-0.5">
                  <label className="flex items-center gap-2 cursor-pointer select-none">
                    <input type="checkbox" checked={beniHatirla}
                      onChange={e => setBeniHatirla(e.target.checked)}
                      style={{ accentColor: '#2563eb', width: 15, height: 15 }} />
                    <span className="text-body-sm" style={{ color: '#6b7388' }}>Beni hatırla</span>
                  </label>
                  <button type="button" onClick={() => kipDegistir('unuttum')}
                    className="text-body-sm hover:underline" style={{ color: '#2563eb' }}>
                    Şifremi unuttum
                  </button>
                </div>
              )}
            </div>

            <div className="px-6 py-4 mt-2 flex flex-col gap-2"
              style={{ borderTop: '1px solid rgba(0,6,30,0.08)', background: '#f8f9fc' }}>
              <button type="submit" disabled={!gonderilebilir}
                className="btn-primary w-full justify-center">
                {gonderiliyor && <Loader2 className="w-4 h-4 animate-spin" />}
                {kip === 'giris' ? 'Giriş Yap'
                  : kip === 'kayit' ? 'Üyeliği Başlat'
                  : kip === 'unuttum' ? 'Sıfırlama Bağlantısı Gönder'
                  : 'Parolayı Güncelle'}
              </button>
              {(kip === 'unuttum' || kip === 'sifirla') && (
                <button type="button" onClick={() => kipDegistir('giris')}
                  className="btn-ghost w-full justify-center text-label-md">
                  <ArrowLeft className="w-3.5 h-3.5" /> Giriş ekranına dön
                </button>
              )}
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
