import { useEffect, useRef, useState } from 'react'
import { ChevronUp, LogIn, LogOut, ShieldCheck, User, UserPlus } from 'lucide-react'
import toast from 'react-hot-toast'
import { useAuth } from '../../context/AuthContext'

// Kenar çubuğunun alt bloğu. Eskiden sabit "Destek Uzmanı / Aktif oturum"
// yazıyordu — backend'de oturum diye bir şey yokken bile.

function basHarfler(ad) {
  return (ad || '?')
    .split(/\s+/).filter(Boolean).slice(0, 2)
    .map(p => p[0].toLocaleUpperCase('tr-TR')).join('')
}

export default function UyeMenu({ onGiris, onKayit, onProfil }) {
  const { kullanici, girisli, admin, yukleniyor, cikisYap } = useAuth()
  const [acik, setAcik] = useState(false)
  const kutuRef = useRef(null)

  useEffect(() => {
    if (!acik) return
    const disariTikla = (e) => {
      if (kutuRef.current && !kutuRef.current.contains(e.target)) setAcik(false)
    }
    document.addEventListener('mousedown', disariTikla)
    return () => document.removeEventListener('mousedown', disariTikla)
  }, [acik])

  if (yukleniyor) {
    return (
      <div className="px-3 flex items-center gap-2">
        <div className="w-7 h-7 rounded-full animate-pulse" style={{ background: '#eef0f6' }} />
        <div className="flex-1">
          <div className="h-3 rounded w-24 mb-1.5 animate-pulse" style={{ background: '#eef0f6' }} />
          <div className="h-2.5 rounded w-16 animate-pulse" style={{ background: '#f4f5fb' }} />
        </div>
      </div>
    )
  }

  if (!girisli) {
    return (
      <div className="px-2 flex flex-col gap-1.5">
        <button onClick={onGiris}
          className="w-full flex items-center justify-center gap-2 py-2 rounded-btn text-body-sm font-medium transition-all duration-150"
          style={{ background: 'linear-gradient(135deg, #4d8eff 0%, #2563eb 100%)', color: '#ffffff' }}>
          <LogIn className="w-3.5 h-3.5" /> Giriş Yap
        </button>
        <button onClick={onKayit}
          className="w-full flex items-center justify-center gap-2 py-1.5 rounded-btn text-label-md transition-colors"
          style={{ color: '#6b7388' }}>
          <UserPlus className="w-3.5 h-3.5" /> Üye Ol
        </button>
      </div>
    )
  }

  const cikis = async () => {
    setAcik(false)
    await cikisYap()
    toast.success('Çıkış yapıldı')
  }

  return (
    <div className="relative px-1" ref={kutuRef}>
      {acik && (
        <div className="absolute bottom-full left-1 right-1 mb-2 rounded-card overflow-hidden py-1 z-50"
          style={{ background: '#ffffff', boxShadow: '0 8px 32px rgba(0,6,30,0.14)',
                   border: '1px solid rgba(0,6,30,0.08)' }}>
          <div className="px-3 py-2" style={{ borderBottom: '1px solid rgba(0,6,30,0.06)' }}>
            <p className="text-label-sm truncate" style={{ color: '#9da5be' }}>{kullanici.email}</p>
          </div>
          <button onClick={() => { setAcik(false); onProfil() }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-body-sm text-left transition-colors hover:opacity-70"
            style={{ color: '#4a5068' }}>
            <User className="w-3.5 h-3.5" /> Profil ve parola
          </button>
          <button onClick={cikis}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-body-sm text-left transition-colors hover:opacity-70"
            style={{ color: '#dc2626' }}>
            <LogOut className="w-3.5 h-3.5" /> Çıkış yap
          </button>
        </div>
      )}

      <button onClick={() => setAcik(v => !v)}
        className="w-full flex items-center gap-2 px-2 py-1.5 rounded-btn transition-colors text-left"
        style={{ background: acik ? 'rgba(0,6,30,0.04)' : 'transparent' }}>
        <div className="w-7 h-7 rounded-full flex items-center justify-center text-label-sm font-semibold flex-shrink-0"
          style={admin
            ? { background: 'rgba(37,99,235,0.14)', color: '#2563eb' }
            : { background: 'rgba(59,127,255,0.12)', color: '#3b7eff' }}>
          {basHarfler(kullanici.ad_soyad)}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-body-sm font-medium truncate" style={{ color: '#1a1d2e' }}>
            {kullanici.ad_soyad}
          </p>
          <p className="text-label-sm truncate flex items-center gap-1" style={{ color: '#6b7388' }}>
            {admin && <ShieldCheck className="w-3 h-3 flex-shrink-0" style={{ color: '#2563eb' }} />}
            {admin ? 'Yönetici' : 'Üye'}
          </p>
        </div>
        <ChevronUp className="w-3.5 h-3.5 flex-shrink-0 transition-transform"
          style={{ color: '#9da5be', transform: acik ? 'rotate(0deg)' : 'rotate(180deg)' }} />
      </button>
    </div>
  )
}
