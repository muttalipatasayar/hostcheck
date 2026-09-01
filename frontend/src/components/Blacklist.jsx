import { useState } from 'react'
import {
  ShieldAlert, Search, Loader2, Clock,
  CheckCircle2, XCircle, AlertTriangle, Info, Server,
} from 'lucide-react'
import axios from 'axios'
import toast from 'react-hot-toast'
import { useTarget, useCommittedTarget } from '../context/TargetContext'
import { apiHataMesaji } from '../lib/apiHata'

const STATUS_CONFIG = {
  healthy: { icon: CheckCircle2,  color: '#4a6cf7', dot: 'status-dot-healthy', label: 'Temiz' },
  error:   { icon: XCircle,       color: '#ffb4ab', dot: 'status-dot-error',   label: 'Listeli' },
  warning: { icon: AlertTriangle, color: '#ffb786', dot: 'status-dot-warning', label: 'Doğrulanamadı' },
  info:    { icon: Info,          color: '#3b7eff', dot: 'status-dot-pending', label: 'Bilgi' },
}

export default function Blacklist() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const { target, commitTarget } = useTarget()

  const check = async (value) => {
    setLoading(true)
    setResult(null)
    try {
      const res = await axios.post('/api/blacklist/check', { target: value })
      setResult(res.data)
    } catch (err) {
      toast.error(apiHataMesaji(err, 'Kara liste kontrolü başarısız'))
    } finally {
      setLoading(false)
    }
  }

  // autoRun:true — idempotent DNS sorguları; commit edilmiş hedefle sekmeye
  // gelindiğinde kendiliğinden de çalışır
  useCommittedTarget(check, { autoRun: true })

  const overallCfg = result ? STATUS_CONFIG[result.overall] : null

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Başlık */}
      <div className="px-8 pt-8 pb-6">
        <div className="flex items-center gap-3 mb-1">
          <div
            className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, rgba(255,180,171,0.2) 0%, rgba(255,146,133,0.15) 100%)' }}
          >
            <ShieldAlert className="w-4 h-4" style={{ color: '#ff8a80' }} />
          </div>
          <h1 className="text-headline-md font-semibold" style={{ color: '#1a1d2e', letterSpacing: '-0.01em' }}>
            Blacklist / RBL
          </h1>
        </div>
        <p className="text-body-md" style={{ color: '#6b7388' }}>
          IP'nin spam kara listelerindeki durumu — 28 bölge, kod açıklamalarıyla
        </p>
      </div>

      {/* Çalıştır */}
      <div className="px-8 pb-5">
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={commitTarget}
            disabled={loading || !target.trim()}
            className="btn-primary flex-shrink-0 flex items-center gap-2"
          >
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" /> Kontrol ediliyor…</>
              : <><Search className="w-4 h-4" /> {target.trim() ? `${target.trim()} kontrol et` : 'Kontrol Et'}</>
            }
          </button>
          {!target.trim() && (
            <p className="text-body-sm" style={{ color: '#9da5be' }}>
              Üstteki hedef çubuğuna IPv4 adresi veya alan adı yazın.
            </p>
          )}
        </div>
      </div>

      <div className="px-8 pb-10 flex flex-col gap-4">
        {/* Yükleniyor */}
        {loading && (
          <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
            {[1, 2, 3, 4, 5, 6].map(i => (
              <div key={i} className="flex items-center gap-4 px-5 py-3 animate-pulse"
                style={{ borderBottom: '1px solid rgba(0,6,30,0.04)' }}>
                <div className="h-3 w-40 rounded" style={{ background: '#f2f4fa' }} />
                <div className="h-3 flex-1 rounded" style={{ background: '#f0f2f8' }} />
              </div>
            ))}
          </div>
        )}

        {result && !loading && (
          <>
            {/* Özet */}
            <div className="rounded-card px-5 py-4" style={{ background: '#ffffff' }}>
              <div className="flex items-center gap-2 mb-2">
                <span className={`status-dot ${overallCfg?.dot}`} />
                <p className="text-body-sm font-medium" style={{ color: overallCfg?.color }}>
                  {overallCfg?.label}
                </p>
                <span className="font-mono text-body-sm" style={{ color: '#3b7eff' }}>{result.target}</span>
              </div>
              <p className="text-body-sm" style={{ color: '#4a5068' }}>{result.summary}</p>
            </div>

            {/* Her IP ayrı raporlanır */}
            {result.ips.map((rep) => (
              <div key={rep.ip} className="flex flex-col gap-2">
                <div className="flex items-center gap-2 px-1">
                  <Server className="w-4 h-4" style={{ color: '#6b7388' }} />
                  <p className="text-body-sm font-semibold font-mono" style={{ color: '#1a1d2e' }}>{rep.ip}</p>
                  <p className="text-label-sm" style={{ color: '#9da5be' }}>
                    {rep.listed_count > 0
                      ? `${rep.listed_count}/${rep.checked_count} listede`
                      : `${rep.checked_count} bölge kontrol edildi`}
                    {rep.unverified_count > 0 ? ` · ${rep.unverified_count} doğrulanamadı` : ''}
                  </p>
                </div>

                <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
                  {rep.zones.map((z, i) => {
                    const cfg = STATUS_CONFIG[z.status]
                    return (
                      <div key={i} className="flex items-start gap-3 px-5 py-2.5"
                        style={{ borderBottom: '1px solid rgba(0,6,30,0.04)' }}>
                        <span className={`status-dot ${cfg.dot} mt-1.5 flex-shrink-0`} />
                        <div className="flex-shrink-0" style={{ minWidth: 200 }}>
                          <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>{z.name}</p>
                          <p className="text-label-sm font-mono" style={{ color: '#9da5be' }}>{z.zone}</p>
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-body-sm" style={{ color: z.status === 'error' ? '#c14953' : '#6b7388' }}>
                            {z.detail}
                          </p>
                          {z.codes.length > 0 && (
                            <p className="text-label-sm font-mono mt-0.5" style={{ color: '#9da5be' }}>
                              {z.codes.join(' · ')}
                            </p>
                          )}
                        </div>
                        <div className="flex-shrink-0 text-right">
                          <span className="text-label-sm font-medium" style={{ color: cfg.color }}>{cfg.label}</span>
                          {z.latency_ms != null && (
                            <p className="text-label-sm font-mono flex items-center gap-1 justify-end" style={{ color: '#9da5be' }}>
                              <Clock className="w-3 h-3" />{z.latency_ms}ms
                            </p>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}

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
              style={{ background: 'rgba(255,180,171,0.06)' }}>
              <ShieldAlert className="w-7 h-7 opacity-30" style={{ color: '#ff8a80' }} />
            </div>
            <p className="text-title-md font-medium mb-1" style={{ color: '#4a5068' }}>Blacklist / RBL</p>
            <p className="text-body-md text-center max-w-xs" style={{ color: '#6b7388' }}>
              Üstteki hedef çubuğuna IPv4 adresi veya alan adı yazın — alan adı girilirse çözülen her IP ayrı raporlanır
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
