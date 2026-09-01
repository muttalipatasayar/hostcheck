import { useEffect, useRef, useState } from 'react'
import { useTarget, useCommittedTarget } from '../context/TargetContext'
import {
  Gauge, Loader2, CheckCircle2, XCircle, AlertTriangle, Info,
  ChevronDown, ChevronUp, Copy, Check, Wrench, User, Monitor,
  Smartphone, Server, Clock, TrendingUp, TrendingDown, Minus,
  ExternalLink, Zap, Globe,
} from 'lucide-react'
import toast from 'react-hot-toast'
import axios from 'axios'
import { apiHataMesaji } from '../lib/apiHata'

// PageSpeed'in kendi renk dili — teknisyen bu üç rengi zaten tanıyor.
// Panelin genel paletinden bilerek ayrılıyor: skor bandı evrensel bir
// gösterge, projeye özel renklerle değiştirmek tanınırlığı bozardı.
const SKOR_RENK = { healthy: '#0CCE6B', warning: '#FFA400', error: '#FF4E42', info: '#6b7388' }
// Renge EK olarak şekil: renk körlüğü için PSI'nin kendi çözümü
const SKOR_SEKIL = { healthy: '●', warning: '■', error: '▲', info: '·' }
const SKOR_ETIKET = { healthy: 'İyi', warning: 'İyileştirilmeli', error: 'Kötü', info: 'Bilgi' }

const DURUM_IKON = { healthy: CheckCircle2, warning: AlertTriangle, error: XCircle, info: Info }

// Şelale çubuklarının tür renkleri
const TIP_RENK = {
  script: '#f5b642', css: '#4a6cf7', link: '#4a6cf7', img: '#22c55e',
  image: '#22c55e', font: '#a855f7', fetch: '#06b6d4', xmlhttprequest: '#06b6d4',
  navigation: '#1a1d2e', other: '#9da5be',
}
const tipRenk = (t) => TIP_RENK[t] || TIP_RENK.other

