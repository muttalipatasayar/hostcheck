import { useState, useRef } from 'react'
import {
  Search, Globe, Building2, Network, MapPin, Clock,
  Loader2, X, Server, Smartphone, ShieldAlert, Wifi,
  ExternalLink, Copy, Check, Info,
} from 'lucide-react'
import toast from 'react-hot-toast'
import axios from 'axios'

// ISO 3166-1 alpha-2 → bayrak emoji
const flagEmoji = (code) => {
  if (!code || code.length !== 2) return '🌐'
  return code.toUpperCase().replace(/./g, c =>
    String.fromCodePoint(c.charCodeAt(0) + 0x1F1A5)
  )
}

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    toast.success('Kopyalandı')
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={copy}
      className="p-1 rounded opacity-50 hover:opacity-100 transition-opacity"
      style={{ color: '#adc6ff' }}
      title="Kopyala"
    >
      {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  )
}

function InfoRow({ icon: Icon, label, value, mono, copy, color }) {
  if (!value) return null
  return (
    <div className="flex items-start gap-3 py-2.5" style={{ borderBottom: '1px solid rgba(66,71,84,0.15)' }}>
      <div
        className="w-7 h-7 rounded flex items-center justify-center flex-shrink-0 mt-0.5"
        style={{ background: 'rgba(173,198,255,0.07)' }}
      >
        <Icon className="w-3.5 h-3.5" style={{ color: '#424754' }} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-label-sm" style={{ color: '#424754' }}>{label}</p>
        <p
          className={`text-body-sm font-medium mt-0.5 ${mono ? 'font-mono' : ''}`}
          style={{ color: color || '#e3e5ef', wordBreak: 'break-all' }}
        >
          {value}
        </p>
      </div>
      {copy && <CopyBtn text={value} />}
    </div>
  )
}

const NETWORK_TAGS = [
  {
    key: 'is_hosting',
    label: 'Datacenter / Hosting',
    icon: Server,
    color: '#adc6ff',
    bg: 'rgba(173,198,255,0.1)',
    border: 'rgba(173,198,255,0.2)',
    desc: 'Bu IP bir veri merkezi veya hosting firmasına ait',
  },
  {
    key: 'is_proxy',
    label: 'VPN / Proxy',
    icon: ShieldAlert,
    color: '#f5d37a',
    bg: 'rgba(245,211,122,0.1)',
    border: 'rgba(245,211,122,0.2)',
    desc: 'Bu IP VPN, proxy veya Tor çıkış noktası olarak işaretlenmiş',
  },
  {
    key: 'is_mobile',
    label: 'Mobil Ağ',
    icon: Smartphone,
    color: '#a8d5a2',
    bg: 'rgba(168,213,162,0.1)',
    border: 'rgba(168,213,162,0.2)',
    desc: 'Bu IP mobil operatör ağına ait',
  },
]

