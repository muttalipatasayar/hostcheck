import { useState, useRef } from 'react'
import {
  Search, Globe, Shield, Mail, Wifi, Lock,
  CheckCircle2, XCircle, AlertTriangle, Info,
  ChevronDown, ChevronUp, Copy, Check, Loader2,
  Zap, User, Wrench, Monitor, ExternalLink, RefreshCw
} from 'lucide-react'
import toast from 'react-hot-toast'
import axios from 'axios'

const STATUS_CONFIG = {
  healthy: { icon: CheckCircle2, color: '#b1c6f9', dot: 'status-dot-healthy', label: 'Sağlıklı' },
  warning: { icon: AlertTriangle, color: '#ffb786', dot: 'status-dot-warning', label: 'Uyarı' },
  error:   { icon: XCircle,       color: '#ffb4ab', dot: 'status-dot-error',   label: 'Hata' },
  info:    { icon: Info,           color: '#adc6ff', dot: 'status-dot-pending', label: 'Bilgi' },
}

const CHECK_ICONS = {
  'WHOIS / Alan Adı':  Globe,
  'DNS / NS Kayıtları': Globe,
  'DNS / A Kaydı':     Globe,
  'DNS / MX Kaydı':    Mail,
  'SSL Sertifika':     Lock,
  'HTTP Erişim':       Wifi,
}

