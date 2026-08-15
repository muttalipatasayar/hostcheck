import { useState } from 'react'
import axios from 'axios'
import { Search, Clock, Shield, Building2, Server, ChevronDown, ChevronUp, AlertCircle, CheckCircle2, Info } from 'lucide-react'
import { useTarget, useCommittedTarget } from '../context/TargetContext'

export default function DNSHistory() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const { target, commitTarget } = useTarget()

  const lookup = async (d) => {
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const res = await axios.post('/api/dns-history/lookup', { domain: d })
      setResult(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Sorgu sırasında bir hata oluştu.')
    } finally {
      setLoading(false)
    }
  }

  // autoRun:false — SecurityTrails kotası pahalı; yalnızca açık Enter/Çalıştır
  // ile sorgular, sekmeye gelince kendiliğinden çalışmaz
  useCommittedTarget(lookup, { autoRun: false })

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Başlık */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1" style={{ color: '#1a1d2e' }}>DNS History</h1>
        <p className="text-sm" style={{ color: '#6b7388' }}>
          Alan adı kayıt tarihi, registrar bilgisi ve NS sunucu geçmişi
        </p>
      </div>

      {/* Hedef hazır — tek Enter yeter */}
      <div className="mb-8 flex items-center gap-3">
        <button
          onClick={commitTarget}
          disabled={loading || !target.trim()}
          autoFocus
          className="px-5 py-2.5 rounded-btn text-sm font-medium transition-opacity disabled:opacity-50 flex items-center gap-2"
          style={{ background: '#3b7eff', color: '#002e6a' }}
        >
          <Search className="w-4 h-4" />
          {loading ? 'Sorgulanıyor…' : target.trim() ? `${target.trim()} geçmişini sorgula` : 'Sorgula'}
        </button>
        {!target.trim() && (
          <p className="text-sm" style={{ color: '#9da5be' }}>
            Üstteki hedef çubuğuna bir alan adı yazın.
          </p>
        )}
      </div>

      {/* Error */}
      {error && (
        <div
          className="flex items-center gap-3 px-4 py-3 rounded-card mb-6 text-sm"
          style={{ background: 'rgba(255, 180, 171, 0.1)', border: '1px solid rgba(255,180,171,0.2)', color: '#ffb4ab' }}
        >
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Results */}
      {result && <ResultPanel data={result} />}
    </div>
  )
}

function ResultPanel({ data }) {
  return (
    <div className="flex flex-col gap-4">
      {/* Domain header */}
      <div
        className="px-5 py-4 rounded-card flex items-center gap-3"
        style={{ background: '#ffffff', border: '1px solid rgba(0,6,30,0.09)' }}
      >
        <div
          className="w-9 h-9 rounded-btn flex items-center justify-center flex-shrink-0"
          style={{ background: 'rgba(59,127,255,0.09)' }}
        >
          <Server className="w-4 h-4" style={{ color: '#3b7eff' }} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-base truncate" style={{ color: '#1a1d2e' }}>{data.domain}</p>
          <p className="text-xs" style={{ color: '#6b7388' }}>{data.message}</p>
        </div>
        {data.has_api_key
          ? <span className="text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(177,198,249,0.1)', color: '#4a6cf7' }}>SecurityTrails</span>
          : <span className="text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(0,6,30,0.09)', color: '#6b7388' }}>Temel mod</span>
        }
      </div>

      {/* Info cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <InfoCard
          icon={<Clock className="w-4 h-4" />}
          label="İlk Kayıt"
          value={data.created_at ?? '—'}
          color="#4a6cf7"
        />
        <InfoCard
          icon={<Shield className="w-4 h-4" />}
          label="Bitiş Tarihi"
          value={data.expires_at ?? '—'}
          color="#4a6cf7"
        />
        <InfoCard
          icon={<Building2 className="w-4 h-4" />}
          label="Registrar"
          value={data.registrar ?? '—'}
          color="#4a6cf7"
          truncate
        />
      </div>

      {/* Current NS */}
      {data.current_ns.length > 0 && (
        <Section title="Mevcut Name Server'lar" icon={<Server className="w-4 h-4" />}>
          <div className="flex flex-wrap gap-2 pt-1">
            {data.current_ns.map((ns, i) => (
              <span
                key={i}
                className="text-xs px-3 py-1.5 rounded-btn font-mono"
                style={{ background: 'rgba(177,198,249,0.1)', color: '#4a6cf7', border: '1px solid rgba(177,198,249,0.15)' }}
              >
                {ns}
              </span>
            ))}
          </div>
        </Section>
      )}

      {/* NS History timeline */}
      {data.ns_history.length > 0 && (
        <Section title="NS Geçmişi" icon={<Clock className="w-4 h-4" />}>
          {!data.has_api_key && (
            <div
              className="flex items-center gap-2 text-xs px-3 py-2 rounded mb-3"
              style={{ background: 'rgba(0,6,30,0.09)', color: '#6b7388' }}
            >
              <Info className="w-3.5 h-3.5 flex-shrink-0" />
              Tam NS geçmişi için SecurityTrails API anahtarı gereklidir. Şu an yalnızca mevcut NS gösteriliyor.
            </div>
          )}
          <div className="flex flex-col gap-0">
            {data.ns_history.map((entry, i) => (
              <NSEntry key={i} entry={entry} isLast={i === data.ns_history.length - 1} />
            ))}
          </div>
        </Section>
      )}
    </div>
  )
}

