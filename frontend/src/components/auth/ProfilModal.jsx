import { useEffect, useState } from 'react'
import { Loader2, LogOut, Monitor, Save, ShieldCheck, User, X } from 'lucide-react'
import axios from 'axios'
import toast from 'react-hot-toast'
import { useAuth } from '../../context/AuthContext'
import { useHotkeys } from '../../hooks/useHotkeys'
import { apiHataMesaji } from '../../lib/apiHata'

const SEKMELER = [
  { id: 'profil',    etiket: 'Profil',    ikon: User },
  { id: 'parola',    etiket: 'Parola',    ikon: ShieldCheck },
  { id: 'oturumlar', etiket: 'Oturumlar', ikon: Monitor },
]

function tarih(iso) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleString('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }) }
  catch { return iso }
}

export default function ProfilModal({ onKapat }) {
  const { kullanici, admin, setKullanici } = useAuth()
  const [sekme, setSekme] = useState('profil')
  const [adSoyad, setAdSoyad] = useState(kullanici?.ad_soyad || '')
  const [mevcut, setMevcut] = useState('')
  const [yeni, setYeni] = useState('')
  const [mesgul, setMesgul] = useState(false)
  const [oturumlar, setOturumlar] = useState(null)

  useHotkeys({ escape: () => onKapat(), 'ctrl+k': () => {} })

  useEffect(() => {
    if (sekme !== 'oturumlar' || oturumlar) return
    axios.get('/api/uyelik/oturumlarim')
      .then(({ data }) => setOturumlar(data))
      .catch(err => toast.error(apiHataMesaji(err, 'Oturumlar alınamadı')))
  }, [sekme, oturumlar])

  const profilKaydet = async () => {
    setMesgul(true)
    try {
      const { data } = await axios.patch('/api/uyelik/profil', { ad_soyad: adSoyad.trim() })
      setKullanici(data)
      toast.success('Profil güncellendi')
    } catch (err) { toast.error(apiHataMesaji(err, 'Profil güncellenemedi')) }
    finally { setMesgul(false) }
  }

  const parolaDegistir = async () => {
    setMesgul(true)
    try {
      const { data } = await axios.post('/api/uyelik/sifre-degistir',
        { mevcut_parola: mevcut, yeni_parola: yeni })
      toast.success(data.mesaj)
      setMevcut(''); setYeni(''); setOturumlar(null)
    } catch (err) { toast.error(apiHataMesaji(err, 'Parola değiştirilemedi')) }
    finally { setMesgul(false) }
  }

  const digerleriniKapat = async () => {
    setMesgul(true)
    try {
      const { data } = await axios.post('/api/uyelik/oturumlarimi-kapat')
      toast.success(data.mesaj)
      setOturumlar(null)
    } catch (err) { toast.error(apiHataMesaji(err, 'Oturumlar kapatılamadı')) }
    finally { setMesgul(false) }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,6,30,0.4)', backdropFilter: 'blur(6px)' }}
      onClick={onKapat}>
      <div className="w-full max-w-lg rounded-xl overflow-hidden animate-slide-up"
        style={{ background: '#ffffff', boxShadow: '0 24px 64px rgba(0,6,30,0.18)' }}
        onClick={e => e.stopPropagation()} role="dialog" aria-modal="true">

        <div className="px-6 py-5 flex items-start justify-between gap-3"
          style={{ borderBottom: '1px solid rgba(0,6,30,0.08)' }}>
          <div className="min-w-0">
            <h2 className="text-title-lg font-semibold" style={{ color: '#1a1d2e' }}>Hesabım</h2>
            <p className="text-label-md mt-0.5 flex items-center gap-1.5 truncate" style={{ color: '#6b7388' }}>
              {kullanici?.email}
              <span className="badge" style={admin
                ? { background: 'rgba(37,99,235,0.1)', color: '#2563eb' }
                : { background: 'rgba(0,6,30,0.05)', color: '#6b7388' }}>
                {admin ? 'Yönetici' : 'Üye'}
              </span>
            </p>
          </div>
          <button onClick={onKapat} aria-label="Kapat" className="p-1.5 rounded-btn hover:opacity-70"
            style={{ color: '#9da5be', background: 'rgba(0,6,30,0.05)' }}>
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 pt-4">
          <div className="flex p-1 rounded-btn" style={{ background: '#f0f2f8' }}>
            {SEKMELER.map(({ id, etiket, ikon: Ikon }) => (
              <button key={id} onClick={() => setSekme(id)}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded text-body-sm font-medium transition-all duration-150"
                style={sekme === id
                  ? { background: '#ffffff', color: '#2563eb', boxShadow: '0 1px 3px rgba(0,6,30,0.10)' }
                  : { color: '#6b7388' }}>
                <Ikon className="w-3.5 h-3.5" /> {etiket}
              </button>
            ))}
          </div>
        </div>

        <div className="px-6 py-5 flex flex-col gap-4" style={{ minHeight: 210 }}>
          {sekme === 'profil' && (
            <>
              <div>
                <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>Ad Soyad</label>
                <input type="text" className="input-field" value={adSoyad} maxLength={120}
                  onChange={e => setAdSoyad(e.target.value)} />
              </div>
              <div>
                <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>E-posta</label>
                <input type="text" className="input-field" value={kullanici?.email || ''} disabled
                  style={{ color: '#9da5be', cursor: 'not-allowed' }} />
                <p className="mt-1.5 text-label-md" style={{ color: '#9da5be' }}>
                  E-posta adresi değiştirilemez — hesabın kimliği bu adrestir.
                </p>
              </div>
              <button onClick={profilKaydet} disabled={mesgul || adSoyad.trim().length < 2}
                className="btn-primary self-start">
                {mesgul ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Kaydet
              </button>
            </>
          )}

          {sekme === 'parola' && (
            <>
              <div>
                <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>Mevcut Parola</label>
                <input type="password" className="input-field" value={mevcut} autoComplete="current-password"
                  onChange={e => setMevcut(e.target.value)} />
              </div>
              <div>
                <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>Yeni Parola</label>
                <input type="password" className="input-field" value={yeni} autoComplete="new-password"
                  onChange={e => setYeni(e.target.value)} placeholder="En az 10 karakter" />
              </div>
              <p className="text-label-md" style={{ color: '#9da5be' }}>
                Parola değişince diğer cihazlardaki oturumlarınız kapatılır.
              </p>
              <button onClick={parolaDegistir} disabled={mesgul || !mevcut || yeni.length < 10}
                className="btn-primary self-start">
                {mesgul ? <Loader2 className="w-4 h-4 animate-spin" /> : <ShieldCheck className="w-4 h-4" />}
                Parolayı Değiştir
              </button>
            </>
          )}

          {sekme === 'oturumlar' && (
            oturumlar === null ? (
              <div className="flex items-center gap-2 text-body-sm" style={{ color: '#6b7388' }}>
                <Loader2 className="w-4 h-4 animate-spin" /> Oturumlar yükleniyor…
              </div>
            ) : (
              <>
                <div className="flex flex-col gap-2 max-h-56 overflow-y-auto">
                  {oturumlar.map(o => (
                    <div key={o.id} className="rounded-card px-3 py-2.5 flex items-start gap-3"
                      style={{ background: o.bu_oturum ? 'rgba(37,99,235,0.05)' : '#f8f9fc',
                               border: `1px solid ${o.bu_oturum ? 'rgba(37,99,235,0.18)' : 'rgba(0,6,30,0.06)'}` }}>
                      <Monitor className="w-4 h-4 flex-shrink-0 mt-0.5"
                        style={{ color: o.bu_oturum ? '#2563eb' : '#9da5be' }} />
                      <div className="min-w-0 flex-1">
                        <p className="text-body-sm font-medium truncate" style={{ color: '#1a1d2e' }}>
                          {o.ip || 'bilinmiyor'}
                          {o.bu_oturum && <span className="badge ml-2"
                            style={{ background: 'rgba(37,99,235,0.1)', color: '#2563eb' }}>bu cihaz</span>}
                        </p>
                        <p className="text-label-sm truncate" style={{ color: '#9da5be' }}>{o.user_agent || '—'}</p>
                        <p className="text-label-sm" style={{ color: '#9da5be' }}>{tarih(o.created_at)}</p>
                      </div>
                    </div>
                  ))}
                </div>
                {oturumlar.length > 1 && (
                  <button onClick={digerleriniKapat} disabled={mesgul} className="btn-secondary self-start">
                    <LogOut className="w-4 h-4" /> Diğer oturumları kapat
                  </button>
                )}
              </>
            )
          )}
        </div>
      </div>
    </div>
  )
}
