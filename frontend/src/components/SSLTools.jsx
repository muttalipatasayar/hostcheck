import { useState, useRef } from 'react'
import {
  Shield, FileKey, Package, FilePlus2, Copy, Check,
  Download, Upload, Plus, X, CheckCircle2, XCircle,
  AlertTriangle, ChevronDown, ChevronUp, Loader2, Info,
  Search, Calendar, Clock, Building2, Globe, Lock, LockOpen,
  ShieldCheck, ShieldAlert, ShieldX, BadgeCheck, Star,
} from 'lucide-react'
import toast from 'react-hot-toast'
import axios from 'axios'

// ── Yardımcı ─────────────────────────────────────────────────────────────────

const TR_MAP = { ğ:'g',Ğ:'G',ü:'u',Ü:'U',ş:'s',Ş:'S',ı:'i',İ:'I',ö:'o',Ö:'O',ç:'c',Ç:'C' }
const sanitizeTR = (s) => s.split('').map(c => TR_MAP[c] || c).join('')
const hasTR = (s) => Object.keys(TR_MAP).some(c => s.includes(c))

function CopyButton({ text, size = 'sm' }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    toast.success('Kopyalandı')
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button onClick={copy} className="btn-ghost text-label-md py-1 px-2 flex items-center gap-1.5">
      {copied ? <><Check className="w-3.5 h-3.5" style={{ color: '#4a6cf7' }} />Kopyalandı</>
               : <><Copy className="w-3.5 h-3.5" />Kopyala</>}
    </button>
  )
}

function PemBox({ label, value, onChange, placeholder, readOnly = false, rows = 8 }) {
  const fileRef = useRef()
  const loadFile = (e) => {
    const file = e.target.files[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (ev) => onChange(ev.target.result)
    reader.readAsText(file)
    e.target.value = ''
  }
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <label className="text-label-md font-medium" style={{ color: '#4a5068' }}>{label}</label>
        <div className="flex items-center gap-1">
          {value && <CopyButton text={value} />}
          {!readOnly && (
            <>
              <input ref={fileRef} type="file" className="hidden" onChange={loadFile} />
              <button onClick={() => fileRef.current.click()} className="btn-ghost text-label-md py-1 px-2">
                <Upload className="w-3.5 h-3.5" /> Dosya Yükle
              </button>
            </>
          )}
        </div>
      </div>
      <textarea
        rows={rows}
        value={value}
        onChange={readOnly ? undefined : (e) => onChange(e.target.value)}
        readOnly={readOnly}
        placeholder={placeholder}
        className="w-full rounded-card px-4 py-3 font-mono text-xs outline-none resize-y"
        style={{
          background: '#0e1012',
          color: readOnly ? '#6b7388' : '#4a5068',
          border: '1px solid rgba(0,6,30,0.09)',
          lineHeight: '1.6',
        }}
      />
    </div>
  )
}

function Field({ label, value, highlight }) {
  if (!value) return null
  return (
    <div className="flex flex-col gap-0.5">
      <p className="text-label-sm" style={{ color: '#9da5be' }}>{label}</p>
      <p className="text-body-sm font-mono" style={{ color: highlight || '#1a1d2e' }}>{value}</p>
    </div>
  )
}

// ── Tab 0: SSL Sorgula ────────────────────────────────────────────────────────

const CERT_TYPE_META = {
  EV: {
    label: 'EV',
    full: 'Extended Validation',
    color: '#a8d5a2',
    bg: 'rgba(168,213,162,0.12)',
    desc: 'En yüksek güven seviyesi. Kurum kimliği doğrulanmış.',
  },
  OV: {
    label: 'OV',
    full: 'Organization Validated',
    color: '#3b7eff',
    bg: 'rgba(59,127,255,0.10)',
    desc: 'Orta güven seviyesi. Kurum bilgileri doğrulanmış.',
  },
  DV: {
    label: 'DV',
    full: 'Domain Validated',
    color: '#6b7388',
    bg: 'rgba(141,144,153,0.12)',
    desc: 'Temel güven. Yalnızca alan adı doğrulanmış.',
  },
}

