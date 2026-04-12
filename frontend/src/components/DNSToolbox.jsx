import { useState, useCallback, useRef } from 'react'
import {
  Search, Globe, Mail, Server, FileText, Shield,
  CheckCircle2, XCircle, AlertTriangle, Info,
  Loader2, Clock, ChevronRight, Copy, Check,
  Wrench, RefreshCw
} from 'lucide-react'
import toast from 'react-hot-toast'
import axios from 'axios'

// ── Kayıt tipleri ─────────────────────────────────────────────────────────────

const RECORD_TYPES = [
  { id: 'A',     label: 'A',     desc: 'IPv4 Adresi',              icon: Globe,       color: '#b1c6f9' },
  { id: 'AAAA',  label: 'AAAA',  desc: 'IPv6 Adresi',              icon: Globe,       color: '#b1c6f9' },
  { id: 'CNAME', label: 'CNAME', desc: 'Alias / Takma Ad',         icon: ChevronRight,color: '#adc6ff' },
  { id: 'MX',    label: 'MX',    desc: 'Mail Sunucusu',            icon: Mail,        color: '#c3b1e1' },
  { id: 'NS',    label: 'NS',    desc: 'Ad Sunucusu',              icon: Server,      color: '#adc6ff' },
  { id: 'TXT',   label: 'TXT',   desc: 'Metin Kaydı',             icon: FileText,    color: '#8d9099' },
  { id: 'SOA',   label: 'SOA',   desc: 'Otorite Başlangıcı',       icon: Info,        color: '#8d9099' },
  { id: 'PTR',   label: 'PTR',   desc: 'Ters DNS (IP girin)',       icon: RefreshCw,   color: '#8d9099' },
  { id: 'SPF',   label: 'SPF',   desc: 'Gönderici Politikası',     icon: Shield,      color: '#b1f9c2' },
  { id: 'DMARC', label: 'DMARC', desc: 'E-posta Kimlik Doğrulama', icon: Shield,      color: '#ffb786' },
  { id: 'DKIM',   label: 'DKIM',   desc: 'E-posta İmzası',      icon: Shield, color: '#f9d4b1' },
  { id: 'DNSSEC', label: 'DNSSEC', desc: 'Zone İmza Doğrulama', icon: Shield, color: '#b1f9e0' },
]

const TYPE_MAP = Object.fromEntries(RECORD_TYPES.map(t => [t.id, t]))

// ── Yardımcı bileşenler ───────────────────────────────────────────────────────

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    toast.success('Kopyalandı')
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button onClick={copy}
      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded"
      style={{ color: '#424754' }}
      title="Kopyala">
      {copied ? <Check className="w-3 h-3" style={{ color: '#b1c6f9' }} /> : <Copy className="w-3 h-3" />}
    </button>
  )
}

function StatusBadge({ status }) {
  if (status === 'found')
    return <span className="flex items-center gap-1 text-label-sm" style={{ color: '#b1c6f9' }}><CheckCircle2 className="w-3.5 h-3.5" />Bulundu</span>
  if (status === 'not_found')
    return <span className="flex items-center gap-1 text-label-sm" style={{ color: '#ffb786' }}><AlertTriangle className="w-3.5 h-3.5" />Kayıt Yok</span>
  return <span className="flex items-center gap-1 text-label-sm" style={{ color: '#ffb4ab' }}><XCircle className="w-3.5 h-3.5" />Hata</span>
}

// ── Kayıt satırı ─────────────────────────────────────────────────────────────

function RecordRow({ record, rtype }) {
  const cfg = TYPE_MAP[rtype] || TYPE_MAP['TXT']

  return (
    <div
      className="group flex items-start gap-4 px-5 py-3.5 transition-colors"
      style={{ borderBottom: '1px solid rgba(66,71,84,0.1)' }}
      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.015)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
      {/* TTL */}
      <div className="flex-shrink-0 text-right" style={{ minWidth: '64px' }}>
        {record.ttl != null && (
          <span className="text-label-sm font-mono" style={{ color: '#424754' }}>
            {record.ttl}s
          </span>
        )}
      </div>

      {/* Tip */}
      <span
        className="text-label-sm font-mono font-semibold flex-shrink-0 px-1.5 py-0.5 rounded"
        style={{ background: 'rgba(173,198,255,0.08)', color: cfg.color, minWidth: '52px', textAlign: 'center' }}
      >
        {rtype === 'SPF' || rtype === 'DMARC' ? rtype : rtype}
      </span>

      {/* MX öncelik */}
      {record.priority != null && (
        <span
          className="text-label-sm font-mono flex-shrink-0 px-1.5 py-0.5 rounded"
          style={{ background: 'rgba(195,177,225,0.1)', color: '#c3b1e1' }}
        >
          {record.priority}
        </span>
      )}

      {/* Değer */}
      <div className="flex-1 min-w-0">
        <p className="text-body-sm font-mono break-all" style={{ color: '#e3e5ef' }}>
          {record.value}
        </p>
        {record.extra && (
          <p className="text-label-sm mt-1 break-all" style={{ color: '#8d9099' }}>
            {record.extra}
          </p>
        )}
      </div>

      {/* Kopyala */}
      <CopyBtn text={record.value} />
    </div>
  )
}