export default function IPLookup() {
  const [query, setQuery]   = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState(null)
  const [error, setError]     = useState('')
  const inputRef = useRef(null)

  const lookup = async () => {
    const q = query.trim()
    if (!q) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const res = await axios.get('/api/ip/lookup', { params: { q } })
      setResult(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Sorgulama başarısız')
    } finally {
      setLoading(false)
    }
  }

  const handleKey = (e) => { if (e.key === 'Enter') lookup() }

  const mapsUrl = result?.lat && result?.lon
    ? `https://www.google.com/maps?q=${result.lat},${result.lon}`
    : null

  return (
    <div className="flex flex-col h-full overflow-y-auto">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="px-8 pt-8 pb-6">
        <div className="flex items-center gap-3 mb-1">
          <div
            className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg,rgba(168,213,162,.2) 0%,rgba(100,200,120,.15) 100%)' }}
          >
            <Globe className="w-4 h-4" style={{ color: '#a8d5a2' }} />
          </div>
          <h1 className="text-headline-md font-semibold" style={{ color: '#e3e5ef', letterSpacing: '-0.01em' }}>
            IP Sorgulama
          </h1>
        </div>
        <p className="text-body-md" style={{ color: '#8d9099' }}>
          IP adresi veya alan adı sorgula — firma, ülke, ASN ve ağ türü bilgisi
        </p>
      </div>

      {/* ── Search ─────────────────────────────────────────────────────────── */}
      <div className="px-8 pb-6">
        <div
          className="flex items-center gap-3 rounded-card px-4 py-3"
          style={{ background: '#1a1c20' }}
        >
          <Search className="w-4 h-4 flex-shrink-0" style={{ color: '#8d9099' }} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKey}
            placeholder="8.8.8.8 · 2001:4860:4860::8888 · example.com"
            className="flex-1 bg-transparent outline-none text-title-md font-mono"
            style={{ color: '#e3e5ef', caretColor: '#a8d5a2' }}
            autoFocus
            spellCheck={false}
          />
          {query && (
            <button onClick={() => { setQuery(''); setResult(null); setError('') }}
              className="p-1 rounded hover:opacity-70" style={{ color: '#424754' }}>
              <X className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={lookup}
            disabled={loading || !query.trim()}
            className="btn-primary flex-shrink-0"
            style={{ background: loading ? undefined : 'linear-gradient(135deg,#a8d5a2,#6dc87a)' }}
          >
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Sorgulanıyor…</>
              : <><Search className="w-4 h-4" /> Sorgula</>
            }
          </button>
        </div>
      </div>

      {/* ── Error ──────────────────────────────────────────────────────────── */}
      {error && (
        <div className="px-8 pb-4">
          <div
            className="rounded-btn px-4 py-3 flex items-center gap-2 text-body-sm"
            style={{ background: 'rgba(255,180,171,0.08)', color: '#ffb4ab', border: '1px solid rgba(255,180,171,0.2)' }}
          >
            <X className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        </div>
      )}

      {/* ── Skeleton ───────────────────────────────────────────────────────── */}
      {loading && (
        <div className="px-8">
          <div className="rounded-card overflow-hidden animate-pulse" style={{ background: '#1a1c20' }}>
            <div className="px-6 py-5 flex items-center gap-4"
              style={{ borderBottom: '1px solid rgba(66,71,84,0.2)' }}>
              <div className="w-16 h-16 rounded-card" style={{ background: '#282a2e' }} />
              <div className="flex flex-col gap-2 flex-1">
                <div className="h-5 w-40 rounded" style={{ background: '#282a2e' }} />
                <div className="h-4 w-28 rounded" style={{ background: '#1e2128' }} />
              </div>
            </div>
            {[1,2,3,4,5].map(i => (
              <div key={i} className="flex items-center gap-3 px-6 py-3"
                style={{ borderBottom: '1px solid rgba(66,71,84,0.1)' }}>
                <div className="w-7 h-7 rounded" style={{ background: '#282a2e' }} />
                <div className="flex flex-col gap-1.5 flex-1">
                  <div className="h-3 w-24 rounded" style={{ background: '#1e2128' }} />
                  <div className="h-4 w-52 rounded" style={{ background: '#282a2e' }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Result ─────────────────────────────────────────────────────────── */}
      {result && !loading && (
        <div className="px-8 pb-10 flex flex-col gap-4">

          {/* ── Hero card ── */}
          <div
            className="rounded-card overflow-hidden"
            style={{ background: '#1a1c20', border: '1px solid rgba(66,71,84,0.35)' }}
          >
            {/* Top bar */}
            <div
              className="px-6 py-5 flex items-center gap-5 flex-wrap"
              style={{ background: '#16181d', borderBottom: '1px solid rgba(66,71,84,0.25)' }}
            >
              {/* Flag + country */}
              <div
                className="w-16 h-16 rounded-card flex items-center justify-center flex-shrink-0 text-4xl select-none"
                style={{ background: '#111317' }}
                title={result.country || ''}
              >
                {flagEmoji(result.country_code)}
              </div>

              <div className="flex-1 min-w-0">
                {/* IP address */}
                <div className="flex items-center gap-2 mb-1">
                  <p className="text-title-md font-mono font-semibold" style={{ color: '#a8d5a2' }}>
                    {result.query}
                  </p>
                  <CopyBtn text={result.query} />
                </div>
                {/* Country */}
                <p className="text-body-md font-medium" style={{ color: '#e3e5ef' }}>
                  {result.country || '—'}
                  {result.city && (
                    <span style={{ color: '#8d9099' }}> · {result.city}{result.region ? `, ${result.region}` : ''}</span>
                  )}
                </p>
              </div>

              {/* Map link */}
              {mapsUrl && (
                <a
                  href={mapsUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-ghost flex items-center gap-1.5 text-body-sm flex-shrink-0"
                >
                  <MapPin className="w-3.5 h-3.5" />
                  Haritada Gör
                  <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>

            {/* Details grid */}
            <div className="px-6 py-1">
              <InfoRow
                icon={Building2}
                label="ISP / Servis Sağlayıcı"
                value={result.isp}
                copy
              />
              <InfoRow
                icon={Building2}
                label="Kuruluş (Organization)"
                value={result.org !== result.isp ? result.org : null}
                copy
              />
              <InfoRow
                icon={Network}
                label="ASN"
                value={result.asn ? `${result.asn}${result.asn_name ? '  —  ' + result.asn_name : ''}` : null}
                mono
                color="#adc6ff"
              />
              <InfoRow
                icon={MapPin}
                label="Konum"
                value={[result.city, result.region, result.country].filter(Boolean).join(', ') || null}
              />
              <InfoRow
                icon={Clock}
                label="Saat Dilimi"
                value={result.timezone}
                mono
              />
              {result.lat && result.lon && (
                <InfoRow
                  icon={MapPin}
                  label="Koordinat"
                  value={`${result.lat?.toFixed(4)}, ${result.lon?.toFixed(4)}`}
                  mono
                  color="#424754"
                />
              )}
            </div>
          </div>

          {/* ── Network type tags ── */}
          {(result.is_hosting || result.is_proxy || result.is_mobile) && (
            <div>
              <p
                className="text-label-sm font-medium uppercase tracking-wider mb-2.5"
                style={{ color: '#424754' }}
              >
                Ağ Özellikleri
              </p>
              <div className="flex flex-wrap gap-3">
                {NETWORK_TAGS.filter(t => result[t.key]).map(t => (
                  <div
                    key={t.key}
                    className="flex items-start gap-3 px-4 py-3 rounded-card flex-1 min-w-52"
                    style={{
                      background: t.bg,
                      border: `1px solid ${t.border}`,
                    }}
                  >
                    <div
                      className="w-8 h-8 rounded-btn flex items-center justify-center flex-shrink-0 mt-0.5"
                      style={{ background: `${t.bg}` }}
                    >
                      <t.icon className="w-4 h-4" style={{ color: t.color }} />
                    </div>
                    <div>
                      <p className="text-body-sm font-semibold" style={{ color: t.color }}>
                        {t.label}
                      </p>
                      <p className="text-label-sm mt-0.5" style={{ color: '#8d9099' }}>
                        {t.desc}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Normal IP note ── */}
          {!result.is_hosting && !result.is_proxy && !result.is_mobile && (
            <div
              className="flex items-center gap-2.5 px-4 py-3 rounded-btn text-body-sm"
              style={{ background: 'rgba(168,213,162,0.06)', border: '1px solid rgba(168,213,162,0.15)' }}
            >
              <Wifi className="w-4 h-4 flex-shrink-0" style={{ color: '#a8d5a2' }} />
              <p style={{ color: '#8d9099' }}>
                Standart ev/ofis bağlantısı — VPN, proxy veya datacenter değil
              </p>
            </div>
          )}

          {/* Source note */}
          <p className="text-label-sm flex items-center gap-1.5" style={{ color: '#282a2e' }}>
            <Info className="w-3 h-3" />
            Veri kaynağı: ip-api.com
          </p>
        </div>
      )}

      {/* ── Empty state ────────────────────────────────────────────────────── */}
      {!result && !loading && !error && (
        <div className="flex-1 flex flex-col items-center justify-center pb-20">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
            style={{ background: 'rgba(168,213,162,0.06)' }}
          >
            <Globe className="w-7 h-7 opacity-30" style={{ color: '#a8d5a2' }} />
          </div>
          <p className="text-title-md font-medium mb-1" style={{ color: '#c2c6d6' }}>
            IP adresi veya alan adı girin
          </p>
          <p className="text-body-md text-center max-w-xs" style={{ color: '#8d9099' }}>
            Firma, ülke, şehir, ASN ve ağ türü bilgisi görüntülenir
          </p>
          {/* Quick examples */}
          <div className="flex flex-wrap gap-2 mt-5 justify-center">
            {['8.8.8.8', '1.1.1.1', '208.67.222.222'].map(ip => (
              <button
                key={ip}
                onClick={() => { setQuery(ip); setTimeout(lookup, 50) }}
                className="text-label-sm font-mono px-3 py-1.5 rounded-btn transition-colors"
                style={{ background: '#1a1c20', color: '#8d9099', border: '1px solid rgba(66,71,84,0.3)' }}
              >
                {ip}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