function CheckRow({ item }) {
  const cfg = STATUS_CONFIG[item.status] || STATUS_CONFIG.info
  const Icon = CHECK_ICONS[item.label] || Globe
  const StatusIcon = cfg.icon

  return (
    <div
      className="flex items-center gap-4 px-5 py-3.5 transition-colors"
      style={{ borderBottom: '1px solid rgba(66,71,84,0.1)' }}
      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
      {/* Icon */}
      <div
        className="w-8 h-8 rounded-btn flex items-center justify-center flex-shrink-0"
        style={{ background: 'rgba(173,198,255,0.06)' }}
      >
        <Icon className="w-3.5 h-3.5" style={{ color: '#adc6ff' }} />
      </div>

      {/* Label + detail */}
      <div className="flex-1 min-w-0">
        <p className="text-body-sm font-medium" style={{ color: '#e3e5ef' }}>
          {item.label}
        </p>
        {item.detail && (
          <p className="text-label-md mt-0.5 truncate" style={{ color: '#8d9099' }}>
            {item.detail}
          </p>
        )}
      </div>

      {/* Value */}
      {item.value && (
        <code
          className="text-label-md font-mono px-2 py-0.5 rounded flex-shrink-0"
          style={{ background: '#282a2e', color: cfg.color }}
        >
          {item.value}
        </code>
      )}

      {/* Latency */}
      {item.latency_ms != null && (
        <p className="text-label-sm font-mono flex-shrink-0" style={{ color: '#424754' }}>
          {item.latency_ms < 1000 ? `${item.latency_ms}ms` : `${(item.latency_ms/1000).toFixed(1)}s`}
        </p>
      )}

      {/* Status */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        <span className={`status-dot ${cfg.dot}`} />
        <p className="text-label-sm" style={{ color: cfg.color }}>{cfg.label}</p>
      </div>
    </div>
  )
}

function ErrorAnalysisPanel({ analysis, httpStatus }) {
  const [showCustomer, setShowCustomer] = useState(false)
  const [copied, setCopied] = useState(false)

  const copyDraft = async () => {
    await navigator.clipboard.writeText(analysis.draft)
    setCopied(true)
    toast.success('Taslak kopyalandı')
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Hata başlığı */}
      <div
        className="flex items-center gap-3 px-5 py-4 rounded-card"
        style={{ background: '#282a2e' }}
      >
        <div
          className="w-9 h-9 rounded-btn flex items-center justify-center flex-shrink-0"
          style={{ background: 'rgba(255,180,171,0.1)' }}
        >
          <XCircle className="w-4 h-4" style={{ color: '#ffb4ab' }} />
        </div>
        <div>
          <p className="text-body-sm font-semibold" style={{ color: '#ffb4ab' }}>
            {analysis.title}
          </p>
          <p className="text-label-sm mt-0.5" style={{ color: '#8d9099' }}>
            Platform: {analysis.platform} · HTTP {httpStatus}
          </p>
        </div>
      </div>

      {/* İki kolon: nedenler + adımlar */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Olası nedenler */}
        <div className="rounded-card overflow-hidden" style={{ background: '#1a1c20' }}>
          <div
            className="flex items-center gap-2 px-4 py-3"
            style={{ borderBottom: '1px solid rgba(66,71,84,0.2)' }}
          >
            <Info className="w-3.5 h-3.5" style={{ color: '#ffb786' }} />
            <p className="text-label-md font-medium" style={{ color: '#ffb786' }}>
              Olası Nedenler
            </p>
          </div>
          <div className="px-4 py-3 flex flex-col gap-2">
            {analysis.causes.map((cause, i) => (
              <div key={i} className="flex items-start gap-2">
                <span
                  className="text-label-sm font-mono mt-0.5 flex-shrink-0"
                  style={{ color: '#424754' }}
                >
                  {String(i + 1).padStart(2, '0')}
                </span>
                <p className="text-body-sm" style={{ color: '#c2c6d6' }}>{cause}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Teknik adımlar — senin için */}
        <div className="rounded-card overflow-hidden" style={{ background: '#1a1c20' }}>
          <div
            className="flex items-center gap-2 px-4 py-3"
            style={{ borderBottom: '1px solid rgba(66,71,84,0.2)' }}
          >
            <Wrench className="w-3.5 h-3.5" style={{ color: '#adc6ff' }} />
            <p className="text-label-md font-medium" style={{ color: '#adc6ff' }}>
              Sen Ne Yapacaksın
            </p>
          </div>
          <div className="px-4 py-3 flex flex-col gap-2.5">
            {analysis.tech_steps.map((step, i) => (
              <div key={i} className="flex items-start gap-2.5">
                <div
                  className="w-5 h-5 rounded flex items-center justify-center flex-shrink-0 mt-0.5"
                  style={{ background: 'rgba(173,198,255,0.1)' }}
                >
                  <span className="text-label-sm font-medium" style={{ color: '#adc6ff' }}>
                    {i + 1}
                  </span>
                </div>
                <p className="text-body-sm" style={{ color: '#c2c6d6' }}>{step}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Müşteri yanıt taslağı */}
      <div className="rounded-card overflow-hidden" style={{ background: '#1a1c20' }}>
        <button
          onClick={() => setShowCustomer(!showCustomer)}
          className="flex items-center justify-between w-full px-4 py-3 text-left"
          style={{ borderBottom: showCustomer ? '1px solid rgba(66,71,84,0.2)' : 'none' }}
        >
          <div className="flex items-center gap-2">
            <User className="w-3.5 h-3.5" style={{ color: '#b1c6f9' }} />
            <p className="text-label-md font-medium" style={{ color: '#b1c6f9' }}>
              {analysis.customer_action ? 'Müşteri Yapacak — Rehber Metin' : 'Müşteriye Yanıt Taslağı'}
            </p>
          </div>
          {showCustomer
            ? <ChevronUp className="w-4 h-4" style={{ color: '#424754' }} />
            : <ChevronDown className="w-4 h-4" style={{ color: '#424754' }} />
          }
        </button>
        {showCustomer && (
          <div className="px-4 pb-4 pt-3">
            <p className="text-body-sm mb-3" style={{ color: '#c2c6d6', lineHeight: '1.7' }}>
              {analysis.draft}
            </p>
            <button onClick={copyDraft} className="btn-ghost text-label-md">
              {copied
                ? <><Check className="w-3.5 h-3.5" style={{ color: '#b1c6f9' }} /> Kopyalandı</>
                : <><Copy className="w-3.5 h-3.5" /> Kopyala</>
              }
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function SitePreview({ domain }) {
  const [imgLoaded, setImgLoaded] = useState(false)
  const [imgError, setImgError] = useState(false)
  const [key, setKey] = useState(0)

  // Backend'deki yerel Playwright endpoint — Edge ile anında screenshot
  const screenshotUrl = `/api/screenshot/${domain}?_=${key}`

  const retry = () => {
    setImgLoaded(false)
    setImgError(false)
    setKey(k => k + 1)
  }

  return (
    <div>
      <p
        className="text-label-sm font-medium uppercase tracking-wider mb-3"
        style={{ color: '#424754' }}
      >
        Site Görünümü
      </p>

      <div className="rounded-card overflow-hidden" style={{ background: '#1a1c20' }}>
        {/* Adres çubuğu */}
        <div
          className="flex items-center justify-between px-4 py-2.5"
          style={{ borderBottom: '1px solid rgba(66,71,84,0.15)' }}
        >
          <div className="flex items-center gap-2 min-w-0">
            <Monitor className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#8d9099' }} />
            <p className="text-label-md font-mono truncate" style={{ color: '#8d9099' }}>
              https://{domain}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0 ml-3">
            {imgError && (
              <button onClick={retry} className="btn-ghost text-label-sm py-1 px-2">
                <RefreshCw className="w-3.5 h-3.5" /> Yeniden Dene
              </button>
            )}
            <a
              href={`https://${domain}`}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-ghost text-label-sm py-1 px-2"
            >
              <ExternalLink className="w-3.5 h-3.5" /> Aç
            </a>
          </div>
        </div>

        {/* Screenshot alanı */}
        <div className="relative" style={{ minHeight: '240px', background: '#111317' }}>
          {/* Loading */}
          {!imgLoaded && !imgError && (
            <div
              className="absolute inset-0 flex flex-col items-center justify-center gap-2"
              style={{ color: '#424754' }}
            >
              <Loader2 className="w-5 h-5 animate-spin" />
              <p className="text-label-sm">Ekran görüntüsü alınıyor...</p>
            </div>
          )}

          {/* Error */}
          {imgError && (
            <div
              className="absolute inset-0 flex flex-col items-center justify-center gap-2"
              style={{ color: '#424754' }}
            >
              <Monitor className="w-7 h-7 opacity-30" />
              <p className="text-body-sm" style={{ color: '#8d9099' }}>Önizleme alınamadı</p>
              <p className="text-label-sm text-center max-w-xs" style={{ color: '#424754' }}>
                Site HTTPS'i reddediyor veya screenshot servisi ulaşamıyor olabilir
              </p>
            </div>
          )}

          {/* Actual image */}
          <img
            key={key}
            src={screenshotUrl}
            alt={`${domain} önizleme`}
            className="w-full block"
            style={{ display: imgLoaded ? 'block' : 'none' }}
            onLoad={() => setImgLoaded(true)}
            onError={() => setImgError(true)}
          />
        </div>
      </div>
    </div>
  )
}

export default function QuickCheck() {
  const [domain, setDomain] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const inputRef = useRef(null)

  const run = async () => {
    const d = domain.trim()
    if (!d) return
    setLoading(true)
    setResult(null)
    try {
      const res = await axios.post('/api/quick-check/', { domain: d })
      setResult(res.data)
    } catch (err) {
      toast.error('Kontrol çalıştırılamadı — backend çalışıyor mu?')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleKey = (e) => {
    if (e.key === 'Enter') run()
  }

  const overallCfg = result ? STATUS_CONFIG[result.overall] : null

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="px-8 pt-8 pb-6">
        <div className="flex items-center gap-3 mb-1">
          <div
            className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, rgba(173,198,255,0.2) 0%, rgba(77,142,255,0.15) 100%)' }}
          >
            <Zap className="w-4 h-4" style={{ color: '#adc6ff' }} />
          </div>
          <h1
            className="text-headline-md font-semibold"
            style={{ color: '#e3e5ef', letterSpacing: '-0.01em' }}
          >
            Hızlı Kontrol
          </h1>
        </div>
        <p className="text-body-md" style={{ color: '#8d9099' }}>
          Alan adı yaz — WHOIS, DNS, SSL, HTTP kontrollerini saniyeler içinde gör
        </p>
      </div>

      {/* Search bar */}
      <div className="px-8 pb-6">
        <div
          className="flex items-center gap-3 rounded-card px-4 py-3"
          style={{ background: '#1a1c20' }}
        >
          <Search className="w-4 h-4 flex-shrink-0" style={{ color: '#8d9099' }} />
          <input
            ref={inputRef}
            type="text"
            value={domain}
            onChange={e => setDomain(e.target.value)}
            onKeyDown={handleKey}
            placeholder="example.com"
            className="flex-1 bg-transparent outline-none text-title-md font-mono"
            style={{ color: '#e3e5ef', caretColor: '#adc6ff' }}
            autoFocus
          />
          <button
            onClick={run}
            disabled={loading || !domain.trim()}
            className="btn-primary flex-shrink-0"
          >
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Kontrol ediliyor...</>
              : <><Zap className="w-4 h-4" /> Kontrol Et</>
            }
          </button>
        </div>
      </div>

      {/* Results */}
      {loading && (
        <div className="px-8">
          <div className="rounded-card overflow-hidden" style={{ background: '#1a1c20' }}>
            {[1,2,3,4,5,6].map(i => (
              <div
                key={i}
                className="flex items-center gap-4 px-5 py-3.5 animate-pulse"
                style={{ borderBottom: '1px solid rgba(66,71,84,0.1)' }}
              >
                <div className="w-8 h-8 rounded-btn" style={{ background: '#282a2e' }} />
                <div className="flex-1 flex flex-col gap-1.5">
                  <div className="h-3 rounded w-32" style={{ background: '#282a2e' }} />
                  <div className="h-3 rounded w-56" style={{ background: '#1e2128' }} />
                </div>
                <div className="h-5 w-20 rounded" style={{ background: '#282a2e' }} />
              </div>
            ))}
          </div>
        </div>
      )}

      {result && !loading && (
        <div className="px-8 pb-10 flex flex-col gap-5 slide-up">

          {/* Overall status banner */}
          <div
            className="flex items-center justify-between px-5 py-4 rounded-card"
            style={{ background: '#1a1c20' }}
          >
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <span className={`status-dot ${overallCfg?.dot}`} />
                <p className="text-body-sm font-medium" style={{ color: overallCfg?.color }}>
                  {overallCfg?.label}
                </p>
              </div>
              <span style={{ color: '#424754' }}>·</span>
              <p className="text-body-sm font-mono" style={{ color: '#adc6ff' }}>
                {result.domain}
              </p>
              <span style={{ color: '#424754' }}>·</span>
              <p className="text-body-sm" style={{ color: '#8d9099' }}>
                {result.summary}
              </p>
            </div>
            {result.http_status && (
              <code
                className="text-label-md font-mono px-2.5 py-1 rounded"
                style={{
                  background: result.http_status >= 500 ? 'rgba(255,180,171,0.1)'
                    : result.http_status >= 400 ? 'rgba(255,183,134,0.1)'
                    : 'rgba(177,198,249,0.1)',
                  color: result.http_status >= 500 ? '#ffb4ab'
                    : result.http_status >= 400 ? '#ffb786'
                    : '#b1c6f9',
                }}
              >
                HTTP {result.http_status}
              </code>
            )}
          </div>

          {/* Check rows */}
          <div className="rounded-card overflow-hidden" style={{ background: '#1a1c20' }}>
            {result.checks.map((item, i) => (
              <CheckRow key={i} item={item} />
            ))}
          </div>

          {/* Site önizleme */}
          <SitePreview domain={result.domain} />

          {/* Error analysis — sadece hata varsa */}
          {result.error_analysis && (
            <div>
              <p
                className="text-label-sm font-medium uppercase tracking-wider mb-3"
                style={{ color: '#424754' }}
              >
                Hata Analizi
              </p>
              <ErrorAnalysisPanel
                analysis={result.error_analysis}
                httpStatus={result.http_status}
              />
            </div>
          )}

          {/* Hata yok ama uyarı var */}
          {!result.error_analysis && result.overall === 'warning' && (
            <div
              className="px-5 py-4 rounded-card flex items-center gap-3"
              style={{ background: 'rgba(255,183,134,0.06)' }}
            >
              <AlertTriangle className="w-4 h-4 flex-shrink-0" style={{ color: '#ffb786' }} />
              <p className="text-body-sm" style={{ color: '#c2c6d6' }}>
                Bazı kontrollerde uyarı mevcut. Detayları yukarıdan inceleyin.
              </p>
            </div>
          )}

          {/* Her şey sağlıklı */}
          {result.overall === 'healthy' && (
            <div
              className="px-5 py-4 rounded-card flex items-center gap-3"
              style={{ background: 'rgba(177,198,249,0.06)' }}
            >
              <CheckCircle2 className="w-4 h-4 flex-shrink-0" style={{ color: '#b1c6f9' }} />
              <p className="text-body-sm" style={{ color: '#c2c6d6' }}>
                Tüm kontroller başarılı. Alan adı sağlıklı görünüyor.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!result && !loading && (
        <div className="flex-1 flex flex-col items-center justify-center pb-20">
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
            style={{ background: 'rgba(173,198,255,0.06)' }}
          >
            <Search className="w-7 h-7 opacity-30" style={{ color: '#adc6ff' }} />
          </div>
          <p className="text-title-md font-medium mb-1" style={{ color: '#c2c6d6' }}>
            Alan adı girin
          </p>
          <p className="text-body-md text-center max-w-xs" style={{ color: '#8d9099' }}>
            WHOIS, DNS (NS/A/MX), SSL ve HTTP kontrolleri otomatik çalışır
          </p>
        </div>
      )}
    </div>
  )
}