// ── DKIM pattern yardımcısı ───────────────────────────────────────────────────

/**
 * "ntr._domainkey.gastronomad.online" gibi tam DKIM adresi girildiğinde
 * selector ve base domain'i ayıklar. Eşleşmezse null döner.
 */
function parseDkimInput(input) {
  const m = input.match(/^([^.\s]+)\._domainkey\.(.+)$/i)
  if (m) return { selector: m[1].toLowerCase(), baseDomain: m[2].toLowerCase() }
  return null
}

/**
 * Girilen domain'in subdomain'siz kök domain olup olmadığını kontrol eder.
 * example.com → true | www.example.com → false | example.com.tr → true
 */
function isBareRootDomain(domain) {
  const parts = domain.split('.')
  if (parts.length === 2) return true
  // Bileşik TLD'ler: .com.tr, .net.tr, .co.uk vb.
  const compoundTLDs = [
    'com.tr','net.tr','org.tr','gov.tr','edu.tr','av.tr','biz.tr','web.tr',
    'info.tr','tv.tr','tel.tr','name.tr','pol.tr','k12.tr','mil.tr',
    'co.uk','org.uk','me.uk','co.jp','or.jp','ne.jp',
  ]
  const lastTwo = parts.slice(-2).join('.')
  if (compoundTLDs.includes(lastTwo) && parts.length === 3) return true
  return false
}

// ── Ana bileşen ───────────────────────────────────────────────────────────────