function InfoCard({ icon, label, value, color, truncate }) {
  return (
    <div
      className="px-4 py-3 rounded-card flex flex-col gap-1"
      style={{ background: '#ffffff', border: '1px solid rgba(0,6,30,0.09)' }}
    >
      <div className="flex items-center gap-1.5 text-xs mb-0.5" style={{ color: '#6b7388' }}>
        <span style={{ color }}>{icon}</span>
        {label}
      </div>
      <p
        className={`text-sm font-medium ${truncate ? 'truncate' : ''}`}
        style={{ color: '#1a1d2e' }}
        title={truncate ? value : undefined}
      >
        {value}
      </p>
    </div>
  )
}

function Section({ title, icon, children }) {
  return (
    <div
      className="px-5 py-4 rounded-card"
      style={{ background: '#ffffff', border: '1px solid rgba(0,6,30,0.09)' }}
    >
      <div className="flex items-center gap-2 mb-3">
        <span style={{ color: '#3b7eff' }}>{icon}</span>
        <h2 className="text-sm font-semibold" style={{ color: '#1a1d2e' }}>{title}</h2>
      </div>
      {children}
    </div>
  )
}

function NSEntry({ entry, isLast }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="flex gap-3">
      {/* Timeline line */}
      <div className="flex flex-col items-center" style={{ width: 20 }}>
        <div
          className="w-3 h-3 rounded-full flex-shrink-0 mt-1"
          style={{
            background: entry.is_current ? '#4a6cf7' : 'rgba(66,71,84,0.6)',
            border: entry.is_current ? '2px solid rgba(177,198,249,0.4)' : '2px solid rgba(0,6,30,0.12)',
          }}
        />
        {!isLast && (
          <div className="flex-1 w-px mt-1" style={{ background: 'rgba(0,6,30,0.12)', minHeight: 16 }} />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 pb-4">
        <div className="flex items-center gap-2 flex-wrap mb-1.5">
          <span className="text-xs" style={{ color: '#6b7388' }}>
            {entry.first_seen} — {entry.last_seen}
          </span>
          {entry.is_current && (
            <span
              className="text-xs px-1.5 py-0.5 rounded"
              style={{ background: 'rgba(177,198,249,0.12)', color: '#4a6cf7' }}
            >
              Güncel
            </span>
          )}
          {entry.organizations.length > 0 && (
            <span className="text-xs" style={{ color: '#6b7388' }}>
              · {entry.organizations.join(', ')}
            </span>
          )}
        </div>

        {/* NS list */}
        <div className="flex flex-col gap-1">
          {(expanded ? entry.nameservers : entry.nameservers.slice(0, 2)).map((ns, i) => (
            <span
              key={i}
              className="text-xs font-mono px-2 py-1 rounded inline-block w-fit"
              style={{ background: 'rgba(0,6,30,0.09)', color: '#c4c7cf' }}
            >
              {ns}
            </span>
          ))}
          {entry.nameservers.length > 2 && (
            <button
              onClick={() => setExpanded(v => !v)}
              className="flex items-center gap-1 text-xs mt-0.5 w-fit"
              style={{ color: '#6b7388' }}
            >
              {expanded
                ? <><ChevronUp className="w-3 h-3" /> Gizle</>
                : <><ChevronDown className="w-3 h-3" /> +{entry.nameservers.length - 2} daha</>
              }
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
