import { useState } from 'react'
import { clsx } from 'clsx'
import {
  ShieldCheck, Globe, Wifi, Lock, AlertTriangle,
  CheckCircle2, XCircle, Minus, RefreshCw, Play
} from 'lucide-react'
import toast from 'react-hot-toast'
import { checksApi, ticketsApi } from '../api/client'

const CHECK_ICONS = {
  DNS: Globe,
  HTTP: Wifi,
  SSL: Lock,
  PING: Wifi,
  WHOIS: ShieldCheck,
}

const STATUS_CONFIG = {
  healthy: {
    icon: CheckCircle2,
    dotClass: 'status-dot-healthy',
    color: '#4a6cf7',
    label: 'Sağlıklı',
  },
  error: {
    icon: XCircle,
    dotClass: 'status-dot-error',
    color: '#ffb4ab',
    label: 'Hata',
  },
  warning: {
    icon: AlertTriangle,
    dotClass: 'status-dot-warning',
    color: '#ffb786',
    label: 'Uyarı',
  },
  skipped: {
    icon: Minus,
    dotClass: 'status-dot-pending',
    color: '#6b7388',
    label: 'Atlandı',
  },
}

function CheckRow({ result }) {
  const cfg = STATUS_CONFIG[result.status] || STATUS_CONFIG.skipped
  const CheckIcon = CHECK_ICONS[result.check_type] || Globe
  const StatusIcon = cfg.icon

  return (
    <div className="check-row">
      {/* Check type icon */}
      <div
        className="w-8 h-8 rounded-btn flex items-center justify-center flex-shrink-0"
        style={{ background: 'rgba(173, 198, 255, 0.06)' }}
      >
        <CheckIcon className="w-3.5 h-3.5" style={{ color: '#3b7eff' }} />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>
            {result.check_type}
          </p>
          {result.value && (
            <code
              className="text-label-sm font-mono px-1.5 py-0.5 rounded"
              style={{ background: '#f2f4fa', color: '#4a5068' }}
            >
              {result.value}
            </code>
          )}
        </div>
        <p className="text-label-md" style={{ color: '#6b7388' }}>
          {result.message}
        </p>
      </div>

      {/* Latency */}
      {result.latency_ms != null && (
        <div className="flex-shrink-0 text-right">
          <p className="text-label-sm font-mono" style={{ color: '#9da5be' }}>
            {result.latency_ms < 1000
              ? `${result.latency_ms.toFixed(0)}ms`
              : `${(result.latency_ms / 1000).toFixed(2)}s`}
          </p>
        </div>
      )}

      {/* Status */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        <span className={`status-dot ${cfg.dotClass}`} />
        <p className="text-label-sm" style={{ color: cfg.color }}>
          {cfg.label}
        </p>
      </div>
    </div>
  )
}

export default function CheckResults({ ticket, onResultsSaved }) {
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(
    ticket.check_results?.results || null
  )
  const [summary, setSummary] = useState(
    ticket.check_results?.summary || null
  )

  const hasTarget = ticket.domain || ticket.server_ip

  const runChecks = async () => {
    if (!hasTarget) {
      toast.error('Talep için domain veya IP adresi belirtilmemiş')
      return
    }

    setLoading(true)
    try {
      const res = await checksApi.run({
        domain: ticket.domain || undefined,
        server_ip: ticket.server_ip || undefined,
        ticket_id: ticket.id,
      })

      const data = res.data
      setResults(data.results)
      setSummary(data.summary)

      // Ticket'a kaydet
      await ticketsApi.saveCheckResults(ticket.id, data)
      onResultsSaved && onResultsSaved(data)
      toast.success('Kontroller tamamlandı')
    } catch (err) {
      toast.error('Kontroller çalıştırılamadı')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const overallStatus = results
    ? results.some(r => r.status === 'error')
      ? 'error'
      : results.some(r => r.status === 'warning')
        ? 'warning'
        : 'healthy'
    : null

  return (
    <div
      className="rounded-card overflow-hidden"
      style={{ background: '#ffffff' }}
    >
      {/* Panel header */}
      <div
        className="flex items-center justify-between px-5 py-4"
        style={{ borderBottom: '1px solid rgba(0,6,30,0.06)' }}
      >
        <div className="flex items-center gap-3">
          <ShieldCheck className="w-4 h-4" style={{ color: '#3b7eff' }} />
          <div>
            <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>
              Otomatik Kontroller
            </p>
            {results && (
              <p className="text-label-sm mt-0.5" style={{ color: '#6b7388' }}>
                {results.length} kontrol tamamlandı
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          {overallStatus && (
            <div className="flex items-center gap-1.5">
              <span className={`status-dot status-dot-${overallStatus}`} />
              <p className="text-label-sm" style={{ color: STATUS_CONFIG[overallStatus]?.color }}>
                {STATUS_CONFIG[overallStatus]?.label}
              </p>
            </div>
          )}

          <button
            onClick={runChecks}
            disabled={loading || !hasTarget}
            className={clsx('btn-secondary gap-2', {
              'opacity-50 cursor-not-allowed': !hasTarget,
            })}
          >
            {loading ? (
              <><span className="spinner" /> Kontrol ediliyor...</>
            ) : results ? (
              <><RefreshCw className="w-3.5 h-3.5" /> Yenile</>
            ) : (
              <><Play className="w-3.5 h-3.5" /> Kontrolleri Çalıştır</>
            )}
          </button>
        </div>
      </div>

      {/* No target warning */}
      {!hasTarget && (
        <div className="px-5 py-4">
          <p className="text-body-sm" style={{ color: '#6b7388' }}>
            Kontrol çalıştırmak için talep detaylarında domain veya sunucu IP'si ekleyin.
          </p>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && (
        <div className="flex flex-col">
          {[1, 2, 3].map(i => (
            <div key={i} className="check-row animate-pulse">
              <div className="w-8 h-8 rounded-btn" style={{ background: '#f2f4fa' }} />
              <div className="flex-1 flex flex-col gap-1.5">
                <div className="h-3 rounded w-20" style={{ background: '#f2f4fa' }} />
                <div className="h-3 rounded w-48" style={{ background: '#f0f2f8' }} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Results */}
      {!loading && results && (
        <>
          <div className="flex flex-col">
            {results.map((r, i) => (
              <div key={i} style={{ borderBottom: i < results.length - 1 ? '1px solid rgba(0,6,30,0.04)' : 'none' }}>
                <CheckRow result={r} />
              </div>
            ))}
          </div>

          {/* Summary */}
          {summary && (
            <div
              className="px-5 py-3"
              style={{ borderTop: '1px solid rgba(0,6,30,0.06)', background: '#f0f2f7' }}
            >
              <p className="text-label-md" style={{ color: '#4a5068' }}>
                <span style={{ color: '#3b7eff', fontWeight: 500 }}>Özet: </span>
                {summary}
              </p>
            </div>
          )}
        </>
      )}

      {/* Empty state */}
      {!loading && !results && hasTarget && (
        <div className="py-10 text-center px-5">
          <Play className="w-8 h-8 mx-auto mb-2 opacity-20" style={{ color: '#4a5068' }} />
          <p className="text-body-md mb-1" style={{ color: '#4a5068' }}>
            Kontroller henüz çalıştırılmadı
          </p>
          <p className="text-label-md" style={{ color: '#6b7388' }}>
            DNS, HTTP, SSL ve ping kontrollerini otomatik çalıştırmak için butona tıklayın
          </p>
        </div>
      )}
    </div>
  )
}
