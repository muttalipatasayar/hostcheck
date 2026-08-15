import { useState } from 'react'
import {
  Mail, Search, Loader2, Info,
  CheckCircle2, XCircle, AlertTriangle,
} from 'lucide-react'
import axios from 'axios'
import toast from 'react-hot-toast'
import { useTarget, useCommittedTarget } from '../context/TargetContext'

const STATUS_CONFIG = {
  healthy: { color: '#4a6cf7', dot: 'status-dot-healthy', icon: CheckCircle2 },
  warning: { color: '#ffb786', dot: 'status-dot-warning', icon: AlertTriangle },
  error:   { color: '#ffb4ab', dot: 'status-dot-error',   icon: XCircle },
  info:    { color: '#3b7eff', dot: 'status-dot-pending', icon: Info },
}

function scoreColor(score) {
  if (score >= 85) return '#4a6cf7'
  if (score >= 55) return '#ffb786'
  return '#ffb4ab'
}

export default function MailHealth() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [selector, setSelector] = useState('')
  const { target, commitTarget } = useTarget()

  const check = async (domain) => {
    setLoading(true)
    setResult(null)
    try {
      const res = await axios.post('/api/mail-health/check', {
        domain,
        dkim_selector: selector.trim() || null,
      })
      setResult(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Mail sağlık kontrolü başarısız')
    } finally {
      setLoading(false)
    }
  }

  // autoRun:false — SMTP el sıkışması + DKIM keşfi pahalı; yalnızca açık
  // Enter/Çalıştır ile çalışır
  useCommittedTarget(check, { autoRun: false })

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Başlık */}
      <div className="px-8 pt-8 pb-6">
        <div className="flex items-center gap-3 mb-1">
          <div
            className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, rgba(195,177,225,0.25) 0%, rgba(168,85,247,0.15) 100%)' }}
          >
            <Mail className="w-4 h-4" style={{ color: '#c3b1e1' }} />
          </div>
          <h1 className="text-headline-md font-semibold" style={{ color: '#1a1d2e', letterSpacing: '-0.01em' }}>
            Mail Sağlığı
          </h1>
        </div>
        <p className="text-body-md" style={{ color: '#6b7388' }}>
          "Mailim gitmiyor" çağrısının ilk durağı — MX · SPF · DKIM · DMARC · SMTP · PTR, 0-100 skor
        </p>
      </div>

      {/* Çalıştır + selector */}
      <div className="px-8 pb-5 flex flex-col gap-3">
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={commitTarget}
            disabled={loading || !target.trim()}
            className="btn-primary flex-shrink-0 flex items-center gap-2"
          >
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Kontrol ediliyor…</>
              : <><Search className="w-4 h-4" /> {target.trim() ? `${target.trim()} mail sağlığı` : 'Kontrol Et'}</>
            }
          </button>
          {!target.trim() && (
            <p className="text-body-sm" style={{ color: '#9da5be' }}>
              Üstteki hedef çubuğuna bir alan adı yazın.
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 rounded-card px-3 py-2 w-fit" style={{ background: '#ffffff' }}>
          <span className="text-label-sm font-mono flex-shrink-0" style={{ color: '#f9d4b1' }}>DKIM selector</span>
          <input
            type="text"
            value={selector}
            onChange={e => setSelector(e.target.value.toLowerCase().trim())}
            placeholder="boş bırakılırsa yaygın selector'lar denenir"
            className="bg-transparent outline-none text-body-sm font-mono"
            style={{ color: '#1a1d2e', caretColor: '#f9d4b1', width: '300px' }}
          />
        </div>
      </div>

      <div className="px-8 pb-10 flex flex-col gap-4">
        {/* Yükleniyor */}
        {loading && (
          <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
            {[1, 2, 3, 4, 5, 6].map(i => (
              <div key={i} className="flex items-center gap-4 px-5 py-3.5 animate-pulse"
                style={{ borderBottom: '1px solid rgba(0,6,30,0.04)' }}>
                <div className="w-8 h-8 rounded-btn" style={{ background: '#f2f4fa' }} />
                <div className="flex-1 flex flex-col gap-1.5">
                  <div className="h-3 rounded w-28" style={{ background: '#f2f4fa' }} />
                  <div className="h-3 rounded w-64" style={{ background: '#f0f2f8' }} />
                </div>
                <div className="h-5 w-14 rounded" style={{ background: '#f2f4fa' }} />
              </div>
            ))}
          </div>
        )}

        {result && !loading && (
          <>
            {/* Skor kartı */}
            <div className="rounded-card px-5 py-4 flex items-center gap-5" style={{ background: '#ffffff' }}>
              <div
                className="w-20 h-20 rounded-full flex flex-col items-center justify-center flex-shrink-0"
                style={{ border: `4px solid ${scoreColor(result.score)}` }}
              >
                <span className="text-title-lg font-bold font-mono" style={{ color: scoreColor(result.score) }}>
                  {result.score}
                </span>
                <span className="text-label-sm" style={{ color: '#9da5be' }}>/100</span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-body-sm font-medium mb-1" style={{ color: '#1a1d2e' }}>
                  <span className="font-mono" style={{ color: '#3b7eff' }}>{result.domain}</span>
                </p>
                <p className="text-body-sm" style={{ color: '#4a5068' }}>{result.summary}</p>
                {result.egress_ip && (
                  <p className="text-label-sm mt-1 flex items-center gap-1" style={{ color: '#9da5be' }}>
                    <Info className="w-3 h-3" />
                    Panelin çıkış IP'si: <span className="font-mono">{result.egress_ip}</span>
                  </p>
                )}
              </div>
            </div>

            {/* Altı bölüm */}
            <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
              {result.checks.map((c, i) => {
                const cfg = STATUS_CONFIG[c.status] || STATUS_CONFIG.info
                return (
                  <div key={i} className="flex items-start gap-4 px-5 py-3.5"
                    style={{ borderBottom: '1px solid rgba(0,6,30,0.04)' }}>
                    <span className={`status-dot ${cfg.dot} mt-1.5 flex-shrink-0`} />
                    <div className="flex-shrink-0" style={{ minWidth: 130 }}>
                      <p className="text-body-sm font-semibold" style={{ color: '#1a1d2e' }}>{c.label}</p>
                      <p className="text-label-sm font-mono" style={{ color: cfg.color }}>
                        {c.score}/{c.max_score} puan
                      </p>
                    </div>
                    <div className="flex-1 min-w-0">
                      {c.value && (
                        <p className="text-body-sm font-mono break-all" style={{ color: '#1a1d2e' }}>{c.value}</p>
                      )}
                      {c.detail && (
                        <p className="text-label-sm mt-0.5" style={{ color: '#6b7388' }}>{c.detail}</p>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Hata analizi (ERROR_DB) */}
            {result.error_analysis && (
              <div className="rounded-card px-5 py-4"
                style={{ background: 'rgba(255,180,171,0.06)', border: '1px solid rgba(255,180,171,0.15)' }}>
                <p className="text-label-sm font-semibold mb-2" style={{ color: '#ffb4ab' }}>
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
              style={{ background: 'rgba(195,177,225,0.08)' }}>
              <Mail className="w-7 h-7 opacity-30" style={{ color: '#c3b1e1' }} />
            </div>
            <p className="text-title-md font-medium mb-1" style={{ color: '#4a5068' }}>Mail Sağlığı</p>
            <p className="text-body-md text-center max-w-xs" style={{ color: '#6b7388' }}>
              Üstteki hedef çubuğuna alan adı yazın ve Enter'a basın — altı bölümde puanlanır
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