function DaysGauge({ days, total }) {
  const pct   = Math.max(0, Math.min(100, (days / total) * 100))
  const color = days < 0 ? '#ffb4ab' : days < 30 ? '#ffb4ab' : days < 60 ? '#f5d37a' : '#a8d5a2'
  const label = days < 0 ? 'Süresi Doldu' : `${days} gün kaldı`

  // SVG donut arc
  const R = 36, C = 44, stroke = 7
  const circ = 2 * Math.PI * R
  const dash = (pct / 100) * circ

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative flex items-center justify-center" style={{ width: 96, height: 96 }}>
        <svg width="96" height="96" style={{ transform: 'rotate(-90deg)' }}>
          {/* track */}
          <circle cx={C} cy={C} r={R} fill="none"
            stroke="rgba(0,6,30,0.09)" strokeWidth={stroke} />
          {/* progress */}
          <circle cx={C} cy={C} r={R} fill="none"
            stroke={color} strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circ}`}
            style={{ transition: 'stroke-dasharray 0.6s ease' }}
          />
        </svg>
        <div className="absolute flex flex-col items-center leading-tight">
          <span className="font-bold" style={{ fontSize: 22, color, lineHeight: 1 }}>
            {days < 0 ? '0' : days > 999 ? '999+' : days}
          </span>
          <span style={{ fontSize: 10, color: '#9da5be' }}>gün</span>
        </div>
      </div>
      <span className="text-label-sm font-medium" style={{ color }}>{label}</span>
    </div>
  )
}

function StatusBadge({ isActive, isTrusted, daysRemaining }) {
  if (!isTrusted && daysRemaining > 0) {
    return (
      <div className="flex items-center gap-2.5 px-4 py-3 rounded-btn"
        style={{ background: 'rgba(245,211,122,0.1)', border: '1px solid rgba(245,211,122,0.25)' }}>
        <ShieldAlert className="w-5 h-5 flex-shrink-0" style={{ color: '#f5d37a' }} />
        <div>
          <p className="text-body-sm font-semibold" style={{ color: '#f5d37a' }}>Güvenilir Değil</p>
          <p className="text-label-sm" style={{ color: '#6b7388' }}>Sertifika CA tarafından doğrulanamadı (self-signed veya hatalı zincir)</p>
        </div>
      </div>
    )
  }
  if (daysRemaining < 0) {
    return (
      <div className="flex items-center gap-2.5 px-4 py-3 rounded-btn"
        style={{ background: 'rgba(255,180,171,0.1)', border: '1px solid rgba(255,180,171,0.25)' }}>
        <ShieldX className="w-5 h-5 flex-shrink-0" style={{ color: '#ffb4ab' }} />
        <div>
          <p className="text-body-sm font-semibold" style={{ color: '#ffb4ab' }}>Süresi Dolmuş</p>
          <p className="text-label-sm" style={{ color: '#6b7388' }}>SSL sertifikası geçerlilik süresi dolmuş, yenilenmesi gerekiyor</p>
        </div>
      </div>
    )
  }
  if (isActive && daysRemaining < 30) {
    return (
      <div className="flex items-center gap-2.5 px-4 py-3 rounded-btn"
        style={{ background: 'rgba(255,180,171,0.08)', border: '1px solid rgba(255,180,171,0.2)' }}>
        <ShieldAlert className="w-5 h-5 flex-shrink-0" style={{ color: '#ffb4ab' }} />
        <div>
          <p className="text-body-sm font-semibold" style={{ color: '#ffb4ab' }}>Yakında Sona Eriyor</p>
          <p className="text-label-sm" style={{ color: '#6b7388' }}>SSL sertifikası {daysRemaining} gün içinde sona eriyor, yenilemeyi planlayın</p>
        </div>
      </div>
    )
  }
  if (isActive) {
    return (
      <div className="flex items-center gap-2.5 px-4 py-3 rounded-btn"
        style={{ background: 'rgba(168,213,162,0.08)', border: '1px solid rgba(168,213,162,0.2)' }}>
        <ShieldCheck className="w-5 h-5 flex-shrink-0" style={{ color: '#a8d5a2' }} />
        <div>
          <p className="text-body-sm font-semibold" style={{ color: '#a8d5a2' }}>Aktif ve Güvenilir</p>
          <p className="text-label-sm" style={{ color: '#6b7388' }}>SSL sertifikası geçerli, güvenilir CA tarafından imzalanmış</p>
        </div>
      </div>
    )
  }
  return null
}

function SSLChecker() {
  const [domain, setDomain] = useState('')
  const [port,   setPort]   = useState('443')
  const [loading, setLoading] = useState(false)
  const [result,  setResult]  = useState(null)
  const [error,   setError]   = useState('')

  const check = async () => {
    const d = domain.trim()
    if (!d) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await axios.get('/api/ssl/check', {
        params: { domain: d, port: parseInt(port, 10) || 443 },
      })
      setResult(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Sorgulama başarısız')
    } finally {
      setLoading(false)
    }
  }

  const typeMeta = result ? (CERT_TYPE_META[result.cert_type] || CERT_TYPE_META.DV) : null

  return (
    <div className="flex flex-col gap-5 max-w-3xl">
      {/* Sorgu kutusu */}
      <div
        className="rounded-card p-5"
        style={{ background: '#ffffff' }}
      >
        <p className="text-label-sm font-medium mb-4" style={{ color: '#6b7388' }}>
          SORGULANACAK ALAN ADI
        </p>
        <div className="flex gap-3 flex-wrap">
          <div className="flex-1 min-w-52">
            <input
              type="text"
              className="input-field w-full"
              placeholder="example.com veya https://example.com"
              value={domain}
              onChange={e => setDomain(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && check()}
            />
          </div>
          <div style={{ width: 88 }}>
            <input
              type="number"
              className="input-field w-full text-center font-mono"
              placeholder="443"
              value={port}
              onChange={e => setPort(e.target.value)}
              min="1" max="65535"
              title="Port"
            />
          </div>
          <button
            onClick={check}
            disabled={loading || !domain.trim()}
            className="btn-primary flex items-center gap-2 flex-shrink-0"
          >
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" />Sorgulanıyor…</>
              : <><Search className="w-4 h-4" />Sorgula</>}
          </button>
        </div>
      </div>

      {/* Hata */}
      {error && (
        <div
          className="rounded-btn px-4 py-3 flex items-start gap-2 text-body-sm"
          style={{ background: 'rgba(255,180,171,0.08)', color: '#ffb4ab', border: '1px solid rgba(255,180,171,0.2)' }}
        >
          <XCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Sonuç */}
      {result && (
        <div
          className="rounded-card overflow-hidden"
          style={{ background: '#ffffff', border: '1px solid rgba(0,6,30,0.10)' }}
        >
          {/* ── Üst şerit ── */}
          <div
            className="px-6 py-4 flex items-center justify-between flex-wrap gap-3"
            style={{
              background: '#f7f8fc',
              borderBottom: '1px solid rgba(0,6,30,0.09)',
            }}
          >
            <div className="flex items-center gap-3">
              <div
                className="w-9 h-9 rounded-btn flex items-center justify-center flex-shrink-0"
                style={{
                  background: result.is_active
                    ? 'rgba(168,213,162,0.12)'
                    : 'rgba(255,180,171,0.1)',
                }}
              >
                {result.is_active
                  ? <Lock className="w-4 h-4" style={{ color: '#a8d5a2' }} />
                  : <LockOpen className="w-4 h-4" style={{ color: '#ffb4ab' }} />
                }
              </div>
              <div>
                <p className="text-body-md font-semibold" style={{ color: '#1a1d2e' }}>
                  {result.common_name || result.domain}
                </p>
                <p className="text-label-sm font-mono" style={{ color: '#9da5be' }}>
                  {result.domain}:{result.port}
                </p>
              </div>
            </div>

            {/* Badges row */}
            <div className="flex items-center gap-2 flex-wrap">
              {/* Cert type */}
              <span
                className="flex items-center gap-1.5 text-label-sm font-semibold px-2.5 py-1 rounded-full"
                style={{ background: typeMeta.bg, color: typeMeta.color, border: `1px solid ${typeMeta.color}30` }}
                title={typeMeta.full}
              >
                <BadgeCheck className="w-3.5 h-3.5" />
                {typeMeta.label} — {typeMeta.full}
              </span>

              {/* Wildcard */}
              {result.is_wildcard && (
                <span
                  className="flex items-center gap-1.5 text-label-sm font-semibold px-2.5 py-1 rounded-full"
                  style={{ background: 'rgba(212,168,255,0.12)', color: '#d4a8ff', border: '1px solid rgba(212,168,255,0.25)' }}
                >
                  <Star className="w-3.5 h-3.5" />
                  Wildcard
                </span>
              )}
            </div>
          </div>

          {/* ── Ana içerik ── */}
          <div className="px-6 py-5 flex flex-col gap-5">

            {/* Durum + Gauge */}
            <div className="flex items-start gap-5 flex-wrap">
              <div className="flex-1 min-w-52 flex flex-col gap-3">
                <StatusBadge
                  isActive={result.is_active}
                  isTrusted={result.is_trusted}
                  daysRemaining={result.days_remaining}
                />

                {/* Progress bar */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-label-sm" style={{ color: '#9da5be' }}>Geçerlilik süresi</span>
                    <span className="text-label-sm font-mono" style={{ color: '#6b7388' }}>
                      {Math.max(0, Math.round((result.days_remaining / result.total_days) * 100))}%
                    </span>
                  </div>
                  <div
                    className="w-full rounded-full overflow-hidden"
                    style={{ height: 6, background: 'rgba(0,6,30,0.12)' }}
                  >
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${Math.max(0, Math.min(100, (result.days_remaining / result.total_days) * 100))}%`,
                        background: result.days_remaining < 0 ? '#ffb4ab'
                          : result.days_remaining < 30 ? '#ffb4ab'
                          : result.days_remaining < 60 ? '#f5d37a'
                          : '#a8d5a2',
                      }}
                    />
                  </div>
                </div>
              </div>

              {/* Gauge */}
              <DaysGauge days={result.days_remaining} total={result.total_days} />
            </div>

            {/* Divider */}
            <div style={{ borderTop: '1px solid rgba(0,6,30,0.08)' }} />

            {/* Sertifika detayları */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
              {result.organization && (
                <div className="flex items-start gap-2.5">
                  <Building2 className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: '#9da5be' }} />
                  <div>
                    <p className="text-label-sm" style={{ color: '#9da5be' }}>Kuruluş (Organization)</p>
                    <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>{result.organization}</p>
                  </div>
                </div>
              )}

              {result.issuer && (
                <div className="flex items-start gap-2.5">
                  <ShieldCheck className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: '#9da5be' }} />
                  <div>
                    <p className="text-label-sm" style={{ color: '#9da5be' }}>Sertifika Yayımlayan</p>
                    <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>{result.issuer}</p>
                  </div>
                </div>
              )}

              <div className="flex items-start gap-2.5">
                <Calendar className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: '#9da5be' }} />
                <div>
                  <p className="text-label-sm" style={{ color: '#9da5be' }}>Geçerlilik Başlangıcı</p>
                  <p className="text-body-sm font-mono" style={{ color: '#c9cdd6' }}>{result.valid_from}</p>
                </div>
              </div>

              <div className="flex items-start gap-2.5">
                <Clock className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: '#9da5be' }} />
                <div>
                  <p className="text-label-sm" style={{ color: '#9da5be' }}>Geçerlilik Sonu</p>
                  <p
                    className="text-body-sm font-mono"
                    style={{
                      color: result.days_remaining < 30 ? '#ffb4ab'
                        : result.days_remaining < 60 ? '#f5d37a'
                        : '#c9cdd6',
                    }}
                  >
                    {result.valid_until}
                  </p>
                </div>
              </div>
            </div>

            {/* Sertifika türü açıklaması */}
            <div
              className="flex items-start gap-2.5 px-3 py-2.5 rounded-btn"
              style={{ background: typeMeta.bg }}
            >
              <BadgeCheck className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: typeMeta.color }} />
              <div>
                <p className="text-label-sm font-semibold" style={{ color: typeMeta.color }}>
                  {typeMeta.label} — {typeMeta.full}
                </p>
                <p className="text-label-sm" style={{ color: '#6b7388' }}>{typeMeta.desc}</p>
              </div>
            </div>

            {/* SAN listesi */}
            {result.san.length > 0 && (
              <div>
                <p className="text-label-sm mb-2.5 flex items-center gap-1.5" style={{ color: '#9da5be' }}>
                  <Globe className="w-3.5 h-3.5" />
                  Subject Alternative Names ({result.san.length})
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {result.san.map((s, i) => (
                    <span
                      key={i}
                      className="text-label-sm font-mono px-2 py-1 rounded"
                      style={{
                        background: s.startsWith('*.')
                          ? 'rgba(212,168,255,0.1)'
                          : '#f2f4fa',
                        color: s.startsWith('*.') ? '#d4a8ff' : '#3b7eff',
                      }}
                    >
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Tab 1: CSR Çözümle ───────────────────────────────────────────────────────

function CSRDecode() {
  const [csr, setCsr] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const decode = async () => {
    if (!csr.trim()) return
    setLoading(true)
    try {
      const res = await axios.post('/api/ssl/csr-decode', { csr_pem: csr })
      setResult(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'CSR çözümlenemedi')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <PemBox
        label="CSR (PEM Formatı)"
        value={csr}
        onChange={setCsr}
        placeholder={'-----BEGIN CERTIFICATE REQUEST-----\n...\n-----END CERTIFICATE REQUEST-----'}
      />

      <button
        onClick={decode}
        disabled={loading || !csr.trim()}
        className="btn-primary w-fit"
      >
        {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Çözümleniyor...</> : <><FileKey className="w-4 h-4" />CSR Çözümle</>}
      </button>

      {result && (
        <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
          {/* Başlık */}
          <div
            className="flex items-center gap-3 px-5 py-3.5"
            style={{ borderBottom: '1px solid rgba(0,6,30,0.05)' }}
          >
            {result.is_valid
              ? <CheckCircle2 className="w-4 h-4" style={{ color: '#4a6cf7' }} />
              : <XCircle className="w-4 h-4" style={{ color: '#ffb4ab' }} />}
            <p className="text-body-sm font-semibold" style={{ color: result.is_valid ? '#4a6cf7' : '#ffb4ab' }}>
              {result.is_valid ? 'İmza Geçerli — CSR Doğrulandı' : 'İmza Geçersiz'}
            </p>
            {result.key_algorithm && (
              <span
                className="ml-auto text-label-sm font-mono px-2 py-0.5 rounded"
                style={{ background: 'rgba(59,127,255,0.09)', color: '#3b7eff' }}
              >
                {result.key_algorithm} {result.key_size} bit
              </span>
            )}
          </div>

          {/* Alanlar */}
          <div className="px-5 py-4 grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
            <Field label="Common Name (CN)" value={result.common_name} highlight="#1a1d2e" />
            <Field label="Organization (O)" value={result.organization} />
            <Field label="Organization Unit (OU)" value={result.organization_unit} />
            <Field label="Country (C)" value={result.country} />
            <Field label="State / Province (ST)" value={result.state} />
            <Field label="Locality (L)" value={result.locality} />
            <Field label="E-posta" value={result.email} />
            <Field label="İmza Algoritması" value={result.signature_algorithm} />
          </div>

          {result.san.length > 0 && (
            <div className="px-5 pb-5">
              <p className="text-label-sm mb-2" style={{ color: '#9da5be' }}>Subject Alternative Names (SAN)</p>
              <div className="flex flex-wrap gap-2">
                {result.san.map((s, i) => (
                  <span key={i} className="text-label-md font-mono px-2 py-1 rounded"
                    style={{ background: '#f2f4fa', color: '#3b7eff' }}>
                    {s}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Tab 2: PFX Dönüştür ──────────────────────────────────────────────────────

function PFXConvert() {
  const [cert, setCert] = useState('')
  const [key, setKey] = useState('')
  const [ca, setCa] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  const convert = async () => {
    if (!cert.trim() || !key.trim()) {
      toast.error('Sertifika ve Private Key zorunludur')
      return
    }
    setLoading(true)
    try {
      const res = await axios.post('/api/ssl/pfx-convert', {
        cert_pem: cert,
        key_pem: key,
        ca_pem: ca || null,
        password,
      }, { responseType: 'blob' })

      // Dosya indir
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/x-pkcs12' }))
      const a = document.createElement('a')
      a.href = url
      a.download = 'certificate.pfx'
      a.click()
      URL.revokeObjectURL(url)
      toast.success('PFX dosyası indirildi')
    } catch (err) {
      // blob hata mesajı için text'e çevir
      if (err.response?.data instanceof Blob) {
        const text = await err.response.data.text()
        try { toast.error(JSON.parse(text).detail) } catch { toast.error('PFX dönüşümü başarısız') }
      } else {
        toast.error(err.response?.data?.detail || 'PFX dönüşümü başarısız')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-card px-4 py-3 flex items-start gap-2"
        style={{ background: 'rgba(59,127,255,0.05)' }}>
        <Info className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: '#3b7eff' }} />
        <p className="text-body-sm" style={{ color: '#6b7388' }}>
          Sertifika (CRT) + Private Key zorunludur. CA zinciri opsiyoneldir — CA olmadan da PFX oluşturulabilir.
        </p>
      </div>

      <PemBox label="Sertifika — CRT / PEM *" value={cert} onChange={setCert}
        placeholder={'-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----'} />
      <PemBox label="Private Key *" value={key} onChange={setKey}
        placeholder={'-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----'} />
      <PemBox label="CA Sertifika (Opsiyonel)" value={ca} onChange={setCa}
        placeholder={'-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----'} rows={5} />

      <div className="flex flex-col gap-1.5">
        <label className="text-label-md font-medium" style={{ color: '#4a5068' }}>
          PFX Şifresi (Opsiyonel)
        </label>
        <input
          type="text"
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder="Boş bırakılırsa şifresiz oluşturulur"
          className="rounded-card px-4 py-2.5 text-body-sm outline-none w-full max-w-sm"
          style={{ background: '#0e1012', color: '#1a1d2e', border: '1px solid rgba(0,6,30,0.09)' }}
        />
      </div>

      <button
        onClick={convert}
        disabled={loading || !cert.trim() || !key.trim()}
        className="btn-primary w-fit"
      >
        {loading
          ? <><Loader2 className="w-4 h-4 animate-spin" />Dönüştürülüyor...</>
          : <><Download className="w-4 h-4" />PFX Oluştur ve İndir</>}
      </button>
    </div>
  )
}

// ── Tab 3: CSR Oluştur ───────────────────────────────────────────────────────

const EMPTY_FORM = {
  common_name: '', organization: '', organization_unit: '',
  country: 'TR', state: '', locality: '', email: '',
  san_list: [], key_size: 2048,
}

// Bileşen dışında tanımlanmalı — içinde tanımlanırsa her render'da yeni tip
// oluşur ve input odağı kaybolur.
function CSRInputField({ label, value, onChange, placeholder, required, maxLength, mono }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-label-md font-medium" style={{ color: '#4a5068' }}>
        {label}{required && <span style={{ color: '#ffb4ab' }}> *</span>}
      </label>
      <input
        type="text"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        maxLength={maxLength}
        className={`rounded-card px-3 py-2 text-body-sm outline-none ${mono ? 'font-mono' : ''}`}
        style={{ background: '#0e1012', color: '#1a1d2e', border: '1px solid rgba(0,6,30,0.09)' }}
      />
      {hasTR(value || '') && (
        <p className="text-label-sm" style={{ color: '#ffb786' }}>
          ⚠ Türkçe karakterler otomatik dönüştürülecek: "{sanitizeTR(value)}"
        </p>
      )}
    </div>
  )
}

function CSRGenerate() {
  const [form, setForm] = useState(EMPTY_FORM)
  const [sanInput, setSanInput] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showKey, setShowKey] = useState(false)

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  const addSan = () => {
    const s = sanInput.trim()
    if (!s || form.san_list.includes(s)) return
    setForm(f => ({ ...f, san_list: [...f.san_list, s] }))
    setSanInput('')
  }

  const removeSan = (i) => setForm(f => ({ ...f, san_list: f.san_list.filter((_, idx) => idx !== i) }))

  const trWarningFields = ['common_name', 'organization', 'organization_unit', 'state', 'locality']
  const hasTRChar = trWarningFields.some(k => hasTR(form[k] || ''))

  const generate = async () => {
    if (!form.common_name.trim()) { toast.error('Common Name zorunludur'); return }
    setLoading(true)
    try {
      const res = await axios.post('/api/ssl/csr-generate', form)
      setResult(res.data)
      toast.success('CSR ve Private Key oluşturuldu')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'CSR oluşturulamadı')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      {hasTRChar && (
        <div className="rounded-card px-4 py-3 flex items-start gap-2"
          style={{ background: 'rgba(255,183,134,0.06)', border: '1px solid rgba(255,183,134,0.15)' }}>
          <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: '#ffb786' }} />
          <p className="text-body-sm" style={{ color: '#ffb786' }}>
            SSL sertifikaları Türkçe karakter kabul etmez. Gönderim sırasında otomatik dönüştürülecek (ğ→g, ü→u, ş→s, ı→i, ö→o, ç→c).
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <CSRInputField label="Common Name (Alan Adı)" value={form.common_name} onChange={set('common_name')} placeholder="example.com veya *.example.com" required mono />
        <CSRInputField label="Organization (Kurum Adı)" value={form.organization} onChange={set('organization')} placeholder="Şirket A.Ş." />
        <CSRInputField label="Organization Unit (Birim)" value={form.organization_unit} onChange={set('organization_unit')} placeholder="Bilgi İşlem" />
        <div className="flex flex-col gap-1.5">
          <label className="text-label-md font-medium" style={{ color: '#4a5068' }}>Ülke Kodu</label>
          <input type="text" value={form.country} onChange={set('country')} maxLength={2}
            className="rounded-card px-3 py-2 text-body-sm font-mono outline-none uppercase"
            style={{ background: '#0e1012', color: '#1a1d2e', border: '1px solid rgba(0,6,30,0.09)', maxWidth: '80px' }} />
        </div>
        <CSRInputField label="Şehir / İl" value={form.state} onChange={set('state')} placeholder="İstanbul" />
        <CSRInputField label="İlçe / Lokasyon" value={form.locality} onChange={set('locality')} placeholder="Kadıköy" />
        <CSRInputField label="E-posta (Opsiyonel)" value={form.email} onChange={set('email')} placeholder="admin@example.com" />
      </div>

      {/* Key boyutu */}
      <div className="flex flex-col gap-2">
        <p className="text-label-md font-medium" style={{ color: '#4a5068' }}>Key Boyutu</p>
        <div className="flex gap-2">
          {[2048, 4096].map(size => (
            <button key={size} onClick={() => setForm(f => ({ ...f, key_size: size }))}
              className={`px-4 py-2 rounded-card text-body-sm font-mono transition-colors ${form.key_size === size ? 'btn-primary' : 'btn-ghost'}`}>
              {size} bit{size === 2048 && ' (Önerilen)'}
            </button>
          ))}
        </div>
      </div>

      {/* SAN */}
      <div className="flex flex-col gap-2">
        <p className="text-label-md font-medium" style={{ color: '#4a5068' }}>
          Subject Alternative Names — SAN
          <span className="text-label-sm font-normal ml-2" style={{ color: '#9da5be' }}>
            (CN otomatik eklenir, www.example.com gibi alt alan adları için kullanın)
          </span>
        </p>
        <div className="flex gap-2">
          <input type="text" value={sanInput} onChange={e => setSanInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addSan()}
            placeholder="www.example.com"
            className="flex-1 rounded-card px-3 py-2 text-body-sm font-mono outline-none"
            style={{ background: '#0e1012', color: '#1a1d2e', border: '1px solid rgba(0,6,30,0.09)' }} />
          <button onClick={addSan} className="btn-ghost px-3">
            <Plus className="w-4 h-4" /> Ekle
          </button>
        </div>
        {form.san_list.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {form.san_list.map((s, i) => (
              <span key={i} className="flex items-center gap-1.5 text-label-md font-mono px-2.5 py-1 rounded"
                style={{ background: '#f2f4fa', color: '#3b7eff' }}>
                {s}
                <button onClick={() => removeSan(i)} className="opacity-60 hover:opacity-100">
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      <button onClick={generate} disabled={loading || !form.common_name.trim()} className="btn-primary w-fit">
        {loading
          ? <><Loader2 className="w-4 h-4 animate-spin" />Oluşturuluyor...</>
          : <><FilePlus2 className="w-4 h-4" />CSR ve Private Key Oluştur</>}
      </button>

      {result && (
        <div className="flex flex-col gap-4">
          <div className="rounded-card px-4 py-3 flex items-center gap-2"
            style={{ background: 'rgba(177,198,249,0.06)' }}>
            <CheckCircle2 className="w-4 h-4" style={{ color: '#4a6cf7' }} />
            <p className="text-body-sm" style={{ color: '#4a6cf7' }}>
              CSR ve Private Key başarıyla oluşturuldu. Private Key'i güvenli bir yerde saklayın!
            </p>
          </div>

          <PemBox label="CSR (Sertifika Sağlayıcısına Gönderin)" value={result.csr_pem}
            onChange={() => {}} readOnly rows={10} />

          {/* Private Key — gizli, aç/kapat */}
          <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
            <button onClick={() => setShowKey(v => !v)}
              className="flex items-center justify-between w-full px-4 py-3 text-left"
              style={{ borderBottom: showKey ? '1px solid rgba(0,6,30,0.06)' : 'none' }}>
              <div className="flex items-center gap-2">
                <Shield className="w-3.5 h-3.5" style={{ color: '#ffb786' }} />
                <p className="text-label-md font-medium" style={{ color: '#ffb786' }}>
                  Private Key — Gizli (tıkla aç/kapat)
                </p>
              </div>
              {showKey
                ? <ChevronUp className="w-4 h-4" style={{ color: '#9da5be' }} />
                : <ChevronDown className="w-4 h-4" style={{ color: '#9da5be' }} />}
            </button>
            {showKey && (
              <div className="px-4 pb-4 pt-3">
                <div className="rounded-card px-3 py-2 mb-2 flex items-center gap-2"
                  style={{ background: 'rgba(255,183,134,0.06)' }}>
                  <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#ffb786' }} />
                  <p className="text-label-sm" style={{ color: '#ffb786' }}>
                    Bu anahtarı asla paylaşmayın. Sertifika yüklenirken sadece sunucunuzda kullanın.
                  </p>
                </div>
                <PemBox label="" value={result.private_key_pem} onChange={() => {}} readOnly rows={10} />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Ana Bileşen ───────────────────────────────────────────────────────────────

const TABS = [
  { id: 'ssl-checker',  label: 'SSL Sorgula',   icon: Search    },
  { id: 'csr-decode',   label: 'CSR Çözümle',   icon: FileKey   },
  { id: 'pfx-convert',  label: 'PFX Dönüştür',  icon: Package   },
  { id: 'csr-generate', label: 'CSR Oluştur',   icon: FilePlus2 },
]

export default function SSLTools() {
  const [tab, setTab] = useState('ssl-checker')

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="px-8 pt-8 pb-6">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, rgba(173,198,255,0.2) 0%, rgba(77,142,255,0.15) 100%)' }}>
            <Shield className="w-4 h-4" style={{ color: '#3b7eff' }} />
          </div>
          <h1 className="text-headline-md font-semibold" style={{ color: '#1a1d2e', letterSpacing: '-0.01em' }}>
            SSL Araçları
          </h1>
        </div>
        <p className="text-body-md" style={{ color: '#6b7388' }}>
          CSR çözümle · PFX dönüştür · CSR oluştur
        </p>
      </div>

      {/* Tabs */}
      <div className="px-8 pb-6">
        <div className="flex gap-1 rounded-card p-1 w-fit" style={{ background: '#ffffff' }}>
          {TABS.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setTab(id)}
              className="flex items-center gap-2 px-4 py-2 rounded text-body-sm font-medium transition-all"
              style={{
                background: tab === id ? '#f2f4fa' : 'transparent',
                color: tab === id ? '#1a1d2e' : '#6b7388',
              }}>
              <Icon className="w-3.5 h-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* İçerik */}
      <div className="px-8 pb-10">
        {tab === 'ssl-checker'  && <SSLChecker />}
        {tab === 'csr-decode'   && <CSRDecode />}
        {tab === 'pfx-convert'  && <PFXConvert />}
        {tab === 'csr-generate' && <CSRGenerate />}
      </div>
    </div>
  )
}
