import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, AlertTriangle, BarChart3, ChevronLeft, ChevronRight,
  Clock, Loader2, Lock, LogOut, MessageSquare, Pencil, Plus, RefreshCw,
  Save, Search, Shield, ShieldCheck, Star, Trash2, UserCheck, UserX, Users, X,
} from 'lucide-react'
import axios from 'axios'
import toast from 'react-hot-toast'
import { useAuth } from '../context/AuthContext'
import { useHotkeys } from '../hooks/useHotkeys'
import { apiHataMesaji } from '../lib/apiHata'

// Yönetim paneli — dört sekme. Düzen Hazır Yanıtlar'ın iskeletini izler
// (w-56 yan menü + içerik) ki panel içinde yabancı durmasın.

const SEKMELER = [
  { id: 'istatistik', etiket: 'İstatistikler',  ikon: BarChart3,     renk: '#3b7eff' },
  { id: 'kullanici',  etiket: 'Kullanıcılar',   ikon: Users,         renk: '#22c55e' },
  { id: 'yanit',      etiket: 'Hazır Yanıtlar', ikon: MessageSquare, renk: '#f59e0b' },
  { id: 'denetim',    etiket: 'Denetim Kaydı',  ikon: Activity,      renk: '#a855f7' },
]

// Denetim eylemlerinin okunur karşılıkları. Ham anahtar (`yanit_ekle`) tabloda
// teknisyene bir şey anlatmıyor.
const EYLEM_ADI = {
  kayit: 'Kayıt oldu', kayit_tekrar: 'Tekrar kayıt denedi', dogrulama: 'E-postasını doğruladı',
  giris: 'Giriş yaptı', giris_basarisiz: 'Hatalı giriş', giris_kilitli: 'Kilitliyken denedi',
  giris_askida: 'Askıdayken denedi', cikis: 'Çıkış yaptı',
  sifre_sifirlama_istek: 'Parola sıfırlama istedi', sifre_sifirlandi: 'Parolasını sıfırladı',
  sifre_degistirildi: 'Parolasını değiştirdi', profil_guncelle: 'Profilini güncelledi',
  oturumlar_kapatildi: 'Oturumlarını kapattı', oturum_kapat_yonetici: 'Oturumları kapatıldı (yönetici)',
  yanit_ekle: 'Yanıt ekledi', yanit_guncelle: 'Yanıt güncelledi', yanit_sil: 'Yanıt sildi',
  kategori_ekle: 'Kategori ekledi', kategori_sil: 'Kategori sildi',
  kullanici_guncelle: 'Kullanıcıyı güncelledi', kullanici_sil: 'Kullanıcıyı sildi',
}

const EYLEM_RENGI = (e) =>
  e.startsWith('giris_') ? '#dc2626'
  : e.includes('sil') ? '#dc2626'
  : e.startsWith('yanit') || e.startsWith('kategori') ? '#d97706'
  : e === 'giris' || e === 'kayit' || e === 'dogrulama' ? '#16a34a'
  : '#6b7388'

function tarih(iso, kisa = false) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('tr-TR',
      kisa ? { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }
           : { dateStyle: 'medium', timeStyle: 'short' })
  } catch { return iso }
}

// ─── Ortak parçalar ──────────────────────────────────────────────────────────

function Kart({ etiket, deger, ikon: Ikon, renk, alt }) {
  return (
    <div className="rounded-card px-4 py-4" style={{ background: '#ffffff', border: '1px solid rgba(0,6,30,0.07)' }}>
      <div className="flex items-center justify-between mb-2.5">
        <p className="text-label-md font-medium" style={{ color: '#6b7388' }}>{etiket}</p>
        <Ikon className="w-4 h-4 flex-shrink-0" style={{ color: renk }} />
      </div>
      <p className="font-semibold tabular-nums" style={{ fontSize: 26, color: '#1a1d2e', lineHeight: 1.1 }}>
        {deger}
      </p>
      {alt && <p className="text-label-md mt-1" style={{ color: '#9da5be' }}>{alt}</p>}
    </div>
  )
}

function Bos({ ikon: Ikon, baslik, metin }) {
  return (
    <div className="flex flex-col items-center justify-center py-16">
      <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
        style={{ background: 'rgba(0,6,30,0.04)' }}>
        <Ikon className="w-6 h-6 opacity-25" style={{ color: '#1a1d2e' }} />
      </div>
      <p className="text-title-md font-medium mb-1" style={{ color: '#1a1d2e' }}>{baslik}</p>
      <p className="text-body-md" style={{ color: '#6b7388' }}>{metin}</p>
    </div>
  )
}