export default function DNSToolbox() {
  const [domain, setDomain] = useState('')
  const [selectedType, setSelectedType] = useState('A')
  const [selector, setSelector] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const domainRef = useRef('')
  const selectorRef = useRef('')

  // Domain input değişince DKIM pattern kontrolü
  const handleDomainChange = (val) => {
    setDomain(val)
    domainRef.current = val
    const parsed = parseDkimInput(val.trim())
    if (parsed) {
      setSelectedType('DKIM')
      setSelector(parsed.selector)
      selectorRef.current = parsed.selector
    }
  }

  const handleSelectorChange = (val) => {
    setSelector(val)
    selectorRef.current = val
  }

  // Kayıt tipine tıklayınca tipi değiştir ve varsa otomatik sorgula
  const handleTypeSelect = (id) => {
    setSelectedType(id)
    if (domainRef.current.trim()) {
      query(domainRef.current, id, id === 'DKIM' ? selectorRef.current : undefined)
    }
  }

  const query = useCallback(async (d, t, sel) => {
    let dom = (d ?? domain).trim()
    let typ = t ?? selectedType
    let selVal = sel !== undefined ? sel : selector

    // Tam DKIM adresi girilmişse otomatik ayır
    const parsed = parseDkimInput(dom)
    if (parsed) {
      typ    = 'DKIM'
      selVal = parsed.selector
      dom    = parsed.baseDomain
      setSelectedType('DKIM')
      setSelector(parsed.selector)
      setDomain(parsed.baseDomain)
      domainRef.current = parsed.baseDomain
    }

    // CNAME sorgusunda kök domain girilmişse www. ekle
    if (typ === 'CNAME' && isBareRootDomain(dom)) {
      dom = `www.${dom}`
    }

    if (!dom) return

    setLoading(true)
    setResult(null)
    try {
      const res = await axios.post('/api/dns-toolbox/query', {
        domain: dom,
        record_type: typ,
        selector: typ === 'DKIM' ? (selVal || null) : null,
      })
      setResult(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Sorgu başarısız')
    } finally {
      setLoading(false)
    }
  }, [domain, selectedType, selector])

  const handleKey = (e) => { if (e.key === 'Enter') query() }

  const resultType = result?.record_type
  const typeCfg = resultType ? TYPE_MAP[resultType] : null

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="px-8 pt-8 pb-6">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, rgba(173,198,255,0.2) 0%, rgba(77,142,255,0.15) 100%)' }}>
            <Wrench className="w-4 h-4" style={{ color: '#adc6ff' }} />
          </div>
          <h1 className="text-headline-md font-semibold" style={{ color: '#e3e5ef', letterSpacing: '-0.01em' }}>
            DNS Toolbox
          </h1>
        </div>
        <p className="text-body-md" style={{ color: '#8d9099' }}>
          A · AAAA · CNAME · MX · NS · TXT · SOA · PTR · SPF · DMARC sorguları
        </p>
      </div>

      {/* Arama */}
      <div className="px-8 pb-5 flex flex-col gap-3">
        {/* Input */}
        <div className="flex items-center gap-3 rounded-card px-4 py-3" style={{ background: '#1a1c20' }}>
          <Search className="w-4 h-4 flex-shrink-0" style={{ color: '#8d9099' }} />
          <input
            type="text"
            value={domain}
            onChange={e => handleDomainChange(e.target.value)}
            onKeyDown={handleKey}
            placeholder={selectedType === 'PTR' ? '8.8.8.8 — IP girin' : 'example.com'}
            autoFocus
            className="flex-1 bg-transparent outline-none text-title-md font-mono"
            style={{ color: '#e3e5ef', caretColor: '#adc6ff' }}
          />
          <button onClick={() => query()} disabled={loading || !domain.trim()} className="btn-primary flex-shrink-0">
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" />Sorgulanıyor...</>
              : <><Search className="w-4 h-4" />Sorgula</>}
          </button>
        </div>

        {/* DKIM selector alanı */}
        {selectedType === 'DKIM' && (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-card px-3 py-2" style={{ background: '#1a1c20' }}>
              <span className="text-label-sm font-mono flex-shrink-0" style={{ color: '#f9d4b1' }}>selector</span>
              <span className="text-label-sm" style={{ color: '#424754' }}>._domainkey.</span>
              <input
                type="text"
                value={selector}
                onChange={e => handleSelectorChange(e.target.value.toLowerCase().trim())}
                onKeyDown={handleKey}
                placeholder="ör: google, default, mail — boş bırakırsan otomatik arar"
                className="bg-transparent outline-none text-body-sm font-mono"
                style={{ color: '#e3e5ef', caretColor: '#f9d4b1', width: '320px' }}
              />
            </div>
          </div>
        )}

        {/* Kayıt tipi seçici */}
        <div className="flex flex-wrap gap-2">
          {RECORD_TYPES.map(({ id, label, desc }) => (
            <button
              key={id}
              onClick={() => handleTypeSelect(id)}
              title={desc}
              className="px-3 py-1.5 rounded text-label-md font-mono font-semibold transition-all"
              style={{
                background: selectedType === id ? 'rgba(173,198,255,0.15)' : 'rgba(255,255,255,0.04)',
                color: selectedType === id ? '#adc6ff' : '#8d9099',
                border: selectedType === id ? '1px solid rgba(173,198,255,0.3)' : '1px solid transparent',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="px-8 pb-10">
        <div className="flex flex-col gap-4">

          {/* Loading skeleton */}
          {loading && (
            <div className="rounded-card overflow-hidden" style={{ background: '#1a1c20' }}>
              {[1,2,3].map(i => (
                <div key={i} className="flex items-center gap-4 px-5 py-3.5 animate-pulse"
                  style={{ borderBottom: '1px solid rgba(66,71,84,0.1)' }}>
                  <div className="h-3 w-12 rounded" style={{ background: '#282a2e' }} />
                  <div className="h-4 w-14 rounded" style={{ background: '#282a2e' }} />
                  <div className="h-3 flex-1 rounded" style={{ background: '#1e2128' }} />
                </div>
              ))}
            </div>
          )}

          {/* Sonuç başlığı */}
          {result && !loading && (
            <>
              <div className="flex items-center justify-between px-5 py-3.5 rounded-card"
                style={{ background: '#1a1c20' }}>
                <div className="flex items-center gap-3">
                  {typeCfg && <typeCfg.icon className="w-4 h-4" style={{ color: typeCfg.color }} />}
                  <p className="text-body-sm font-semibold" style={{ color: '#e3e5ef' }}>
                    {result.record_type} &nbsp;·&nbsp;
                    <span className="font-mono" style={{ color: '#adc6ff' }}>{result.queried_domain}</span>
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  {result.query_ms && (
                    <span className="flex items-center gap-1 text-label-sm font-mono" style={{ color: '#424754' }}>
                      <Clock className="w-3 h-3" />{result.query_ms}ms
                    </span>
                  )}
                  <StatusBadge status={result.status} />
                </div>
              </div>

              {/* Kayıtlar */}
              {result.records.length > 0 ? (
                <div className="rounded-card overflow-hidden" style={{ background: '#1a1c20' }}>
                  {/* Tablo başlığı */}
                  <div className="flex items-center gap-4 px-5 py-2"
                    style={{ borderBottom: '1px solid rgba(66,71,84,0.2)', background: '#111317' }}>
                    <span className="text-label-sm font-medium" style={{ color: '#424754', minWidth: '64px', textAlign: 'right' }}>TTL</span>
                    <span className="text-label-sm font-medium" style={{ color: '#424754', minWidth: '52px' }}>Tip</span>
                    {result.record_type === 'MX' && (
                      <span className="text-label-sm font-medium" style={{ color: '#424754' }}>Öncelik</span>
                    )}
                    <span className="text-label-sm font-medium" style={{ color: '#424754' }}>Değer</span>
                  </div>
                  {result.records.map((rec, i) => (
                    <RecordRow key={i} record={rec} rtype={result.record_type} />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 rounded-card"
                  style={{ background: '#1a1c20' }}>
                  <AlertTriangle className="w-7 h-7 mb-3 opacity-40" style={{ color: '#ffb786' }} />
                  <p className="text-body-sm font-medium" style={{ color: '#c2c6d6' }}>{result.message}</p>
                  <p className="text-label-sm mt-1" style={{ color: '#424754' }}>
                    Sunucu: {result.nameservers.slice(0, 2).join(', ')}
                  </p>
                </div>
              )}

              {/* Analiz paneli */}
              {result.analysis && (
                <div className="rounded-card px-5 py-4 flex items-start gap-3"
                  style={{
                    background: result.record_type === 'DMARC'  ? 'rgba(255,183,134,0.06)'
                      : result.record_type === 'SPF'    ? 'rgba(177,249,194,0.05)'
                      : result.record_type === 'DKIM'   ? 'rgba(249,212,177,0.06)'
                      : result.record_type === 'DNSSEC' ? 'rgba(177,249,224,0.06)'
                      : 'rgba(173,198,255,0.06)',
                    border: `1px solid ${
                      result.record_type === 'DMARC'  ? 'rgba(255,183,134,0.15)'
                      : result.record_type === 'SPF'    ? 'rgba(177,249,194,0.15)'
                      : result.record_type === 'DKIM'   ? 'rgba(249,212,177,0.15)'
                      : result.record_type === 'DNSSEC' ? 'rgba(177,249,224,0.15)'
                      : 'rgba(173,198,255,0.1)'}`,
                  }}>
                  <Shield className="w-4 h-4 mt-0.5 flex-shrink-0" style={{
                    color: result.record_type === 'DMARC'  ? '#ffb786'
                      : result.record_type === 'SPF'    ? '#b1f9c2'
                      : result.record_type === 'DKIM'   ? '#f9d4b1'
                      : result.record_type === 'DNSSEC' ? '#b1f9e0'
                      : '#adc6ff'
                  }} />
                  <div>
                    <p className="text-label-sm font-semibold mb-1" style={{
                      color: result.record_type === 'DMARC'  ? '#ffb786'
                        : result.record_type === 'SPF'    ? '#b1f9c2'
                        : result.record_type === 'DKIM'   ? '#f9d4b1'
                        : result.record_type === 'DNSSEC' ? '#b1f9e0'
                        : '#adc6ff'
                    }}>
                      {result.record_type} Analizi
                    </p>
                    <p className="text-body-sm" style={{ color: '#c2c6d6', lineHeight: '1.7' }}>
                      {result.analysis}
                    </p>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Boş ekran */}
          {!result && !loading && (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
                style={{ background: 'rgba(173,198,255,0.06)' }}>
                <Wrench className="w-7 h-7 opacity-30" style={{ color: '#adc6ff' }} />
              </div>
              <p className="text-title-md font-medium mb-1" style={{ color: '#c2c6d6' }}>DNS Toolbox</p>
              <p className="text-body-md text-center max-w-xs" style={{ color: '#8d9099' }}>
                Alan adı ve kayıt tipini seçin, ardından Sorgula butonuna basın
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
