import { useState } from 'react'
import {
  Radar, Search, Loader2, Clock, MapPin,
  CheckCircle2, XCircle, AlertTriangle, Info,
} from 'lucide-react'
import axios from 'axios'
import toast from 'react-hot-toast'
import { useTarget, useCommittedTarget } from '../context/TargetContext'

const STATUS_CONFIG = {
  healthy: { icon: CheckCircle2,  color: '#4a6cf7', dot: 'status-dot-healthy', label: 'Tutarlı' },
  warning: { icon: AlertTriangle, color: '#ffb786', dot: 'status-dot-warning', label: 'Farklı' },
  error:   { icon: XCircle,       color: '#ffb4ab', dot: 'status-dot-error',   label: 'Ulaşılamadı' },
  info:    { icon: Info,          color: '#3b7eff', dot: 'status-dot-pending', label: 'Kayıt Yok' },
}

const RECORD_TYPES = ['A', 'AAAA', 'CNAME', 'MX', 'NS', 'TXT']

export default function DNSPropagation() {
  const [recordType, setRecordType] = useState('A')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const { target, commitTarget } = useTarget()

  const check = async (domain, typeOverride) => {
    setLoading(true)
    setResult(null)
    try {
      const res = await axios.post('/api/dns-propagation/check', {
        domain,
        record_type: typeOverride ?? recordType,
      })
      setResult(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Yayılma kontrolü başarısız')
    } finally {
      setLoading(false)
    }
  }

  // autoRun:true — ucuz/idempotent; commit edilmiş hedefle sekmeye gelindiğinde
  // kendiliğinden de çalışır
  useCommittedTarget(check, { autoRun: true })

  const handleTypeSelect = (t) => {
    setRecordType(t)
    if (target.trim()) check(target.trim(), t)
  }

  const overallCfg = result ? STATUS_CONFIG[result.overall] : null

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Başlık */}
      <div className="px-8 pt-8 pb-6">
        <div className="flex items-center gap-3 mb-1">
          <div
            className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, rgba(173,198,255,0.2) 0%, rgba(77,142,255,0.15) 100%)' }}
          >
            <Radar className="w-4 h-4" style={{ color: '#3b7eff' }} />
          </div>
          <h1 className="text-headline-md font-semibold" style={{ color: '#1a1d2e', letterSpacing: '-0.01em' }}>
            DNS Yayılma
          </h1>
        </div>
        <p className="text-body-md" style={{ color: '#6b7388' }}>
          Kaydın dünyadaki ve Türkiye'deki resolver'larda görünürlüğü — Türk Telekom ve Superonline dahil
        </p>
      </div>

      {/* Çalıştır + kayıt tipi */}
      <div className="px-8 pb-5 flex flex-col gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={commitTarget}
            disabled={loading || !target.trim()}
            className="btn-primary flex-shrink-0 flex items-center gap-2"
          >
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Kontrol ediliyor…</>
              : <><Search className="w-4 h-4" /> {target.trim() ? `${target.trim()} yayılmasını kontrol et` : 'Kontrol Et'}</>
            }
          </button>
          {!target.trim() && (
            <p className="text-body-sm" style={{ color: '#9da5be' }}>
              Üstteki hedef çubuğuna bir alan adı yazın.
            </p>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          {RECORD_TYPES.map(t => (
            <button
              key={t}
              onClick={() => handleTypeSelect(t)}
              className="px-3 py-1.5 rounded text-label-md font-mono font-semibold transition-all"
              style={{
                background: recordType === t ? 'rgba(59,127,255,0.12)' : 'rgba(0,6,30,0.03)',
                color: recordType === t ? '#3b7eff' : '#6b7388',
                border: recordType === t ? '1px solid rgba(59,127,255,0.25)' : '1px solid transparent',
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="px-8 pb-10 flex flex-col gap-4">
        {/* Yükleniyor */}
        {loading && (
          <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
            {[1, 2, 3, 4, 5].map(i => (
              <div key={i} className="flex items-center gap-4 px-5 py-3.5 animate-pulse"
                style={{ borderBottom: '1px solid rgba(0,6,30,0.04)' }}>
                <div className="h-4 w-32 rounded" style={{ background: '#f2f4fa' }} />
                <div className="h-3 flex-1 rounded" style={{ background: '#f0f2f8' }} />
                <div className="h-3 w-16 rounded" style={{ background: '#f2f4fa' }} />
              </div>
            ))}
          </div>
        )}

        {result && !loading && (
          <>
            {/* Özet + yayılma yüzdesi */}
            <div className="rounded-card px-5 py-4" style={{ background: '#ffffff' }}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className={`status-dot ${overallCfg?.dot}`} />
                  <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>
                    {result.record_type} · <span className="font-mono" style={{ color: '#3b7eff' }}>{result.domain}</span>
                  </p>
                </div>
                <span className="text-title-md font-semibold font-mono" style={{ color: overallCfg?.color }}>
                  %{result.propagated_pct}
                </span>
              </div>
              {/* Yayılma çubuğu */}
              <div className="h-2 rounded-full overflow-hidden mb-3" style={{ background: 'rgba(0,6,30,0.06)' }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${result.propagated_pct}%`,
                    background: result.overall === 'healthy'
                      ? 'linear-gradient(90deg,#4a6cf7,#3b7eff)'
                      : 'linear-gradient(90deg,#ffb786,#f5a35c)',
                  }}
                />
              </div>
              <p className="text-body-sm" style={{ color: '#4a5068' }}>{result.summary}</p>
              {result.consensus.length > 0 && (
                <p className="text-label-sm font-mono mt-2 break-all" style={{ color: '#6b7388' }}>
                  Konsensüs: {result.consensus.join(' · ')}
                </p>
              )}
            </div>

            {/* Resolver tablosu */}
            <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
              {result.results.map((r, i) => {
                const cfg = STATUS_CONFIG[r.status]
                return (
                  <div key={i} className="flex items-start gap-4 px-5 py-3"
                    style={{ borderBottom: '1px solid rgba(0,6,30,0.04)' }}>
                    <span className={`status-dot ${cfg.dot} mt-1.5 flex-shrink-0`} />
                    <div className="flex-shrink-0" style={{ minWidth: 170 }}>
                      <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>{r.name}</p>
                      <p className="text-label-sm font-mono flex items-center gap-1" style={{ color: '#9da5be' }}>
                        <MapPin className="w-3 h-3" />{r.location} · {r.ip}
                      </p>
                    </div>
                    <div className="flex-1 min-w-0">
                      {r.records.length > 0 ? (
                        <p className="text-body-sm font-mono break-all" style={{ color: '#1a1d2e' }}>
                          {r.records.join(' · ')}
                        </p>
                      ) : (
                        <p className="text-body-sm" style={{ color: '#9da5be' }}>{r.detail || '—'}</p>
                      )}
                      {r.records.length > 0 && r.detail && (
                        <p className="text-label-sm mt-0.5" style={{ color: '#ffb786' }}>{r.detail}</p>
                      )}
                    </div>
                    <div className="flex-shrink-0 text-right">
                      <span className="text-label-sm font-medium" style={{ color: cfg.color }}>{cfg.label}</span>
                      {r.latency_ms != null && (
                        <p className="text-label-sm font-mono flex items-center gap-1 justify-end" style={{ color: '#9da5be' }}>
                          <Clock className="w-3 h-3" />{r.latency_ms}ms
                        </p>
                      )}
                      {r.ttl != null && (
                        <p className="text-label-sm font-mono" style={{ color: '#9da5be' }}>TTL {r.ttl}s</p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Hata analizi (ERROR_DB) */}
            {result.error_analysis && (
              <div className="rounded-card px-5 py-4"
                style={{ background: 'rgba(255,183,134,0.06)', border: '1px solid rgba(255,183,134,0.15)' }}>
                <p className="text-label-sm font-semibold mb-2" style={{ color: '#ffb786' }}>
                  {result.error_analysis.title}
                </p>
                <p className="text-label-sm font-medium mb-1" style={{ color: '#6b7388' }}>Olası nedenler:</p>
                <ul className="text-body-sm mb-3 pl-4 list-disc" style={{ color: '#4a5068' }}>
                  {result.error_analysis.causes.map((c, i) => <li key={i}>{c}</li>)}
                </ul>
                <p className="text-label-sm font-medium mb-1" style={{ color: '#6b7388' }}>Teknisyen adımları:</p>
                <ol className="text-body-sm mb-3 pl-4 list-decimal" style={{ color: '#4a5068' }}>
                  {result.error_analysis.tech_steps.map((s, i) => <li key={i}>{s}</li>)}
                </ol>
                <p className="text-label-sm font-medium mb-1" style={{ color: '#6b7388' }}>Müşteriye taslak yanıt:</p>
                <p className="text-body-sm rounded-btn px-3 py-2" style={{ background: 'rgba(0,6,30,0.03)', color: '#4a5068' }}>
                  {result.error_analysis.draft}
                </p>
              </div>
            )}
          </>
        )}

        {/* Boş ekran */}
        {!result && !loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
              style={{ background: 'rgba(59,127,255,0.05)' }}>
              <Radar className="w-7 h-7 opacity-30" style={{ color: '#3b7eff' }} />
            </div>
            <p className="text-title-md font-medium mb-1" style={{ color: '#4a5068' }}>DNS Yayılma</p>
            <p className="text-body-md text-center max-w-xs" style={{ color: '#6b7388' }}>
              Üstteki hedef çubuğuna alan adı yazın — 13 resolver'da (TR dahil) görünürlüğü kontrol edilir
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