function Yukleniyor({ satir = 5 }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: satir }, (_, i) => (
        <div key={i} className="rounded-card px-4 py-3.5 animate-pulse flex items-center gap-4"
          style={{ background: '#ffffff' }}>
          <div className="w-8 h-8 rounded-full" style={{ background: '#f2f4fa' }} />
          <div className="flex-1 flex flex-col gap-1.5">
            <div className="h-3 rounded w-40" style={{ background: '#f2f4fa' }} />
            <div className="h-2.5 rounded w-56" style={{ background: '#f4f5fb' }} />
          </div>
        </div>
      ))}
    </div>
  )
}

function Sayfalayici({ sayfa, limit, toplam, onDegis }) {
  const sonSayfa = Math.max(1, Math.ceil(toplam / limit))
  if (sonSayfa <= 1) return null
  return (
    <div className="flex items-center justify-between pt-4">
      <p className="text-label-md" style={{ color: '#9da5be' }}>
        {toplam} kayıt · sayfa {sayfa}/{sonSayfa}
      </p>
      <div className="flex items-center gap-1">
        <button onClick={() => onDegis(sayfa - 1)} disabled={sayfa <= 1}
          className="p-1.5 rounded-btn disabled:opacity-30" style={{ color: '#6b7388' }}
          aria-label="Önceki sayfa">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <button onClick={() => onDegis(sayfa + 1)} disabled={sayfa >= sonSayfa}
          className="p-1.5 rounded-btn disabled:opacity-30" style={{ color: '#6b7388' }}
          aria-label="Sonraki sayfa">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

// ─── Sekme: İstatistikler ────────────────────────────────────────────────────

function Istatistikler() {
  const [veri, setVeri] = useState(null)
  const [yukleniyor, setYukleniyor] = useState(true)

  const yukle = useCallback(async () => {
    setYukleniyor(true)
    try {
      const { data } = await axios.get('/api/yonetim/istatistik')
      setVeri(data)
    } catch (err) { toast.error(apiHataMesaji(err, 'İstatistikler alınamadı')) }
    finally { setYukleniyor(false) }
  }, [])

  useEffect(() => { yukle() }, [yukle])

  if (yukleniyor) return <Yukleniyor satir={3} />
  if (!veri) return <Bos ikon={BarChart3} baslik="Veri alınamadı" metin="Yenilemeyi deneyin" />

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Kart etiket="Toplam üye" deger={veri.toplam_uye} ikon={Users} renk="#3b7eff"
          alt={`${veri.yonetici} yönetici`} />
        <Kart etiket="Doğrulanmış" deger={veri.dogrulanmis} ikon={UserCheck} renk="#22c55e"
          alt={veri.bekleyen > 0 ? `${veri.bekleyen} doğrulama bekliyor` : 'Bekleyen yok'} />
        <Kart etiket="Askıdaki hesap" deger={veri.askida} ikon={UserX} renk="#f59e0b"
          alt={veri.askida > 0 ? 'Girişe kapalı' : 'Askıda hesap yok'} />
        <Kart etiket="Açık oturum" deger={veri.acik_oturum} ikon={ShieldCheck} renk="#a855f7"
          alt="Şu an geçerli" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Kart etiket="Giriş (7 gün)" deger={veri.giris_7gun} ikon={Activity} renk="#3b7eff" />
        <Kart etiket="Hatalı giriş (24 saat)" deger={veri.basarisiz_24saat} ikon={AlertTriangle}
          renk={veri.basarisiz_24saat > 20 ? '#dc2626' : '#9da5be'}
          alt={veri.basarisiz_24saat > 20 ? 'Olağandışı — denetim kaydına bakın' : 'Normal aralıkta'} />
        <Kart etiket="Hazır yanıt" deger={veri.toplam_yanit} ikon={MessageSquare} renk="#f59e0b" />
        <Kart etiket="Toplam kullanım" deger={veri.toplam_kullanim} ikon={BarChart3} renk="#22c55e"
          alt="Panodan kopyalama" />
      </div>

      <div className="rounded-card overflow-hidden" style={{ background: '#ffffff', border: '1px solid rgba(0,6,30,0.07)' }}>
        <div className="px-5 py-3.5 flex items-center justify-between"
          style={{ borderBottom: '1px solid rgba(0,6,30,0.06)' }}>
          <p className="text-body-sm font-semibold" style={{ color: '#1a1d2e' }}>En çok kullanılan yanıtlar</p>
          <button onClick={yukle} className="btn-ghost text-label-md" aria-label="Yenile">
            <RefreshCw className="w-3.5 h-3.5" /> Yenile
          </button>
        </div>
        {veri.en_cok_kullanilan.length === 0 ? (
          <p className="px-5 py-8 text-center text-body-sm" style={{ color: '#9da5be' }}>
            Henüz kullanım kaydı yok — bir yanıt kopyalandığında burada görünür.
          </p>
        ) : veri.en_cok_kullanilan.map((y, i) => (
          <div key={i} className="px-5 py-3 flex items-center gap-3"
            style={{ borderBottom: i < veri.en_cok_kullanilan.length - 1 ? '1px solid rgba(0,6,30,0.04)' : 'none' }}>
            <span className="text-label-sm font-semibold tabular-nums w-5 flex-shrink-0" style={{ color: '#9da5be' }}>
              {i + 1}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-body-sm font-medium truncate" style={{ color: '#1a1d2e' }}>{y.baslik}</p>
              <p className="text-label-sm" style={{ color: '#9da5be' }}>{y.kategori}</p>
            </div>
            <span className="text-label-md tabular-nums px-2 py-0.5 rounded flex-shrink-0"
              style={{ background: 'rgba(59,127,255,0.1)', color: '#2563eb' }}>
              {y.kullanim} kez
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Sekme: Kullanıcılar ─────────────────────────────────────────────────────

const DURUMLAR = [
  ['hepsi', 'Hepsi'], ['aktif', 'Aktif'], ['bekleyen', 'Doğrulanmamış'],
  ['askida', 'Askıda'], ['yonetici', 'Yönetici'],
]

function Kullanicilar() {
  const { kullanici: ben } = useAuth()
  const [veri, setVeri] = useState(null)
  const [arama, setArama] = useState('')
  const [durum, setDurum] = useState('hepsi')
  const [sayfa, setSayfa] = useState(1)
  const [mesgulId, setMesgulId] = useState(null)
  const [silinecek, setSilinecek] = useState(null)

  const yukle = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/yonetim/kullanicilar', {
        params: { arama, durum, sayfa, limit: 25 },
      })
      setVeri(data)
    } catch (err) { toast.error(apiHataMesaji(err, 'Kullanıcılar alınamadı')) }
  }, [arama, durum, sayfa])

  // Arama kutusuna her harfte istek atmamak için gecikmeli tetikleme.
  useEffect(() => {
    const t = setTimeout(yukle, arama ? 300 : 0)
    return () => clearTimeout(t)
  }, [yukle, arama])

  useEffect(() => { setSayfa(1) }, [arama, durum])

  const eylem = async (k, govde, mesaj) => {
    setMesgulId(k.id)
    try {
      await axios.patch(`/api/yonetim/kullanicilar/${k.id}`, govde)
      toast.success(mesaj)
      yukle()
    } catch (err) { toast.error(apiHataMesaji(err, 'İşlem tamamlanamadı')) }
    finally { setMesgulId(null) }
  }

  const sil = async (k) => {
    setMesgulId(k.id)
    try {
      await axios.delete(`/api/yonetim/kullanicilar/${k.id}`)
      toast.success(`${k.email} silindi`)
      setSilinecek(null)
      yukle()
    } catch (err) { toast.error(apiHataMesaji(err, 'Kullanıcı silinemedi')) }
    finally { setMesgulId(null) }
  }

  const oturumKapat = async (k) => {
    setMesgulId(k.id)
    try {
      const { data } = await axios.post(`/api/yonetim/kullanicilar/${k.id}/oturumlari-kapat`)
      toast.success(data.mesaj)
      yukle()
    } catch (err) { toast.error(apiHataMesaji(err, 'Oturumlar kapatılamadı')) }
    finally { setMesgulId(null) }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1" style={{ minWidth: 240, maxWidth: 380 }}>
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
            style={{ color: '#9da5be' }} />
          <input type="text" className="input-field" style={{ paddingLeft: 38 }}
            placeholder="Ad veya e-posta ile ara…" value={arama}
            onChange={e => setArama(e.target.value)} />
        </div>
        <div className="flex gap-1 p-1 rounded-btn" style={{ background: '#f0f2f8' }}>
          {DURUMLAR.map(([id, etiket]) => (
            <button key={id} onClick={() => setDurum(id)}
              className="px-3 py-1.5 rounded text-label-md font-medium transition-all duration-150"
              style={durum === id
                ? { background: '#ffffff', color: '#2563eb', boxShadow: '0 1px 3px rgba(0,6,30,0.10)' }
                : { color: '#6b7388' }}>
              {etiket}
            </button>
          ))}
        </div>
      </div>

      {veri === null ? <Yukleniyor />
        : veri.kayitlar.length === 0 ? (
          <Bos ikon={Users} baslik="Kullanıcı bulunamadı"
            metin={arama ? `"${arama}" ile eşleşen kayıt yok` : 'Bu filtreye uyan üye yok'} />
        ) : (
          <>
            <div className="flex flex-col gap-2">
              {veri.kayitlar.map(k => {
                const benMiyim = k.id === ben?.id
                const mesgul = mesgulId === k.id
                return (
                  <div key={k.id} className="rounded-card px-4 py-3.5"
                    style={{ background: '#ffffff', border: '1px solid rgba(0,6,30,0.07)',
                             borderLeft: `3px solid ${k.rol === 'admin' ? '#2563eb' : !k.aktif ? '#f59e0b' : !k.dogrulandi ? '#9da5be' : '#22c55e'}` }}>
                    <div className="flex items-start gap-3 flex-wrap">
                      <div className="flex-1 min-w-0" style={{ minWidth: 200 }}>
                        <div className="flex items-center gap-2 flex-wrap mb-0.5">
                          <p className="text-body-sm font-semibold" style={{ color: '#1a1d2e' }}>{k.ad_soyad}</p>
                          {k.rol === 'admin' && (
                            <span className="badge flex items-center gap-1"
                              style={{ background: 'rgba(37,99,235,0.1)', color: '#2563eb' }}>
                              <Shield className="w-3 h-3" />Yönetici
                            </span>
                          )}
                          {k.kurucu_admin && (
                            <span className="badge" style={{ background: 'rgba(0,6,30,0.05)', color: '#6b7388' }}
                              title="Sunucu yapılandırmasında tanımlı — panelden değiştirilemez">
                              sabit
                            </span>
                          )}
                          {!k.dogrulandi && (
                            <span className="badge" style={{ background: 'rgba(0,6,30,0.05)', color: '#6b7388' }}>
                              doğrulanmadı
                            </span>
                          )}
                          {!k.aktif && (
                            <span className="badge" style={{ background: 'rgba(245,158,11,0.12)', color: '#d97706' }}>
                              askıda
                            </span>
                          )}
                          {k.kilitli && (
                            <span className="badge flex items-center gap-1"
                              style={{ background: 'rgba(239,68,68,0.1)', color: '#dc2626' }}>
                              <Lock className="w-3 h-3" />kilitli
                            </span>
                          )}
                          {benMiyim && (
                            <span className="badge" style={{ background: 'rgba(34,197,94,0.1)', color: '#16a34a' }}>
                              siz
                            </span>
                          )}
                        </div>
                        <p className="text-label-md font-mono truncate" style={{ color: '#6b7388' }}>{k.email}</p>
                        <p className="text-label-sm mt-1 flex items-center gap-3 flex-wrap" style={{ color: '#9da5be' }}>
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />son giriş: {tarih(k.son_giris)}
                          </span>
                          <span>kayıt: {tarih(k.created_at, true)}</span>
                          {k.acik_oturum > 0 && <span>{k.acik_oturum} açık oturum</span>}
                        </p>
                      </div>

                      <div className="flex items-center gap-1 flex-shrink-0">
                        {mesgul && <Loader2 className="w-4 h-4 animate-spin mr-1" style={{ color: '#9da5be' }} />}
                        {!benMiyim && !k.kurucu_admin && (
                          <>
                            <button onClick={() => eylem(k, { rol: k.rol === 'admin' ? 'uye' : 'admin' },
                              k.rol === 'admin' ? 'Yöneticilik kaldırıldı' : 'Yönetici yapıldı')}
                              disabled={mesgul} className="btn-ghost text-label-md"
                              title={k.rol === 'admin' ? 'Yöneticiliği kaldır' : 'Yönetici yap'}>
                              <Shield className="w-3.5 h-3.5" />
                              {k.rol === 'admin' ? 'Yetkiyi al' : 'Yönetici yap'}
                            </button>
                            <button onClick={() => eylem(k, { aktif: !k.aktif },
                              k.aktif ? 'Hesap askıya alındı' : 'Hesap yeniden açıldı')}
                              disabled={mesgul} className="btn-ghost text-label-md">
                              {k.aktif ? <><UserX className="w-3.5 h-3.5" />Askıya al</>
                                       : <><UserCheck className="w-3.5 h-3.5" />Aktifleştir</>}
                            </button>
                          </>
                        )}
                        {k.acik_oturum > 0 && (
                          <button onClick={() => oturumKapat(k)} disabled={mesgul}
                            className="btn-ghost text-label-md" title="Tüm oturumlarını kapat">
                            <LogOut className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {!benMiyim && !k.kurucu_admin && (
                          <button onClick={() => setSilinecek(k)} disabled={mesgul}
                            className="btn-ghost text-label-md" title="Hesabı sil" style={{ color: '#9da5be' }}>
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>

                    {silinecek?.id === k.id && (
                      <div className="mt-3 flex items-center gap-2 px-3 py-2.5 rounded-btn flex-wrap"
                        style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)' }}>
                        <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#dc2626' }} />
                        <p className="text-label-md flex-1" style={{ color: '#dc2626' }}>
                          <strong>{k.email}</strong> kalıcı olarak silinsin mi? Oturumları da kapanır.
                        </p>
                        <button onClick={() => sil(k)} className="text-label-md font-semibold px-2.5 py-1 rounded"
                          style={{ background: 'rgba(239,68,68,0.1)', color: '#dc2626' }}>Sil</button>
                        <button onClick={() => setSilinecek(null)} className="text-label-md px-2.5 py-1 rounded"
                          style={{ color: '#6b7388' }}>İptal</button>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            <Sayfalayici sayfa={veri.sayfa} limit={veri.limit} toplam={veri.toplam} onDegis={setSayfa} />
          </>
        )}
    </div>
  )
}

// ─── Sekme: Hazır Yanıtlar ───────────────────────────────────────────────────

function YanitModal({ yanit, kategoriler, onKaydet, onKapat }) {
  const [baslik, setBaslik] = useState(yanit?.title || '')
  const [icerik, setIcerik] = useState(yanit?.content || '')
  const [kategori, setKategori] = useState(yanit?.category || kategoriler[0] || 'Genel')
  const [mesgul, setMesgul] = useState(false)

  useHotkeys({ escape: () => onKapat(), 'ctrl+k': () => {} })

  const kaydet = async () => {
    setMesgul(true)
    await onKaydet({ title: baslik.trim(), content: icerik.trim(), category: kategori })
    setMesgul(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,6,30,0.4)', backdropFilter: 'blur(6px)' }} onClick={onKapat}>
      <div className="w-full max-w-lg rounded-xl overflow-hidden animate-slide-up"
        style={{ background: '#ffffff', boxShadow: '0 24px 64px rgba(0,6,30,0.18)' }}
        onClick={e => e.stopPropagation()}>
        <div className="px-6 py-4 flex items-center justify-between"
          style={{ borderBottom: '1px solid rgba(0,6,30,0.08)' }}>
          <h2 className="text-title-md font-semibold" style={{ color: '#1a1d2e' }}>
            {yanit ? 'Yanıtı Düzenle' : 'Yeni Yanıt Ekle'}
          </h2>
          <button onClick={onKapat} className="p-1.5 rounded hover:opacity-70" style={{ color: '#9da5be' }}>
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-6 py-5 flex flex-col gap-4">
          <div>
            <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>Başlık</label>
            <input type="text" className="input-field" value={baslik} maxLength={200}
              onChange={e => setBaslik(e.target.value)} placeholder="Yanıt başlığı…" />
          </div>
          <div>
            <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>Kategori</label>
            <select className="input-field" style={{ cursor: 'pointer' }} value={kategori}
              onChange={e => setKategori(e.target.value)}>
              {kategoriler.map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </div>
          <div>
            <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>
              İçerik <span style={{ color: '#9da5be' }}>({icerik.length}/20000)</span>
            </label>
            <textarea className="textarea-field" value={icerik} maxLength={20000}
              onChange={e => setIcerik(e.target.value)} placeholder="Hazır yanıt metni…"
              style={{ minHeight: 160 }} />
          </div>
        </div>
        <div className="px-6 py-4 flex items-center justify-end gap-3"
          style={{ borderTop: '1px solid rgba(0,6,30,0.08)', background: '#f8f9fc' }}>
          <button onClick={onKapat} className="btn-ghost">İptal</button>
          <button onClick={kaydet} disabled={!baslik.trim() || !icerik.trim() || mesgul}
            className="btn-primary">
            {mesgul ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {yanit ? 'Kaydet' : 'Ekle'}
          </button>
        </div>
      </div>
    </div>
  )
}

const SABIT_KATEGORILER = ['Alan Adı', 'Hosting', 'SSL', 'E-posta', 'DNS', 'Veritabanı', 'Genel']

function Yanitlar() {
  const [yanitlar, setYanitlar] = useState(null)
  const [ozelKategoriler, setOzelKategoriler] = useState([])
  const [arama, setArama] = useState('')
  const [siralama, setSiralama] = useState('kullanim')
  const [modal, setModal] = useState(null)     // { yanit } | { yanit: null }
  const [silinecek, setSilinecek] = useState(null)

  const yukle = useCallback(async () => {
    try {
      const [y, k] = await Promise.all([
        axios.get('/api/hazir-yanitlar'),
        axios.get('/api/hazir-yanitlar/kategoriler'),
      ])
      setYanitlar(y.data)
      setOzelKategoriler(k.data)
    } catch (err) { toast.error(apiHataMesaji(err, 'Hazır yanıtlar alınamadı')) }
  }, [])

  useEffect(() => { yukle() }, [yukle])

  const kategoriAdlari = useMemo(
    () => [...SABIT_KATEGORILER, ...ozelKategoriler.map(k => k.name)],
    [ozelKategoriler])

  const gosterilecek = useMemo(() => {
    if (!yanitlar) return []
    const q = arama.trim().toLocaleLowerCase('tr-TR')
    const suz = q
      ? yanitlar.filter(y => (y.title + ' ' + y.content + ' ' + y.category)
          .toLocaleLowerCase('tr-TR').includes(q))
      : [...yanitlar]
    return suz.sort((a, b) =>
      siralama === 'kullanim' ? b.use_count - a.use_count
      : siralama === 'baslik' ? a.title.localeCompare(b.title, 'tr')
      : a.category.localeCompare(b.category, 'tr') || a.title.localeCompare(b.title, 'tr'))
  }, [yanitlar, arama, siralama])

  const kaydet = async (govde) => {
    try {
      if (modal.yanit) await axios.put(`/api/hazir-yanitlar/${modal.yanit.id}`, govde)
      else await axios.post('/api/hazir-yanitlar', govde)
      toast.success(modal.yanit ? 'Yanıt güncellendi' : 'Yanıt eklendi')
      setModal(null)
      yukle()
    } catch (err) { toast.error(apiHataMesaji(err, 'Kaydedilemedi')) }
  }

  const sil = async (y) => {
    try {
      await axios.delete(`/api/hazir-yanitlar/${y.id}`)
      toast.success('Yanıt silindi')
      setSilinecek(null)
      yukle()
    } catch (err) { toast.error(apiHataMesaji(err, 'Silinemedi')) }
  }

  const pinle = async (y) => {
    try {
      await axios.patch(`/api/hazir-yanitlar/${y.id}/pin`)
      yukle()
    } catch (err) { toast.error(apiHataMesaji(err, 'Sabitleme değiştirilemedi')) }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1" style={{ minWidth: 240, maxWidth: 380 }}>
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
            style={{ color: '#9da5be' }} />
          <input type="text" className="input-field" style={{ paddingLeft: 38 }}
            placeholder="Başlık, içerik veya kategori…" value={arama}
            onChange={e => setArama(e.target.value)} />
        </div>
        <select className="input-field" value={siralama} onChange={e => setSiralama(e.target.value)}
          style={{ width: 'auto', cursor: 'pointer' }}>
          <option value="kullanim">En çok kullanılan</option>
          <option value="baslik">Başlığa göre</option>
          <option value="kategori">Kategoriye göre</option>
        </select>
        <button onClick={() => setModal({ yanit: null })} className="btn-primary">
          <Plus className="w-4 h-4" /> Yeni Yanıt
        </button>
      </div>

      {yanitlar === null ? <Yukleniyor />
        : gosterilecek.length === 0 ? (
          <Bos ikon={MessageSquare} baslik="Yanıt bulunamadı"
            metin={arama ? `"${arama}" ile eşleşen kayıt yok` : 'Yeni Yanıt ile ekleyin'} />
        ) : (
          <div className="flex flex-col gap-2">
            {gosterilecek.map(y => (
              <div key={y.id} className="rounded-card px-4 py-3"
                style={{ background: '#ffffff', border: '1px solid rgba(0,6,30,0.07)' }}>
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <p className="text-body-sm font-semibold" style={{ color: '#1a1d2e' }}>{y.title}</p>
                      <span className="badge" style={{ background: 'rgba(0,6,30,0.05)', color: '#6b7388' }}>
                        {y.category}
                      </span>
                      {y.is_pinned && (
                        <span className="badge" style={{ background: 'rgba(245,158,11,0.12)', color: '#d97706' }}>
                          sabitlenmiş
                        </span>
                      )}
                      {y.use_count > 0 && (
                        <span className="badge tabular-nums"
                          style={{ background: 'rgba(59,127,255,0.1)', color: '#2563eb' }}>
                          {y.use_count} kullanım
                        </span>
                      )}
                    </div>
                    <p className="text-label-md" style={{
                      color: '#6b7388', display: '-webkit-box', WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical', overflow: 'hidden', lineHeight: 1.55,
                    }}>
                      {y.content}
                    </p>
                  </div>
                  <div className="flex items-center gap-0.5 flex-shrink-0">
                    <button onClick={() => pinle(y)} className="p-1.5 rounded hover:opacity-70"
                      style={{ color: y.is_pinned ? '#d97706' : '#9da5be' }}
                      title={y.is_pinned ? 'Sabitlemeyi kaldır' : 'Sabitle'}>
                      <Star className="w-3.5 h-3.5" style={y.is_pinned ? { fill: '#d97706' } : {}} />
                    </button>
                    <button onClick={() => setModal({ yanit: y })} className="p-1.5 rounded hover:opacity-70"
                      style={{ color: '#6b7388' }} title="Düzenle">
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => setSilinecek(y)} className="p-1.5 rounded hover:opacity-70"
                      style={{ color: '#9da5be' }} title="Sil">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {silinecek?.id === y.id && (
                  <div className="mt-3 flex items-center gap-2 px-3 py-2.5 rounded-btn"
                    style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)' }}>
                    <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#dc2626' }} />
                    <p className="text-label-md flex-1" style={{ color: '#dc2626' }}>Bu yanıt silinsin mi?</p>
                    <button onClick={() => sil(y)} className="text-label-md font-semibold px-2.5 py-1 rounded"
                      style={{ background: 'rgba(239,68,68,0.1)', color: '#dc2626' }}>Sil</button>
                    <button onClick={() => setSilinecek(null)} className="text-label-md px-2.5 py-1 rounded"
                      style={{ color: '#6b7388' }}>İptal</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

      {modal && (
        <YanitModal yanit={modal.yanit} kategoriler={kategoriAdlari}
          onKaydet={kaydet} onKapat={() => setModal(null)} />
      )}
    </div>
  )
}

// ─── Sekme: Denetim Kaydı ────────────────────────────────────────────────────

function Denetim() {
  const [veri, setVeri] = useState(null)
  const [eylemler, setEylemler] = useState([])
  const [eylem, setEylem] = useState('')
  const [sayfa, setSayfa] = useState(1)

  const yukle = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/yonetim/denetim', {
        params: { eylem, sayfa, limit: 50 },
      })
      setVeri(data)
    } catch (err) { toast.error(apiHataMesaji(err, 'Denetim kaydı alınamadı')) }
  }, [eylem, sayfa])

  useEffect(() => { yukle() }, [yukle])
  useEffect(() => { setSayfa(1) }, [eylem])
  useEffect(() => {
    axios.get('/api/yonetim/denetim/eylemler')
      .then(({ data }) => setEylemler(data)).catch(() => {})
  }, [])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <select className="input-field" value={eylem} onChange={e => setEylem(e.target.value)}
          style={{ width: 'auto', minWidth: 220, cursor: 'pointer' }}>
          <option value="">Tüm eylemler</option>
          {eylemler.map(e => <option key={e} value={e}>{EYLEM_ADI[e] || e}</option>)}
        </select>
        <button onClick={yukle} className="btn-ghost text-label-md">
          <RefreshCw className="w-3.5 h-3.5" /> Yenile
        </button>
        {veri && (
          <p className="text-label-md ml-auto" style={{ color: '#9da5be' }}>
            {veri.toplam} kayıt · en yeniden eskiye
          </p>
        )}
      </div>

      {veri === null ? <Yukleniyor />
        : veri.kayitlar.length === 0 ? (
          <Bos ikon={Activity} baslik="Kayıt yok" metin="Bu filtreye uyan denetim kaydı bulunamadı" />
        ) : (
          <>
            <div className="rounded-card overflow-hidden"
              style={{ background: '#ffffff', border: '1px solid rgba(0,6,30,0.07)' }}>
              {veri.kayitlar.map((d, i) => (
                <div key={d.id} className="px-4 py-2.5 flex items-start gap-3 flex-wrap"
                  style={{ borderBottom: i < veri.kayitlar.length - 1 ? '1px solid rgba(0,6,30,0.04)' : 'none' }}>
                  <span className="text-label-sm tabular-nums flex-shrink-0 font-mono pt-0.5"
                    style={{ color: '#9da5be', width: 120 }}>
                    {tarih(d.created_at)}
                  </span>
                  <span className="text-label-md font-medium flex-shrink-0" style={{ color: EYLEM_RENGI(d.eylem), width: 180 }}>
                    {EYLEM_ADI[d.eylem] || d.eylem}
                  </span>
                  <span className="text-label-md font-mono truncate flex-1" style={{ color: '#4a5068', minWidth: 160 }}>
                    {d.eposta || '—'}
                  </span>
                  <span className="text-label-md truncate" style={{ color: '#6b7388', minWidth: 120, maxWidth: 280 }}>
                    {d.detay || d.hedef || ''}
                  </span>
                  <span className="text-label-sm font-mono flex-shrink-0" style={{ color: '#9da5be', width: 110 }}>
                    {d.ip || '—'}
                  </span>
                </div>
              ))}
            </div>
            <Sayfalayici sayfa={veri.sayfa} limit={veri.limit} toplam={veri.toplam} onDegis={setSayfa} />
          </>
        )}
    </div>
  )
}

// ─── Kabuk ───────────────────────────────────────────────────────────────────

export default function Yonetim() {
  const { admin, yukleniyor } = useAuth()
  const [sekme, setSekme] = useState('istatistik')

  if (yukleniyor) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="w-7 h-7 animate-spin" style={{ color: '#3b7eff' }} />
      </div>
    )
  }

  // Sunucu zaten 403 döndürüyor; bu yalnızca arayüzün boş tablolar yerine
  // anlaşılır bir mesaj göstermesi için.
  if (!admin) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <div className="text-center max-w-sm">
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4"
            style={{ background: 'rgba(239,68,68,0.08)' }}>
            <Lock className="w-6 h-6" style={{ color: '#dc2626' }} />
          </div>
          <p className="text-title-md font-medium mb-1" style={{ color: '#1a1d2e' }}>Yetkiniz yok</p>
          <p className="text-body-md" style={{ color: '#6b7388' }}>
            Bu sayfa yalnızca yöneticiye açıktır.
          </p>
        </div>
      </div>
    )
  }

  const aktif = SEKMELER.find(s => s.id === sekme)

  return (
    <div className="flex h-full overflow-hidden">
      <aside className="flex flex-col w-56 flex-shrink-0 h-full"
        style={{ background: '#ffffff', borderRight: '1px solid rgba(0,6,30,0.08)' }}>
        <div className="px-4 pt-5 pb-4 flex-shrink-0">
          <div className="flex items-center gap-2 mb-0.5">
            <div className="w-6 h-6 rounded flex items-center justify-center"
              style={{ background: 'rgba(37,99,235,0.12)' }}>
              <ShieldCheck className="w-3.5 h-3.5" style={{ color: '#2563eb' }} />
            </div>
            <p className="text-body-sm font-semibold" style={{ color: '#1a1d2e' }}>Yönetim</p>
          </div>
          <p className="text-label-sm pl-8" style={{ color: '#9da5be' }}>Yalnızca yöneticiler</p>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-2 flex flex-col gap-0.5">
          {SEKMELER.map(({ id, etiket, ikon: Ikon, renk }) => {
            const secili = sekme === id
            return (
              <button key={id} onClick={() => setSekme(id)}
                className="flex items-center gap-2.5 px-2.5 py-2 rounded-btn text-left transition-all"
                style={secili ? { background: `${renk}15`, color: renk } : { color: '#6b7388' }}>
                <Ikon className="w-3.5 h-3.5 flex-shrink-0" />
                <span className="flex-1 text-body-sm font-medium">{etiket}</span>
                {secili && <ChevronRight className="w-3 h-3" />}
              </button>
            )
          })}
        </nav>
      </aside>

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <div className="px-6 pt-5 pb-3 flex-shrink-0 flex items-center gap-2.5"
          style={{ background: '#ffffff', borderBottom: '1px solid rgba(0,6,30,0.08)' }}>
          <aktif.ikon className="w-4 h-4" style={{ color: aktif.renk }} />
          <h2 className="text-headline-md font-semibold" style={{ color: '#1a1d2e' }}>{aktif.etiket}</h2>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {sekme === 'istatistik' && <Istatistikler />}
          {sekme === 'kullanici' && <Kullanicilar />}
          {sekme === 'yanit' && <Yanitlar />}
          {sekme === 'denetim' && <Denetim />}
        </div>
      </div>
    </div>
  )
}
