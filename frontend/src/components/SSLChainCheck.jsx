import { useState } from 'react'
import {
  Search, Loader2, XCircle, CheckCircle2, AlertTriangle, Info,
  ChevronDown, ChevronRight, ShieldCheck, ShieldAlert, ShieldQuestion,
  Server, Download, Database, Wrench, Smartphone, Monitor, Globe,
} from 'lucide-react'
import axios from 'axios'
import { useTarget, useCommittedTarget } from '../context/TargetContext'
import CopyButton from './CopyButton'
import { apiHataMesaji } from '../lib/apiHata'

// ── Renkler ───────────────────────────────────────────────────────────────────
//
// index.css'teki açık tema paleti kullanılıyor (`.badge-*` değerleri).
// SSLChecker sekmesindeki #ffb4ab / #a8d5a2 tonları terk edilmiş KOYU temadan
// (DESIGN.md) kalma; beyaz zeminde okunmuyorlar. CLAUDE.md görsel kararlarda
// index.css'i kaynak kabul ediyor ve burası yeni bir dosya.

const STATUS_CONFIG = {
  healthy: { icon: CheckCircle2,  color: '#16a34a', dot: 'status-dot-healthy', label: 'Sağlıklı' },
  warning: { icon: AlertTriangle, color: '#d97706', dot: 'status-dot-warning', label: 'Uyarı'    },
  error:   { icon: XCircle,       color: '#dc2626', dot: 'status-dot-error',   label: 'Hata'     },
  info:    { icon: Info,          color: '#3b7eff', dot: 'status-dot-pending', label: 'Bilgi'    },
}

const VERDICT = {
  guvenilir:  { label: 'Güvenilir',   color: '#16a34a', bg: 'rgba(34,197,94,0.10)',  icon: ShieldCheck    },
  guvenilmez: { label: 'Güvenilmez',  color: '#dc2626', bg: 'rgba(239,68,68,0.10)',  icon: ShieldAlert    },
  belirsiz:   { label: 'Belirsiz',    color: '#d97706', bg: 'rgba(245,158,11,0.10)', icon: ShieldQuestion },
  bilinmiyor: { label: 'Bilinmiyor',  color: '#6b7388', bg: 'rgba(0,6,30,0.05)',     icon: ShieldQuestion },
}

const PLATFORM_ICON = {
  android: Smartphone, android7: Smartphone, android_chrome: Smartphone,
  ios: Smartphone, chrome: Monitor, windows: Monitor, firefox: Globe,
}

const ROLE_META = {
  yaprak: { label: 'Sunucu sertifikası', color: '#2563eb', bg: 'rgba(59,127,255,0.10)' },
  ara:    { label: 'Ara sertifika',      color: '#6b7388', bg: 'rgba(0,6,30,0.05)'     },
  kök:    { label: 'Kök',                color: '#7c3aed', bg: 'rgba(124,58,237,0.10)' },
}

const SOURCE_META = {
  sunucu:          { label: 'sunucudan geldi',      color: '#16a34a', icon: Server   },
  AIA:             { label: 'AIA ile indirildi',    color: '#d97706', icon: Download },
  'güven deposu':  { label: 'güven deposundan',     color: '#6b7388', icon: Database },
}

// ── Küçük parçalar ────────────────────────────────────────────────────────────

function Pill({ text, color, bg, icon: Icon }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-label-sm font-semibold px-2.5 py-1 rounded-full flex-shrink-0"
      style={{ background: bg, color, border: `1px solid ${color}30` }}>
      {Icon && <Icon className="w-3 h-3" />}
      {text}
    </span>
  )
}

function VerdictPill({ value }) {
  const v = VERDICT[value] || VERDICT.bilinmiyor
  return <Pill text={v.label} color={v.color} bg={v.bg} icon={v.icon} />
}

function Section({ title, hint, children }) {
  return (
    <div className="rounded-card overflow-hidden" style={{ background: '#ffffff', border: '1px solid rgba(0,6,30,0.10)' }}>
      <div className="px-6 py-4" style={{ background: '#f7f8fc', borderBottom: '1px solid rgba(0,6,30,0.09)' }}>
        <p className="text-title-md font-semibold" style={{ color: '#1a1d2e' }}>{title}</p>
        {hint && <p className="text-label-md mt-0.5" style={{ color: '#6b7388' }}>{hint}</p>}
      </div>
      {children}
    </div>
  )
}