// Şelalede tam URL sığmaz. Baştan kesmek "www.site.com/static/sty…" gibi
// birbirinden ayırt edilemeyen satırlar üretiyordu; ayırt edici olan kısım
// host ile DOSYA ADI, arası atılabilir.
function kisaUrl(url) {
  try {
    const u = new URL(url)
    const parcalar = u.pathname.split('/').filter(Boolean)
    const dosya = parcalar[parcalar.length - 1] || '/'
    return parcalar.length > 1 ? `${u.host}/…/${dosya}` : `${u.host}/${dosya}`
  } catch {
    return (url || '').replace(/^https?:\/\//, '')
  }
}

const ms = (v) => v == null ? '—' : v < 1000 ? `${Math.round(v)} ms` : `${(v / 1000).toFixed(2).replace('.', ',')} sn`
const bayt = (n) => {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${Math.round(n / 1024)} KB`
  return `${(n / 1048576).toFixed(2).replace('.', ',')} MB`
}

// ── Skor göstergesi ─────────────────────────────────────────────────────────
// SSLTools'taki DaysGauge deseninin aynısı; oradaki merkez kayması (C=44 iken
// SVG 96) burada düzeltildi.
function SkorGauge({ skor, durum, boyut = 128 }) {
  const renk = SKOR_RENK[durum] || SKOR_RENK.info
  const C = boyut / 2
  const stroke = boyut * 0.075
  const R = C - stroke * 1.6
  const cevre = 2 * Math.PI * R
  const dolu = (Math.max(0, Math.min(100, skor ?? 0)) / 100) * cevre

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative flex items-center justify-center" style={{ width: boyut, height: boyut }}>
        <svg width={boyut} height={boyut} style={{ transform: 'rotate(-90deg)' }}>
          <circle cx={C} cy={C} r={R} fill={`${renk}14`} stroke="rgba(0,6,30,0.07)" strokeWidth={stroke} />
          <circle
            cx={C} cy={C} r={R} fill="none" stroke={renk} strokeWidth={stroke}
            strokeLinecap="round" strokeDasharray={`${dolu} ${cevre}`}
            style={{ transition: 'stroke-dasharray 0.8s cubic-bezier(0.4,0,0.2,1)' }}
          />
        </svg>
        <div className="absolute flex flex-col items-center leading-none">
          <span className="font-bold" style={{ fontSize: boyut * 0.31, color: renk }}>
            {skor ?? '—'}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <span style={{ color: renk, fontSize: 11 }}>{SKOR_SEKIL[durum]}</span>
        <span className="text-label-md font-medium" style={{ color: renk }}>{SKOR_ETIKET[durum]}</span>
      </div>
    </div>
  )
}

// ── Core Web Vitals kartı ───────────────────────────────────────────────────
function MetrikKart({ ad, aciklama, deger, durum, esikler, birim = 'ms' }) {
  const renk = SKOR_RENK[durum] || SKOR_RENK.info
  const [iyi, kotu] = esikler
  // Değerin eşik çubuğu üstündeki konumu: iyi bandı %40, orta %30, kötü %30
  let oran
  if (deger == null) oran = null
  else if (deger <= iyi) oran = (deger / iyi) * 40
  else if (deger <= kotu) oran = 40 + ((deger - iyi) / (kotu - iyi)) * 30
  else oran = Math.min(99, 70 + ((deger - kotu) / kotu) * 30)

  return (
    <div className="rounded-card px-4 py-3.5" style={{ background: '#ffffff' }}>
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <p className="text-label-md font-medium" style={{ color: '#4a5068' }}>{ad}</p>
          <p className="text-label-sm mt-0.5" style={{ color: '#9da5be' }}>{aciklama}</p>
        </div>
        <span style={{ color: renk, fontSize: 10, lineHeight: '18px' }}>{SKOR_SEKIL[durum]}</span>
      </div>
      <p className="font-semibold font-mono mb-2.5" style={{ fontSize: 21, color: renk }}>
        {deger == null ? '—' : birim === 'ms' ? ms(deger) : deger.toFixed(3).replace('.', ',')}
      </p>
      <div className="relative rounded-full overflow-hidden" style={{ height: 4, background: '#eef0f6' }}>
        <div style={{ position: 'absolute', left: 0, width: '40%', height: '100%', background: 'rgba(12,206,107,0.35)' }} />
        <div style={{ position: 'absolute', left: '40%', width: '30%', height: '100%', background: 'rgba(255,164,0,0.35)' }} />
        <div style={{ position: 'absolute', left: '70%', width: '30%', height: '100%', background: 'rgba(255,78,66,0.35)' }} />
        {oran != null && (
          <div style={{
            position: 'absolute', left: `${oran}%`, top: -2, width: 3, height: 8,
            background: renk, borderRadius: 2, transform: 'translateX(-50%)',
            transition: 'left 0.6s ease',
          }} />
        )}
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-label-sm" style={{ color: '#9da5be' }}>
          {birim === 'ms' ? ms(iyi) : iyi}
        </span>
        <span className="text-label-sm" style={{ color: '#9da5be' }}>
          {birim === 'ms' ? ms(kotu) : kotu}
        </span>
      </div>
    </div>
  )
}

// ── TTFB faz dökümü ─────────────────────────────────────────────────────────
function FazDokumu({ medyan }) {
  if (!medyan) return null
  const fazlar = [
    { ad: 'DNS', deger: medyan.dns_ms, renk: '#a855f7' },
    { ad: 'TCP', deger: medyan.tcp_ms, renk: '#06b6d4' },
    { ad: 'TLS', deger: medyan.tls_ms, renk: '#f5b642' },
    { ad: 'Sunucu', deger: medyan.sunucu_ms, renk: '#4a6cf7' },
  ]
  const toplam = fazlar.reduce((a, f) => a + (f.deger || 0), 0) || 1

  return (
    <div className="rounded-card px-5 py-4" style={{ background: '#ffffff' }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Server className="w-3.5 h-3.5" style={{ color: '#3b7eff' }} />
          <p className="text-label-md font-medium" style={{ color: '#4a5068' }}>
            Bağlantı fazları — sorun nerede?
          </p>
        </div>
        <span className="text-label-sm font-mono" style={{ color: '#6b7388' }}>
          {medyan.olcum_sayisi} ölçümün medyanı
        </span>
      </div>

      <div className="flex rounded-full overflow-hidden mb-3" style={{ height: 10 }}>
        {fazlar.map(f => (
          <div key={f.ad} title={`${f.ad}: ${ms(f.deger)}`}
               style={{ width: `${((f.deger || 0) / toplam) * 100}%`, background: f.renk }} />
        ))}
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {fazlar.map(f => (
          <div key={f.ad}>
            <div className="flex items-center gap-1.5">
              <span style={{ width: 8, height: 8, borderRadius: 2, background: f.renk }} />
              <span className="text-label-sm" style={{ color: '#6b7388' }}>{f.ad}</span>
            </div>
            <p className="text-body-sm font-mono font-medium mt-0.5" style={{ color: '#1a1d2e' }}>
              {ms(f.deger)}
            </p>
          </div>
        ))}
      </div>
      <p className="text-label-sm mt-3" style={{ color: '#9da5be' }}>
        Gecikme <strong style={{ color: '#6b7388' }}>Sunucu</strong> fazındaysa yük uygulama/veritabanı
        tarafındadır; DNS veya TLS'teyse altyapı ayarıdır.
      </p>
    </div>
  )
}

// ── Türkçe öneri paneli (QuickCheck'teki ErrorAnalysisPanel deseni) ──────────
function OneriPaneli({ oneri }) {
  const [acik, setAcik] = useState(false)
  const [kopyalandi, setKopyalandi] = useState(false)

  const kopyala = async () => {
    await navigator.clipboard.writeText(oneri.draft)
    setKopyalandi(true)
    toast.success('Taslak kopyalandı')
    setTimeout(() => setKopyalandi(false), 2000)
  }

  return (
    <div className="flex flex-col gap-3 mt-3">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="rounded-card overflow-hidden" style={{ background: '#f7f8fc' }}>
          <div className="flex items-center gap-2 px-4 py-2.5" style={{ borderBottom: '1px solid rgba(0,6,30,0.06)' }}>
            <Info className="w-3.5 h-3.5" style={{ color: '#ffb786' }} />
            <p className="text-label-md font-medium" style={{ color: '#ffb786' }}>Olası Nedenler</p>
          </div>
          <div className="px-4 py-3 flex flex-col gap-2">
            {oneri.causes.map((c, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-label-sm font-mono mt-0.5 flex-shrink-0" style={{ color: '#9da5be' }}>
                  {String(i + 1).padStart(2, '0')}
                </span>
                <p className="text-body-sm" style={{ color: '#4a5068' }}>{c}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-card overflow-hidden" style={{ background: '#f7f8fc' }}>
          <div className="flex items-center gap-2 px-4 py-2.5" style={{ borderBottom: '1px solid rgba(0,6,30,0.06)' }}>
            <Wrench className="w-3.5 h-3.5" style={{ color: '#3b7eff' }} />
            <p className="text-label-md font-medium" style={{ color: '#3b7eff' }}>Sen Ne Yapacaksın</p>
          </div>
          <div className="px-4 py-3 flex flex-col gap-2.5">
            {oneri.tech_steps.map((s, i) => (
              <div key={i} className="flex items-start gap-2.5">
                <div className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0 mt-0.5"
                     style={{ background: 'rgba(59,127,255,0.09)' }}>
                  <span className="text-label-sm font-medium" style={{ color: '#3b7eff' }}>{i + 1}</span>
                </div>
                <p className="text-body-sm font-mono" style={{ color: '#4a5068', fontSize: '0.78rem' }}>{s}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded-card overflow-hidden" style={{ background: '#f7f8fc' }}>
        <button onClick={() => setAcik(!acik)}
                className="flex items-center justify-between w-full px-4 py-2.5 text-left"
                style={{ borderBottom: acik ? '1px solid rgba(0,6,30,0.06)' : 'none' }}>
          <div className="flex items-center gap-2">
            <User className="w-3.5 h-3.5" style={{ color: '#4a6cf7' }} />
            <p className="text-label-md font-medium" style={{ color: '#4a6cf7' }}>
              {oneri.customer_action ? 'Müşteri Yapacak — Rehber Metin' : 'Müşteriye Yanıt Taslağı'}
            </p>
          </div>
          {acik ? <ChevronUp className="w-4 h-4" style={{ color: '#9da5be' }} />
                : <ChevronDown className="w-4 h-4" style={{ color: '#9da5be' }} />}
        </button>
        {acik && (
          <div className="px-4 pb-3.5 pt-3">
            <p className="text-body-sm mb-3" style={{ color: '#4a5068', lineHeight: '1.7' }}>{oneri.draft}</p>
            <button onClick={kopyala} className="btn-ghost text-label-md">
              {kopyalandi ? <><Check className="w-3.5 h-3.5" style={{ color: '#4a6cf7' }} /> Kopyalandı</>
                          : <><Copy className="w-3.5 h-3.5" /> Kopyala</>}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Tek denetim satırı ──────────────────────────────────────────────────────
function DenetimSatiri({ d }) {
  const [acik, setAcik] = useState(false)
  const renk = SKOR_RENK[d.durum] || SKOR_RENK.info
  const Ikon = DURUM_IKON[d.durum] || Info
  const acilabilir = (d.ogeler && d.ogeler.length > 0) || !!d.oneri

  return (
    <div style={{ borderBottom: '1px solid rgba(0,6,30,0.05)' }}>
      <button
        onClick={() => acilabilir && setAcik(!acik)}
        className="flex items-center gap-3 w-full px-5 py-3 text-left"
        style={{ cursor: acilabilir ? 'pointer' : 'default' }}
      >
        <span style={{ color: renk, fontSize: 10, width: 10 }}>{SKOR_SEKIL[d.durum]}</span>
        <Ikon className="w-4 h-4 flex-shrink-0" style={{ color: renk }} />
        <span className="flex-1 text-body-sm font-medium min-w-0" style={{ color: '#1a1d2e' }}>
          {d.baslik}
        </span>
        {d.tasarruf_ms > 0 && (
          <span className="text-label-sm font-mono px-2 py-0.5 rounded flex-shrink-0"
                style={{ background: 'rgba(255,164,0,0.12)', color: '#d97706' }}>
            −{ms(d.tasarruf_ms)}
          </span>
        )}
        <span className="text-label-md font-mono flex-shrink-0" style={{ color: renk }}>{d.deger}</span>
        {acilabilir && (acik ? <ChevronUp className="w-3.5 h-3.5" style={{ color: '#9da5be' }} />
                             : <ChevronDown className="w-3.5 h-3.5" style={{ color: '#9da5be' }} />)}
      </button>

      {acik && (
        <div className="px-5 pb-4">
          <p className="text-body-sm mb-3" style={{ color: '#6b7388', lineHeight: 1.6 }}>{d.detay}</p>

          {d.ogeler && d.ogeler.length > 0 && (
            <div className="rounded-card overflow-hidden" style={{ background: '#f7f8fc' }}>
              <div style={{ maxHeight: 260, overflowY: 'auto' }}>
                <table className="w-full text-label-md">
                  <tbody>
                    {d.ogeler.map((o, i) => (
                      <tr key={i} style={{ borderBottom: '1px solid rgba(0,6,30,0.04)' }}>
                        {Object.entries(o).filter(([k]) => k !== 'bayt').map(([k, v], j) => (
                          <td key={k} className={j === 0 ? 'px-3 py-1.5 font-mono' : 'px-3 py-1.5 text-right whitespace-nowrap'}
                              style={{
                                color: j === 0 ? '#4a5068' : '#6b7388',
                                maxWidth: j === 0 ? 420 : undefined,
                                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                              }}
                              title={String(v)}>
                            {String(v)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {d.oneri && <OneriPaneli oneri={d.oneri} />}
        </div>
      )}
    </div>
  )
}

// ── Şelale grafiği ──────────────────────────────────────────────────────────
function Selale({ kaynaklar }) {
  const [hepsi, setHepsi] = useState(false)
  if (!kaynaklar || kaynaklar.length === 0) return null

  const bitis = Math.max(...kaynaklar.map(k => (k.baslangic || 0) + (k.sure || 0)), 1)
  const gosterilen = hepsi ? kaynaklar : kaynaklar.slice(0, 25)

  return (
    <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
      <div className="flex items-center justify-between px-5 py-3" style={{ borderBottom: '1px solid rgba(0,6,30,0.06)' }}>
        <div className="flex items-center gap-2">
          <Clock className="w-3.5 h-3.5" style={{ color: '#3b7eff' }} />
          <p className="text-label-md font-medium" style={{ color: '#4a5068' }}>
            Şelale — istek zaman çizelgesi
          </p>
        </div>
        <span className="text-label-sm font-mono" style={{ color: '#9da5be' }}>
          {kaynaklar.length} istek · {ms(bitis)}
        </span>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <div style={{ minWidth: 640 }}>
          {gosterilen.map((k, i) => {
            const sol = ((k.baslangic || 0) / bitis) * 100
            const gen = Math.max(0.4, ((k.sure || 0) / bitis) * 100)
            return (
              <div key={i} className="flex items-center gap-3 px-5 py-1"
                   style={{ borderBottom: '1px solid rgba(0,6,30,0.03)' }}>
                <span className="text-label-sm font-mono flex-shrink-0"
                      style={{
                        width: 260, color: k.ucuncu_taraf ? '#a855f7' : '#6b7388',
                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                      }}
                      title={k.url}>
                  {kisaUrl(k.url)}
                </span>
                <div className="flex-1 relative" style={{ height: 12 }}>
                  <div style={{
                    position: 'absolute', left: `${sol}%`, width: `${gen}%`, height: 8, top: 2,
                    background: tipRenk(k.tip), borderRadius: 2, minWidth: 2,
                  }} title={`${k.tip} · başlangıç ${ms(k.baslangic)} · süre ${ms(k.sure)}`} />
                </div>
                <span className="text-label-sm font-mono flex-shrink-0 text-right"
                      style={{ width: 62, color: '#9da5be' }}>
                  {bayt(k.tel_bayt)}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {kaynaklar.length > 25 && (
        <button onClick={() => setHepsi(!hepsi)} className="btn-ghost text-label-md w-full justify-center py-2.5">
          {hepsi ? `İlk 25 satırı göster` : `Tümünü göster (${kaynaklar.length})`}
        </button>
      )}

      <div className="flex flex-wrap items-center gap-3 px-5 py-2.5" style={{ borderTop: '1px solid rgba(0,6,30,0.05)' }}>
        {Object.entries({ script: 'Script', css: 'CSS', img: 'Görsel', font: 'Font', fetch: 'XHR/Fetch' }).map(([t, ad]) => (
          <div key={t} className="flex items-center gap-1.5">
            <span style={{ width: 8, height: 8, borderRadius: 2, background: tipRenk(t) }} />
            <span className="text-label-sm" style={{ color: '#9da5be' }}>{ad}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5">
          <span style={{ width: 8, height: 8, borderRadius: 2, background: '#a855f7' }} />
          <span className="text-label-sm" style={{ color: '#9da5be' }}>Mor ad = üçüncü taraf</span>
        </div>
      </div>
    </div>
  )
}

// ── Geçmiş karşılaştırma ────────────────────────────────────────────────────
function Karsilastirma({ karsilastirma, gecmis }) {
  if (!karsilastirma && (!gecmis || gecmis.length < 2)) return null

  const etiketler = { skor: 'Skor', lcp_ms: 'LCP', fcp_ms: 'FCP', tbt_ms: 'TBT', ttfb_ms: 'TTFB', cls: 'CLS' }
  const farklar = karsilastirma?.farklar || {}
  // Son 20 ölçüm, en eskiden yeniye
  const seri = (gecmis || []).slice(0, 20).reverse()
  const ADIM = 42
  const sparkW = Math.max(120, 12 + (seri.length - 1) * ADIM)
  // 0-100 skoru 42..6 piksel aralığına (üst iyi) yerleştir
  const sparkY = (skor) => 42 - (Math.max(0, Math.min(100, skor)) / 100) * 36

  return (
    <div className="rounded-card px-5 py-4" style={{ background: '#ffffff' }}>
      <div className="flex items-center gap-2 mb-3">
        <TrendingUp className="w-3.5 h-3.5" style={{ color: '#3b7eff' }} />
        <p className="text-label-md font-medium" style={{ color: '#4a5068' }}>
          Önceki ölçüme göre değişim
        </p>
      </div>

      {Object.keys(farklar).length === 0 ? (
        <p className="text-body-sm" style={{ color: '#9da5be' }}>
          Bu alan adı için ilk ölçüm — karşılaştırma bir sonraki çalıştırmada görünecek.
        </p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {Object.entries(etiketler).filter(([k]) => farklar[k]).map(([k, ad]) => {
            const f = farklar[k]
            const renk = !f.degisti ? '#9da5be' : f.iyilesme ? '#0CCE6B' : '#FF4E42'
            const Ok = !f.degisti ? Minus : f.iyilesme ? TrendingDown : TrendingUp
            return (
              <div key={k}>
                <p className="text-label-sm" style={{ color: '#9da5be' }}>{ad}</p>
                <div className="flex items-center gap-1 mt-0.5">
                  <Ok className="w-3 h-3" style={{ color: renk }} />
                  <span className="text-body-sm font-mono font-medium" style={{ color: renk }}>
                    {f.yuzde > 0 ? '+' : ''}{f.yuzde.toFixed(1).replace('.', ',')}%
                  </span>
                </div>
                <p className="text-label-sm font-mono mt-0.5" style={{ color: '#6b7388' }}>
                  {k === 'cls' ? f.eski?.toFixed?.(3) : Math.round(f.eski)} → {k === 'cls' ? f.yeni?.toFixed?.(3) : Math.round(f.yeni)}
                </p>
              </div>
            )
          })}
        </div>
      )}

      {seri.length >= 2 && (
        <div className="mt-4">
          <p className="text-label-sm mb-1.5" style={{ color: '#9da5be' }}>
            Skor geçmişi ({seri.length} ölçüm)
          </p>
          {/* Sabit piksel genişliği: preserveAspectRatio="none" ile esnetmek
              çizgiyi ve noktaları yatayda deforme ediyordu. */}
          <div style={{ overflowX: 'auto' }}>
            <svg width={sparkW} height="48" viewBox={`0 0 ${sparkW} 48`}>
              <polyline
                fill="none" stroke="#3b7eff" strokeWidth="2"
                strokeLinejoin="round" strokeLinecap="round"
                points={seri.map((k, i) => `${6 + i * ADIM},${sparkY(k.skor)}`).join(' ')}
              />
              {seri.map((k, i) => (
                <circle key={i} cx={6 + i * ADIM} cy={sparkY(k.skor)} r="3.5"
                        fill={SKOR_RENK[k.skor >= 90 ? 'healthy' : k.skor >= 50 ? 'warning' : 'error']}
                        stroke="#ffffff" strokeWidth="1.5">
                  <title>{`Skor ${k.skor} — ${k.zaman ? new Date(k.zaman).toLocaleString('tr-TR') : ''}`}</title>
                </circle>
              ))}
            </svg>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Saha verisi (CrUX) ──────────────────────────────────────────────────────
function SahaVerisi({ crux }) {
  if (!crux || crux.veri_yok) {
    return (
      <div className="rounded-card px-5 py-4 flex items-center gap-3" style={{ background: '#ffffff' }}>
        <Globe className="w-4 h-4 flex-shrink-0" style={{ color: '#9da5be' }} />
        <p className="text-body-sm" style={{ color: '#6b7388' }}>
          Bu adres için Chrome kullanıcı deneyimi raporunda yeterli gerçek ziyaretçi verisi yok.
          Düşük trafikli sitelerde normaldir.
        </p>
      </div>
    )
  }

  const kartlar = [
    { ad: 'LCP', deger: crux.lcp_ms, esik: [2500, 4000], birim: 'ms' },
    { ad: 'INP', deger: crux.inp_ms, esik: [200, 500], birim: 'ms' },
    { ad: 'CLS', deger: crux.cls, esik: [0.1, 0.25], birim: 'cls' },
    { ad: 'FCP', deger: crux.fcp_ms, esik: [1800, 3000], birim: 'ms' },
    { ad: 'TTFB', deger: crux.ttfb_ms, esik: [800, 1800], birim: 'ms' },
  ].filter(k => k.deger != null)

  return (
    <div className="rounded-card px-5 py-4" style={{ background: '#ffffff' }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Globe className="w-3.5 h-3.5" style={{ color: '#3b7eff' }} />
          <p className="text-label-md font-medium" style={{ color: '#4a5068' }}>
            Gerçek kullanıcı verisi (CrUX, son 28 gün, 75. persentil)
          </p>
        </div>
        <span className="text-label-sm px-2 py-0.5 rounded"
              style={{ background: 'rgba(59,127,255,0.09)', color: '#3b7eff' }}>
          {crux.kapsam}
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {kartlar.map(k => {
          const durum = k.deger <= k.esik[0] ? 'healthy' : k.deger <= k.esik[1] ? 'warning' : 'error'
          return (
            <div key={k.ad}>
              <p className="text-label-sm" style={{ color: '#9da5be' }}>{k.ad}</p>
              <p className="font-mono font-semibold" style={{ fontSize: 17, color: SKOR_RENK[durum] }}>
                {k.birim === 'ms' ? ms(k.deger) : k.deger.toFixed(3).replace('.', ',')}
              </p>
            </div>
          )
        })}
      </div>
      {crux.kapsam === 'Origin geneli' && (
        <p className="text-label-sm mt-3" style={{ color: '#9da5be' }}>
          Bu sayfa için yeterli veri yoktu; site genelinin ortalaması gösteriliyor.
          Origin verisi ağırlıklı olarak anasayfayı yansıtır.
        </p>
      )}
    </div>
  )
}

// ── Strateji paneli ─────────────────────────────────────────────────────────
function StratejiPaneli({ v, baglanti, notlar, googleEtkin }) {
  const firsatlar = v.denetimler.filter(d => d.grup === 'firsat')
  const teshisler = v.denetimler.filter(d => d.grup !== 'firsat')
  const [teshisAcik, setTeshisAcik] = useState(false)

  const m = v.metrikler
  const md = v.metrik_durumlari

  return (
    <div className="flex flex-col gap-5">
      {/* Skor + ekran görüntüsü */}
      <div className="rounded-card px-6 py-5 flex flex-col sm:flex-row items-center gap-6" style={{ background: '#ffffff' }}>
        <SkorGauge skor={v.skor} durum={v.skor_durumu} />
        <div className="flex-1 min-w-0">
          <p className="text-title-md font-semibold mb-1" style={{ color: '#1a1d2e' }}>
            Performans skoru
          </p>
          <p className="text-body-sm mb-2" style={{ color: '#6b7388', lineHeight: 1.6 }}>
            {v.baslik && <span className="font-medium">{v.baslik} · </span>}
            {v.kaynak_sayisi} istek · {bayt(v.toplam_bayt)} · {v.dom_dugum_sayisi} DOM düğümü
          </p>
          {v.psi?.skor != null && (
            <div className="flex items-center gap-2 mb-2">
              <span className="text-label-md" style={{ color: '#6b7388' }}>Google PSI resmî skoru:</span>
              <span className="font-mono font-semibold text-body-md"
                    style={{ color: SKOR_RENK[v.psi.skor >= 90 ? 'healthy' : v.psi.skor >= 50 ? 'warning' : 'error'] }}>
                {v.psi.skor}
              </span>
              <span className="text-label-sm" style={{ color: '#9da5be' }}>
                (Lighthouse {v.psi.lighthouse_surumu})
              </span>
            </div>
          )}
          {v.psi?.hata && (
            <p className="text-label-md mb-2" style={{ color: '#ffb786' }}>Google katmanı: {v.psi.hata}</p>
          )}
          <p className="text-label-sm" style={{ color: '#9da5be', lineHeight: 1.6 }}>
            {notlar?.speed_index} {notlar?.kisitlama}
          </p>
        </div>
        {v.ekran_goruntusu && (
          <img src={v.ekran_goruntusu} alt="Sayfa görünümü"
               className="rounded-btn flex-shrink-0"
               style={{ width: 132, border: '1px solid rgba(0,6,30,0.1)' }} />
        )}
      </div>

      {/* Core Web Vitals */}
      <div>
        <p className="text-label-sm font-medium uppercase tracking-wider mb-2.5" style={{ color: '#9da5be' }}>
          Laboratuvar metrikleri
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <MetrikKart ad="LCP" aciklama="En büyük içerik boyaması" deger={m.lcp_ms} durum={md.lcp_ms} esikler={[2500, 4000]} />
          <MetrikKart ad="CLS" aciklama="Düzen kayması" deger={m.cls} durum={md.cls} esikler={[0.1, 0.25]} birim="cls" />
          <MetrikKart ad="TBT" aciklama="Toplam engelleme (INP vekili)" deger={m.tbt_ms} durum={md.tbt_ms} esikler={[200, 600]} />
          <MetrikKart ad="FCP" aciklama="İlk içerik boyaması" deger={m.fcp_ms} durum={md.fcp_ms} esikler={[1800, 3000]} />
          <MetrikKart ad="TTFB" aciklama="Sunucu yanıtı (gerçek ağ)" deger={m.ttfb_ms} durum={md.ttfb_ms} esikler={[800, 1800]} />
        </div>
        <p className="text-label-sm mt-2" style={{ color: '#9da5be' }}>{notlar?.inp}</p>
      </div>

      <FazDokumu medyan={baglanti?.medyan} />

      {googleEtkin && <SahaVerisi crux={v.crux} />}

      <Karsilastirma karsilastirma={v.karsilastirma} gecmis={v.gecmis} />

      {/* Fırsatlar */}
      {firsatlar.length > 0 && (
        <div>
          <p className="text-label-sm font-medium uppercase tracking-wider mb-2.5" style={{ color: '#9da5be' }}>
            Fırsatlar — tahmini kazanca göre sıralı
          </p>
          <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
            {firsatlar.map(d => <DenetimSatiri key={d.id} d={d} />)}
          </div>
        </div>
      )}

      {/* PSI fırsatları (varsa) */}
      {v.psi?.firsatlar?.length > 0 && (
        <div>
          <p className="text-label-sm font-medium uppercase tracking-wider mb-2.5" style={{ color: '#9da5be' }}>
            Google Lighthouse bulguları
          </p>
          <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
            {v.psi.firsatlar.map(f => (
              <div key={f.id} className="flex items-center gap-3 px-5 py-2.5"
                   style={{ borderBottom: '1px solid rgba(0,6,30,0.05)' }}>
                <span style={{ color: SKOR_RENK[f.durum], fontSize: 10 }}>{SKOR_SEKIL[f.durum]}</span>
                <span className="flex-1 text-body-sm min-w-0" style={{ color: '#1a1d2e' }}>{f.baslik}</span>
                {f.tasarruf_ms > 0 && (
                  <span className="text-label-sm font-mono px-2 py-0.5 rounded"
                        style={{ background: 'rgba(255,164,0,0.12)', color: '#d97706' }}>
                    −{ms(f.tasarruf_ms)}
                  </span>
                )}
                <span className="text-label-md font-mono" style={{ color: '#6b7388' }}>{f.deger}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <Selale kaynaklar={v.kaynaklar} />

      {/* Teşhisler */}
      <div>
        <button onClick={() => setTeshisAcik(!teshisAcik)}
                className="flex items-center gap-2 mb-2.5">
          <p className="text-label-sm font-medium uppercase tracking-wider" style={{ color: '#9da5be' }}>
            Teşhisler ({teshisler.length})
          </p>
          {teshisAcik ? <ChevronUp className="w-3.5 h-3.5" style={{ color: '#9da5be' }} />
                      : <ChevronDown className="w-3.5 h-3.5" style={{ color: '#9da5be' }} />}
        </button>
        {teshisAcik && (
          <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
            {teshisler.map(d => <DenetimSatiri key={d.id} d={d} />)}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Ana bileşen ─────────────────────────────────────────────────────────────
export default function SiteSpeed() {
  const [loading, setLoading] = useState(false)
  const [ilerleme, setIlerleme] = useState({ ilerleme: 0, adim: '' })
  const [result, setResult] = useState(null)
  const [strateji, setStrateji] = useState('mobile')
  const [googleEtkin, setGoogleEtkin] = useState(false)
  const { target, commitTarget } = useTarget()
  const yoklamaRef = useRef(null)

  useEffect(() => {
    axios.get('/api/site-speed/durum')
      .then(r => setGoogleEtkin(!!r.data.google_etkin))
      .catch(() => {})
    // Sekme değişince yoklamayı bırak — arka planda dönen interval sızıntıdır
    return () => { if (yoklamaRef.current) clearInterval(yoklamaRef.current) }
  }, [])

  const run = async (d) => {
    setLoading(true)
    setResult(null)
    setIlerleme({ ilerleme: 0, adim: 'Ölçüm sıraya alınıyor…' })

    let isId
    try {
      const res = await axios.post('/api/site-speed/run', { domain: d })
      isId = res.data.is_id
    } catch (err) {
      setLoading(false)
      toast.error(apiHataMesaji(err, 'Ölçüm başlatılamadı'))
      return
    }

    if (yoklamaRef.current) clearInterval(yoklamaRef.current)
    yoklamaRef.current = setInterval(async () => {
      try {
        const { data } = await axios.get(`/api/site-speed/job/${isId}`)
        setIlerleme({ ilerleme: data.ilerleme, adim: data.adim })

        if (data.durum === 'bitti') {
          clearInterval(yoklamaRef.current)
          yoklamaRef.current = null
          setResult(data.sonuc)
          setLoading(false)
        } else if (data.durum === 'hata') {
          clearInterval(yoklamaRef.current)
          yoklamaRef.current = null
          setLoading(false)
          toast.error(data.hata || 'Ölçüm başarısız')
        }
      } catch (err) {
        clearInterval(yoklamaRef.current)
        yoklamaRef.current = null
        setLoading(false)
        toast.error(apiHataMesaji(err, 'Ölçüm durumu okunamadı'))
      }
    }, 1200)
  }

  // autoRun:false — ölçüm pahalı (tarayıcı başlatır, 5/dk sınırlı);
  // yalnızca açık Enter/Çalıştır ile tetiklenir
  useCommittedTarget(run, { autoRun: false })

  const aktif = result?.stratejiler?.[strateji]

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Başlık */}
      <div className="px-8 pt-8 pb-6">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-btn flex items-center justify-center"
               style={{ background: 'linear-gradient(135deg, rgba(12,206,107,0.18) 0%, rgba(59,127,255,0.15) 100%)' }}>
            <Gauge className="w-4 h-4" style={{ color: '#3b7eff' }} />
          </div>
          <h1 className="text-headline-md font-semibold" style={{ color: '#1a1d2e', letterSpacing: '-0.01em' }}>
            Site Hızı
          </h1>
        </div>
        <p className="text-body-md" style={{ color: '#6b7388' }}>
          Gerçek tarayıcıyla mobil ve masaüstü performans ölçümü — Core Web Vitals,
          şelale, sunucu fazları ve Türkçe çözüm önerileri
        </p>
      </div>

      {/* Çalıştır */}
      <div className="px-8 pb-6">
        <div className="flex items-center gap-3 flex-wrap">
          <button onClick={commitTarget} disabled={loading || !target.trim()} autoFocus
                  className="btn-primary flex-shrink-0 flex items-center gap-2">
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Ölçülüyor…</>
              : <><Zap className="w-4 h-4" /> {target.trim() ? `${target.trim()} hızını ölç` : 'Hız Testi Yap'}</>}
          </button>
          {!target.trim() && (
            <p className="text-body-sm" style={{ color: '#9da5be' }}>
              Üstteki hedef çubuğuna bir alan adı yazın.
            </p>
          )}
          {googleEtkin && (
            <span className="text-label-sm px-2 py-1 rounded"
                  style={{ background: 'rgba(12,206,107,0.1)', color: '#0a9d53' }}>
              Google PSI + CrUX etkin
            </span>
          )}
        </div>
      </div>

      {/* İlerleme */}
      {loading && (
        <div className="px-8 pb-6">
          <div className="rounded-card px-5 py-4" style={{ background: '#ffffff' }}>
            <div className="flex items-center justify-between mb-2.5">
              <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>{ilerleme.adim}</p>
              <span className="text-label-md font-mono" style={{ color: '#3b7eff' }}>%{ilerleme.ilerleme}</span>
            </div>
            <div className="w-full rounded-full overflow-hidden" style={{ height: 6, background: '#eef0f6' }}>
              <div className="h-full rounded-full"
                   style={{
                     width: `${ilerleme.ilerleme}%`,
                     background: 'linear-gradient(90deg, #4d8eff 0%, #0CCE6B 100%)',
                     transition: 'width 0.5s ease',
                   }} />
            </div>
            <p className="text-label-sm mt-2.5" style={{ color: '#9da5be' }}>
              Gerçek bir tarayıcı sayfayı mobil ve masaüstü profillerinde yüklüyor.
              Ağ kısıtlaması uygulandığı için ölçüm 30-60 saniye sürebilir.
            </p>
          </div>
        </div>
      )}

      {/* Sonuç */}
      {result && !loading && (
        <div className="px-8 pb-10 flex flex-col gap-5 slide-up">
          {/* Özet çubuğu + strateji sekmeleri */}
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3 flex-wrap">
              <p className="text-body-sm font-mono" style={{ color: '#3b7eff' }}>{result.domain}</p>
              <span style={{ color: '#9da5be' }}>·</span>
              <p className="text-body-sm font-mono" style={{ color: '#6b7388' }}>{result.baglanti?.ip}</p>
              {result.baglanti?.cdn && (
                <>
                  <span style={{ color: '#9da5be' }}>·</span>
                  <p className="text-body-sm" style={{ color: '#6b7388' }}>{result.baglanti.cdn}</p>
                </>
              )}
              <a href={`https://${result.domain}`} target="_blank" rel="noopener noreferrer"
                 className="btn-ghost text-label-sm py-1 px-2">
                <ExternalLink className="w-3.5 h-3.5" /> Aç
              </a>
            </div>

            <div className="flex rounded-btn overflow-hidden" style={{ border: '1px solid rgba(0,6,30,0.1)' }}>
              {[
                { id: 'mobile', ad: 'Mobil', Ikon: Smartphone },
                { id: 'desktop', ad: 'Masaüstü', Ikon: Monitor },
              ].map(({ id, ad, Ikon }) => {
                const v = result.stratejiler?.[id]
                const secili = strateji === id
                return (
                  <button key={id} onClick={() => setStrateji(id)}
                          className="flex items-center gap-2 px-4 py-2 text-label-md font-medium"
                          style={{
                            background: secili ? 'rgba(37,99,235,0.09)' : '#ffffff',
                            color: secili ? '#2563eb' : '#6b7388',
                          }}>
                    <Ikon className="w-3.5 h-3.5" />
                    {ad}
                    {v && (
                      <span className="font-mono font-semibold"
                            style={{ color: SKOR_RENK[v.skor_durumu] }}>{v.skor}</span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          {aktif
            ? <StratejiPaneli v={aktif} baglanti={result.baglanti}
                              notlar={result.notlar} googleEtkin={result.google_etkin} />
            : <p className="text-body-sm" style={{ color: '#9da5be' }}>Bu strateji için sonuç yok.</p>}
        </div>
      )}

      {/* Boş ekran */}
      {!result && !loading && (
        <div className="flex-1 flex flex-col items-center justify-center pb-20">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
               style={{ background: 'rgba(12,206,107,0.07)' }}>
            <Gauge className="w-7 h-7 opacity-40" style={{ color: '#0CCE6B' }} />
          </div>
          <p className="text-title-md font-medium mb-1" style={{ color: '#4a5068' }}>Alan adı girin</p>
          <p className="text-body-md text-center max-w-sm" style={{ color: '#6b7388' }}>
            Sayfa gerçek bir Chromium'da mobil ve masaüstü profillerinde yüklenir;
            skor, Core Web Vitals, şelale ve çözüm önerileri çıkarılır.
          </p>
        </div>
      )}
    </div>
  )
}
