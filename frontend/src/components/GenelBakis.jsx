import { useState } from 'react'
import { useTarget, useCommittedTarget } from '../context/TargetContext'
import {
  LayoutGrid, Loader2, ArrowRight, FileText, Gauge, ExternalLink,
  CheckCircle2, AlertTriangle, XCircle, Info,
} from 'lucide-react'
import toast from 'react-hot-toast'
import axios from 'axios'
import { apiHataMesaji } from '../lib/apiHata'
import MusteriRaporu from './MusteriRaporu'

// Alan adı merkezli açılış ekranı.
//
// Panel araç merkezliydi: "example.com sorunlu" diyen bir çağrıda teknisyen
// sekiz sekmeyi tek tek geziyordu. Bu ekran tek Enter ile ucuz kontrollerin
// hepsini paralel çalıştırır (backend'de ~1.5 sn) ve "önce şu araca bak" der.
//
// Site hızı bilerek burada DEĞİL: 30-60 sn sürüyor ve tarayıcı başlatıyor.
// Panonun saniyeler içinde açılması gerekiyor; hız ayrı düğmeyle tetiklenir.

const DURUM = {
  healthy: { Ikon: CheckCircle2,   renk: '#0CCE6B', arka: 'rgba(12,206,107,0.09)',  sekil: '●', etiket: 'Sorun yok' },
  warning: { Ikon: AlertTriangle,  renk: '#FFA400', arka: 'rgba(255,164,0,0.10)',   sekil: '■', etiket: 'İyileştirilmeli' },
  error:   { Ikon: XCircle,        renk: '#FF4E42', arka: 'rgba(255,78,66,0.09)',   sekil: '▲', etiket: 'Sorunlu' },
  info:    { Ikon: Info,           renk: '#6b7388', arka: 'rgba(107,115,136,0.08)', sekil: '·', etiket: 'Bilgi' },
}

const ARAC_ADI = {
  'dns-history': 'DNS History', 'ssl-tools': 'SSL Araçları',
  'dns-toolbox': 'DNS Toolbox', 'quick-check': 'Hızlı Kontrol',
  'mail-health': 'Mail Sağlığı', 'blacklist': 'Blacklist / RBL',
}

function Kart({ k, onAc }) {
  const d = DURUM[k.durum] || DURUM.info
  return (
    <button
      onClick={() => k.arac && onAc(k.arac)}
      className="rounded-card px-4 py-4 text-left w-full transition-shadow"
      style={{ background: '#ffffff', cursor: k.arac ? 'pointer' : 'default' }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,6,30,0.09)' }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none' }}
    >
      <div className="flex items-center justify-between mb-2.5">
        <p className="text-label-md font-medium" style={{ color: '#6b7388' }}>{k.baslik}</p>
        <d.Ikon className="w-4 h-4 flex-shrink-0" style={{ color: d.renk }} />
      </div>
      <p className="font-semibold mb-1" style={{ fontSize: 17, color: d.renk, lineHeight: 1.25 }}>
        {k.deger || d.etiket}
      </p>
      {k.detay && (
        <p className="text-label-md" style={{ color: '#9da5be', lineHeight: 1.45,
             display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {k.detay}
        </p>
      )}
      {k.arac && (
        <p className="text-label-sm mt-2.5 flex items-center gap-1" style={{ color: '#3b7eff' }}>
          {ARAC_ADI[k.arac] || k.arac} <ArrowRight className="w-3 h-3" />
        </p>
      )}
    </button>
  )
}

