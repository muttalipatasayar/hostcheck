import { clsx } from 'clsx'
import { ChevronRight, Server, X } from 'lucide-react'
import { TOOLS } from '../lib/tools'
import { useApiHealth } from '../hooks/useApiHealth'

// Gösterge artık GERÇEK: /api/health yoklanıyor. Eskiden sabit metindi ve
// backend çökmüşken bile "Sistem Sağlıklı" yazıyordu.
const SAGLIK = {
  saglikli:   { nokta: 'status-dot-healthy', renk: '#4a6cf7', baslik: 'Sistem Sağlıklı' },
  kopuk:      { nokta: 'status-dot-error',   renk: '#ef4444', baslik: 'API Yanıt Vermiyor' },
  bilinmiyor: { nokta: 'status-dot-pending', renk: '#6b7388', baslik: 'Bağlantı Kontrol Ediliyor' },
}

export default function Sidebar({ activeView, onNavigate, onKapat }) {
  const { durum, gecikmeMs } = useApiHealth()
  const s = SAGLIK[durum] || SAGLIK.bilinmiyor
  return (
    <aside
      className="flex flex-col h-full w-60 px-3 py-5 gap-1"
      style={{ background: '#ffffff' }}
    >
      {/* Logo */}
      <div className="px-3 pb-6 pt-1">
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #3b7eff 0%, #4d8eff 100%)' }}
          >
            <Server className="w-4 h-4" style={{ color: '#002e6a' }} />
          </div>
          <div>
            <p className="font-semibold text-body-md" style={{ color: '#1a1d2e' }}>HostCheck</p>
            <p className="text-label-sm" style={{ color: '#6b7388' }}>Destek Paneli</p>
          </div>
          {/* Yalnızca mobilde: çekmeceyi kapat */}
          {onKapat && (
            <button
              onClick={onKapat}
              aria-label="Menüyü kapat"
              className="lg:hidden ml-auto p-1.5 rounded-btn"
              style={{ color: '#6b7388' }}
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Sistem sağlığı — /api/health yoklamasına bağlı */}
      <div
        className="mx-0 mb-4 px-3 py-3 rounded-card flex items-center gap-3"
        style={{ background: '#f0f2f7' }}
        title={durum === 'kopuk' ? 'Backend yanıt vermiyor' : undefined}
      >
        <div className="relative flex items-center justify-center">
          <span className={`status-dot ${s.nokta}`} />
          {durum === 'saglikli' && (
            <span
              className="absolute w-2 h-2 rounded-full animate-ping"
              style={{ background: 'rgba(177,198,249,0.3)' }}
            />
          )}
        </div>
        <div className="min-w-0">
          <p className="text-label-sm font-medium" style={{ color: s.renk }}>{s.baslik}</p>
          <p className="text-label-sm truncate" style={{ color: '#6b7388' }}>
            {durum === 'saglikli'
              ? `API yanıt veriyor${gecikmeMs != null ? ` · ${gecikmeMs} ms` : ''}`
              : durum === 'kopuk'
                ? 'Sonuçlar yüklenemeyebilir'
                : 'Yoklanıyor…'}
          </p>
        </div>
      </div>

      {/* Navigation */}
      {/* min-h-0 + overflow-y-auto: 900px'lik ekranda liste alt bloğu taşıyordu. */}
      <nav className="flex flex-col gap-0.5 flex-1 min-h-0 overflow-y-auto">
        <p className="px-3 pt-1 pb-2 text-label-sm font-medium uppercase tracking-wider" style={{ color: '#9da5be' }}>
          Navigasyon
        </p>
        {TOOLS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onNavigate(id)}
            className={clsx('nav-item w-full text-left', { 'nav-item-active': activeView === id })}
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            <span className="flex-1">{label}</span>
            {activeView === id && (
              <ChevronRight className="w-3 h-3" style={{ color: '#3b7eff' }} />
            )}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="pt-3 flex-shrink-0">
        <div className="tonal-divider mb-3" />
        <div className="px-3 flex items-center gap-2">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-label-sm font-semibold"
            style={{ background: 'rgba(59,127,255,0.12)', color: '#3b7eff' }}
          >
            D
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-body-sm font-medium truncate" style={{ color: '#1a1d2e' }}>Destek Uzmanı</p>
            <p className="text-label-sm truncate" style={{ color: '#6b7388' }}>Aktif oturum</p>
          </div>
        </div>
      </div>
    </aside>
  )
}