// ── Platform ızgarası — bu aracın varlık sebebi ───────────────────────────────

function PlatformRow({ p }) {
  const Icon = PLATFORM_ICON[p.key] || Monitor
  // A ve B ayrışıyorsa sebebi göstermek gerekiyor: sorunun "sunucu eksik
  // gönderiyor ama bazı istemciler kendi onarıyor" olduğunu ancak bu iki
  // sütunu yan yana görünce anlaşılıyor.
  const ayrisiyor = p.sunucu_zinciri !== p.aia_onarimli
  return (
    <div className="px-6 py-4" style={{ borderBottom: '1px solid rgba(0,6,30,0.06)' }}>
      <div className="flex items-start gap-3 flex-wrap">
        <div className="w-8 h-8 rounded-btn flex items-center justify-center flex-shrink-0"
          style={{ background: 'rgba(59,127,255,0.05)' }}>
          <Icon className="w-3.5 h-3.5" style={{ color: '#3b7eff' }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-body-sm font-semibold" style={{ color: '#1a1d2e' }}>{p.ad}</p>
            <VerdictPill value={p.sonuc} />
          </div>
          <p className="text-label-md mt-0.5" style={{ color: '#9da5be' }}>{p.kapsam}</p>
          {p.aciklama && (
            <p className="text-body-sm mt-1.5" style={{ color: '#4a5068' }}>{p.aciklama}</p>
          )}
          {ayrisiyor && (
            <div className="flex items-center gap-4 mt-2 text-label-md" style={{ color: '#6b7388' }}>
              <span>Sunucunun zinciri: <b style={{ color: (VERDICT[p.sunucu_zinciri] || VERDICT.bilinmiyor).color }}>
                {(VERDICT[p.sunucu_zinciri] || VERDICT.bilinmiyor).label}</b></span>
              <span>AIA onarımlı: <b style={{ color: (VERDICT[p.aia_onarimli] || VERDICT.bilinmiyor).color }}>
                {(VERDICT[p.aia_onarimli] || VERDICT.bilinmiyor).label}</b></span>
            </div>
          )}
          {p.not_ && (
            <p className="text-label-md mt-1.5 leading-relaxed" style={{ color: '#9da5be' }}>{p.not_}</p>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Zincir merdiveni ──────────────────────────────────────────────────────────

function ChainCert({ c, last }) {
  const [open, setOpen] = useState(false)
  const role = ROLE_META[c.role] || ROLE_META.ara
  const src = SOURCE_META[c.source] || SOURCE_META.sunucu
  const SrcIcon = src.icon
  const sorunlu = c.expired || c.not_yet_valid

  return (
    <div className="px-6 py-4" style={{ borderBottom: last ? 'none' : '1px solid rgba(0,6,30,0.06)' }}>
      <div className="flex items-start gap-3">
        {/* Merdiven çizgisi */}
        <div className="flex flex-col items-center flex-shrink-0" style={{ width: 20 }}>
          <div className="w-2 h-2 rounded-full" style={{ background: sorunlu ? '#ef4444' : '#3b7eff' }} />
          {!last && <div style={{ width: 1, flex: 1, minHeight: 28, background: 'rgba(0,6,30,0.12)', marginTop: 4 }} />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-body-sm font-semibold font-mono truncate" style={{ color: '#1a1d2e' }}>
              {c.common_name || c.subject}
            </p>
            <Pill text={role.label} color={role.color} bg={role.bg} />
            <span className="inline-flex items-center gap-1 text-label-sm" style={{ color: src.color }}>
              <SrcIcon className="w-3 h-3" />{src.label}
            </span>
          </div>

          <div className="flex items-center gap-4 mt-1 text-label-md flex-wrap" style={{ color: '#6b7388' }}>
            {c.organization && <span>{c.organization}</span>}
            <span>{c.key_algorithm}{c.key_size ? ` ${c.key_size} bit` : ''}</span>
            <span>{c.signature_algorithm}</span>
            <span style={{ color: c.expired ? '#dc2626' : c.days_remaining < 30 ? '#d97706' : '#6b7388' }}>
              {c.expired ? `${c.not_after} — SÜRESİ DOLMUŞ` : `${c.not_after} (${c.days_remaining} gün)`}
            </span>
          </div>

          <button onClick={() => setOpen(!open)}
            className="btn-ghost text-label-md py-1 px-0 mt-1 flex items-center gap-1">
            {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            Ayrıntı
          </button>

          {open && (
            <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2 text-label-md"
              style={{ color: '#6b7388' }}>
              <div className="sm:col-span-2"><b style={{ color: '#4a5068' }}>Konu:</b> <span className="font-mono break-all">{c.subject}</span></div>
              <div className="sm:col-span-2"><b style={{ color: '#4a5068' }}>Yayımlayan:</b> <span className="font-mono break-all">{c.issuer}</span></div>
              <div><b style={{ color: '#4a5068' }}>Seri:</b> <span className="font-mono">{c.serial}</span></div>
              <div><b style={{ color: '#4a5068' }}>Başlangıç:</b> {c.not_before}</div>
              <div className="sm:col-span-2"><b style={{ color: '#4a5068' }}>SHA-256:</b> <span className="font-mono break-all">{c.sha256}</span></div>
              {c.ext_key_usage?.length > 0 && <div><b style={{ color: '#4a5068' }}>EKU:</b> {c.ext_key_usage.join(', ')}</div>}
              {c.key_usage?.length > 0 && <div><b style={{ color: '#4a5068' }}>KeyUsage:</b> {c.key_usage.join(', ')}</div>}
              {c.role === 'yaprak' && <div><b style={{ color: '#4a5068' }}>Gömülü SCT:</b> {c.sct_count}</div>}
              {c.san?.length > 0 && (
                <div className="sm:col-span-2">
                  <b style={{ color: '#4a5068' }}>SAN ({c.san.length}):</b>{' '}
                  <span className="font-mono">{c.san.slice(0, 25).join(', ')}{c.san.length > 25 ? ` … +${c.san.length - 25}` : ''}</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Bulgu satırı ──────────────────────────────────────────────────────────────

function FindingRow({ f }) {
  const cfg = STATUS_CONFIG[f.status] || STATUS_CONFIG.info
  const Icon = cfg.icon
  return (
    <div className="flex items-start gap-3 px-6 py-3" style={{ borderBottom: '1px solid rgba(0,6,30,0.06)' }}>
      <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: cfg.color }} />
      <div className="flex-1 min-w-0">
        <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>{f.label}</p>
        {f.detail && <p className="text-body-sm mt-0.5 leading-relaxed" style={{ color: '#4a5068' }}>{f.detail}</p>}
        {f.fix && (
          <p className="text-label-md mt-1 flex items-start gap-1.5" style={{ color: '#2563eb' }}>
            <Wrench className="w-3 h-3 mt-0.5 flex-shrink-0" />{f.fix}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Ana bileşen ───────────────────────────────────────────────────────────────

export default function SSLChainCheck({ isActive }) {
  const [port, setPort] = useState('443')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [teknikAcik, setTeknikAcik] = useState(false)
  const { target, commitTarget } = useTarget()

  const run = async (d) => {
    if (!d) return
    setLoading(true); setError(''); setResult(null)
    try {
      const res = await axios.get('/api/ssl/chain-check', {
        params: { domain: d, port: parseInt(port, 10) || 443 },
      })
      setResult(res.data)
    } catch (err) {
      setError(apiHataMesaji(err, 'Zincir doğrulama başarısız'))
    } finally {
      setLoading(false)
    }
  }

  // autoRun:false — el sıkışma + AIA indirmeleri pahalı, yalnızca açık istekle.
  // isActive kontrolü ZORUNLU: alt sekmeler display:none ile gizleniyor,
  // unmount edilmiyor; onsuz gizli sekme de her commit'te sorgu atardı.
  useCommittedTarget((d) => { if (isActive) run(d) }, { autoRun: false })

  const durumCfg = result ? (STATUS_CONFIG[result.durum] || STATUS_CONFIG.info) : null
  const DurumIcon = durumCfg?.icon
  const teknikli = result?.platformlar?.filter(p => p.teknik) || []

  return (
    <div className="flex flex-col gap-5 max-w-4xl">
      {/* Sorgu kutusu */}
      <div className="rounded-card p-5" style={{ background: '#ffffff' }}>
        <p className="text-label-sm font-medium mb-4" style={{ color: '#6b7388' }}>
          DOĞRULANACAK ALAN ADI — ÜSTTEKİ HEDEF ÇUBUĞU
        </p>
        <div className="flex gap-3 flex-wrap items-center">
          <div style={{ width: 88 }}>
            <input type="number" className="input-field w-full text-center font-mono"
              placeholder="443" value={port} onChange={e => setPort(e.target.value)}
              min="1" max="65535" title="Port" />
          </div>
          <button onClick={commitTarget} disabled={loading || !target.trim()}
            className="btn-primary flex items-center gap-2 flex-shrink-0">
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" />Zincir doğrulanıyor…</>
              : <><Search className="w-4 h-4" />{target.trim() ? `${target.trim()} zincirini doğrula` : 'Zinciri doğrula'}</>}
          </button>
          {!target.trim() && (
            <p className="text-body-sm" style={{ color: '#9da5be' }}>
              Üstteki hedef çubuğuna bir alan adı yazın.
            </p>
          )}
        </div>
        <p className="text-label-md mt-3 leading-relaxed" style={{ color: '#9da5be' }}>
          Sunucunun gerçekten gönderdiği zinciri alır ve Apple, Android, Chrome,
          Microsoft ve Mozilla kök depolarına karşı ayrı ayrı doğrular. Android'in
          eksik ara sertifikayı kendi indirmediğini, iOS'un indirdiğini hesaba katar.
        </p>
      </div>

      {/* Hata */}
      {error && (
        <div className="rounded-btn px-4 py-3 flex items-start gap-2 text-body-sm"
          style={{ background: 'rgba(239,68,68,0.06)', color: '#dc2626', border: '1px solid rgba(239,68,68,0.2)' }}>
          <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Yükleniyor iskeleti */}
      {loading && (
        <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
          {[1, 2, 3, 4, 5].map(i => (
            <div key={i} className="flex items-center gap-4 px-6 py-4 animate-pulse"
              style={{ borderBottom: '1px solid rgba(0,6,30,0.04)' }}>
              <div className="w-8 h-8 rounded-btn" style={{ background: '#f2f4fa' }} />
              <div className="flex-1 flex flex-col gap-1.5">
                <div className="h-3 rounded w-40" style={{ background: '#f2f4fa' }} />
                <div className="h-3 rounded w-64" style={{ background: '#f0f2f8' }} />
              </div>
              <div className="h-5 w-24 rounded-full" style={{ background: '#f2f4fa' }} />
            </div>
          ))}
        </div>
      )}

      {result && (
        <>
          {/* Özet bandı */}
          <div className="rounded-card px-6 py-5 flex items-start gap-4"
            style={{
              background: '#ffffff',
              border: `1px solid ${durumCfg.color}33`,
              borderLeft: `3px solid ${durumCfg.color}`,
            }}>
            <DurumIcon className="w-5 h-5 mt-0.5 flex-shrink-0" style={{ color: durumCfg.color }} />
            <div className="flex-1 min-w-0">
              <p className="text-title-md font-semibold" style={{ color: durumCfg.color }}>{result.baslik}</p>
              <p className="text-body-md mt-1 leading-relaxed" style={{ color: '#4a5068' }}>{result.ozet}</p>
              <div className="flex items-center gap-4 mt-3 text-label-md flex-wrap" style={{ color: '#9da5be' }}>
                <span>{result.protokol} · {result.sifre_suiti}</span>
                <span>Sunucu {result.sunulan_sertifika_sayisi} sertifika gönderdi</span>
                {result.aia_ile_eklenen > 0 && (
                  <span style={{ color: '#d97706' }}>
                    {result.aia_ile_eklenen} sertifika AIA'dan indirilmek zorunda kaldı
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Platform ızgarası */}
          <Section
            title="Cihaz ve tarayıcı sonuçları"
            hint="Her platform kendi kök deposuna karşı doğrulandı. Android sistem istemcileri eksik ara sertifikayı indirmez; iOS ve Chrome indirir.">
            {result.platformlar.map(p => <PlatformRow key={p.key} p={p} />)}
          </Section>

          {/* Bulgular */}
          {result.bulgular?.length > 0 && (
            <Section title="Bulgular">
              {result.bulgular.map((f, i) => <FindingRow key={i} f={f} />)}
            </Section>
          )}

          {/* Zincir */}
          <Section
            title="Sertifika zinciri"
            hint="Yapraktan köke. 'AIA ile indirildi' etiketli sertifikaları sunucu göndermiyor — asıl sorun budur.">
            {result.zincir.map((c, i) => (
              <ChainCert key={c.sha256} c={c} last={i === result.zincir.length - 1} />
            ))}
          </Section>

          {/* Önerilen zincir */}
          {result.onerilen_pem && (
            <Section title="Sunucuya kurulacak zincir" hint={result.onerilen_pem_not}>
              <div className="px-6 py-4">
                <div className="flex justify-end mb-2">
                  <CopyButton text={result.onerilen_pem} label="fullchain.pem kopyala" />
                </div>
                <textarea readOnly rows={10} value={result.onerilen_pem}
                  className="w-full rounded-card px-4 py-3 font-mono text-xs outline-none resize-y"
                  style={{ background: '#f0f2f8', color: '#6b7388', border: '1px solid rgba(0,6,30,0.09)', lineHeight: '1.6' }} />
              </div>
            </Section>
          )}

          {/* Teknik ayrıntı — başlıkta değil ama atılmıyor da */}
          {teknikli.length > 0 && (
            <div className="rounded-card overflow-hidden" style={{ background: '#ffffff', border: '1px solid rgba(0,6,30,0.10)' }}>
              <button onClick={() => setTeknikAcik(!teknikAcik)}
                className="w-full px-6 py-3 flex items-center gap-2 text-body-sm font-medium text-left"
                style={{ color: '#6b7388' }}>
                {teknikAcik ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                Teknik ayrıntı — doğrulayıcının ham çıktısı
              </button>
              {teknikAcik && (
                <div className="px-6 pb-4 flex flex-col gap-2">
                  {teknikli.map(p => (
                    <div key={p.key} className="text-label-md">
                      <b style={{ color: '#4a5068' }}>{p.ad}:</b>{' '}
                      <span className="font-mono" style={{ color: '#6b7388' }}>{p.teknik}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Depo tazeliği */}
          {result.depo_bilgisi?.uretim_tarihi && (
            <p className="text-label-md px-1" style={{ color: '#9da5be' }}>
              Kök depoları {new Date(result.depo_bilgisi.uretim_tarihi).toLocaleDateString('tr-TR')} tarihinde
              CCADB ve AOSP'den üretildi ·{' '}
              {Object.entries(result.depo_bilgisi.sayilar || {}).map(([k, v]) => `${k} ${v}`).join(' · ')}
            </p>
          )}
        </>
      )}

      {/* Boş durum */}
      {!result && !loading && !error && (
        <div className="flex flex-col items-center justify-center py-16">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
            style={{ background: 'rgba(59,127,255,0.05)' }}>
            <ShieldCheck className="w-7 h-7 opacity-30" style={{ color: '#3b7eff' }} />
          </div>
          <p className="text-title-md font-medium mb-1" style={{ color: '#4a5068' }}>Alan adı girin</p>
          <p className="text-body-md text-center max-w-md" style={{ color: '#6b7388' }}>
            "Masaüstünde açılıyor ama telefonda güvenli değil diyor" şikâyetinin
            sebebini bulur: eksik ara sertifika, bozuk sıra, güvenilmeyen kök.
          </p>
        </div>
      )}
    </div>
  )
}