export default function GenelBakis({ onNavigate }) {
  const [loading, setLoading] = useState(false)
  const [veri, setVeri] = useState(null)
  const [raporAcik, setRaporAcik] = useState(false)
  const { target, commitTarget } = useTarget()

  const run = async (d) => {
    setLoading(true); setVeri(null)
    try {
      const r = await axios.post('/api/genel-bakis/', { domain: d }, { timeout: 60000 })
      setVeri(r.data)
    } catch (err) {
      toast.error(apiHataMesaji(err, 'Genel bakış alınamadı'))
    } finally {
      setLoading(false)
    }
  }

  // autoRun:true — kontroller ucuz (~1.5 sn, tarayıcı başlatmıyor) ve pano
  // açılış ekranı; hedef zaten commit edilmişse kendiliğinden çalışsın.
  useCommittedTarget(run, { autoRun: true })

  const d = veri ? (DURUM[veri.genel_durum] || DURUM.info) : null

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-8 pt-8 pb-6">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-btn flex items-center justify-center"
               style={{ background: 'linear-gradient(135deg, rgba(59,127,255,0.18) 0%, rgba(12,206,107,0.15) 100%)' }}>
            <LayoutGrid className="w-4 h-4" style={{ color: '#3b7eff' }} />
          </div>
          <h1 className="text-headline-md font-semibold" style={{ color: '#1a1d2e', letterSpacing: '-0.01em' }}>
            Genel Bakış
          </h1>
        </div>
        <p className="text-body-md" style={{ color: '#6b7388' }}>
          Bir alan adının tüm sağlık başlıklarını tek seferde gör — hangi araca bakman
          gerektiğini söyler
        </p>
      </div>

      <div className="px-8 pb-6">
        <div className="flex items-center gap-3 flex-wrap">
          <button onClick={commitTarget} disabled={loading || !target.trim()} autoFocus
                  className="btn-primary flex items-center gap-2">
            {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Kontrol ediliyor…</>
                     : <><LayoutGrid className="w-4 h-4" /> {target.trim() ? `${target.trim()} durumunu gör` : 'Genel Bakış'}</>}
          </button>
          {!target.trim() && (
            <p className="text-body-sm" style={{ color: '#9da5be' }}>
              Üstteki hedef çubuğuna bir alan adı yazın.
            </p>
          )}
        </div>
      </div>

      {loading && (
        <div className="px-8">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[1,2,3,4,5,6].map(i => (
              <div key={i} className="rounded-card px-4 py-4 animate-pulse" style={{ background: '#ffffff' }}>
                <div className="h-3 rounded w-20 mb-3" style={{ background: '#f2f4fa' }} />
                <div className="h-5 rounded w-28 mb-2" style={{ background: '#eef0f6' }} />
                <div className="h-3 rounded w-full" style={{ background: '#f4f5fb' }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {veri && !loading && (
        <div className="px-8 pb-10 flex flex-col gap-5 slide-up">
          {/* Genel durum */}
          <div className="rounded-card px-5 py-4 flex items-center gap-4 flex-wrap"
               style={{ background: d.arka, borderLeft: `3px solid ${d.renk}` }}>
            <d.Ikon className="w-5 h-5 flex-shrink-0" style={{ color: d.renk }} />
            <div className="flex-1 min-w-0">
              <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>{veri.ozet}</p>
              <p className="text-label-sm mt-0.5" style={{ color: '#6b7388' }}>
                {veri.kartlar.length} başlık · {veri.sure_ms} ms
                {veri.alt_alan_mi && ` · kayıt bilgileri ${veri.kayit_alan_adi} üzerinden`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => setRaporAcik(true)} className="btn-secondary text-label-md py-1.5 px-3">
                <FileText className="w-3.5 h-3.5" /> Müşteri Raporu
              </button>
              <a href={`https://${veri.domain}`} target="_blank" rel="noopener noreferrer"
                 className="btn-ghost text-label-md py-1.5 px-2.5">
                <ExternalLink className="w-3.5 h-3.5" /> Siteyi aç
              </a>
            </div>
          </div>

          {/* Önce buraya bak */}
          {veri.sonraki_adim && (
            <button onClick={() => onNavigate?.(veri.sonraki_adim)}
                    className="rounded-card px-5 py-3.5 flex items-center gap-3 text-left"
                    style={{ background: '#ffffff' }}>
              <span className="text-label-sm font-medium uppercase tracking-wider" style={{ color: '#9da5be' }}>
                Önce buraya bak
              </span>
              <span className="text-body-sm font-medium flex items-center gap-1.5" style={{ color: '#3b7eff' }}>
                {ARAC_ADI[veri.sonraki_adim] || veri.sonraki_adim}
                <ArrowRight className="w-3.5 h-3.5" />
              </span>
            </button>
          )}

          {/* Kartlar */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {veri.kartlar.map(k => (
              <Kart key={k.id} k={k} onAc={(arac) => onNavigate?.(arac)} />
            ))}
          </div>

          {/* Hız testi — pahalı olduğu için ayrı */}
          <button onClick={() => onNavigate?.('site-speed')}
                  className="rounded-card px-5 py-3.5 flex items-center gap-3 text-left"
                  style={{ background: '#ffffff' }}>
            <Gauge className="w-4 h-4 flex-shrink-0" style={{ color: '#3b7eff' }} />
            <div className="flex-1 min-w-0">
              <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>Site hızını da ölç</p>
              <p className="text-label-sm" style={{ color: '#9da5be' }}>
                Gerçek tarayıcıyla mobil + masaüstü ölçüm — 30-60 saniye sürer, bu yüzden ayrı
              </p>
            </div>
            <ArrowRight className="w-4 h-4 flex-shrink-0" style={{ color: '#3b7eff' }} />
          </button>
        </div>
      )}

      {!veri && !loading && (
        <div className="flex-1 flex flex-col items-center justify-center pb-20 px-8">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
               style={{ background: 'rgba(59,127,255,0.06)' }}>
            <LayoutGrid className="w-7 h-7 opacity-40" style={{ color: '#3b7eff' }} />
          </div>
          <p className="text-title-md font-medium mb-1" style={{ color: '#4a5068' }}>Alan adı girin</p>
          <p className="text-body-md text-center max-w-sm" style={{ color: '#6b7388' }}>
            Alan adı, SSL, DNS, HTTP erişimi, e-posta kayıtları ve kara liste durumu
            tek seferde kontrol edilir.
          </p>
        </div>
      )}

      {raporAcik && (
        <MusteriRaporu veri={veri} onKapat={() => setRaporAcik(false)} />
      )}
    </div>
  )
}
