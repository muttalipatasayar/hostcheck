import { clsx } from 'clsx'
import {
  Ticket, LayoutDashboard, ChevronRight,
  Plus, Server, Zap, Shield, Wrench, History
} from 'lucide-react'

const navItems = [
  { id: 'dashboard',   label: 'Dashboard',     icon: LayoutDashboard },
  { id: 'quick-check', label: 'Hızlı Kontrol', icon: Zap },
  { id: 'ssl-tools',   label: 'SSL Araçları',  icon: Shield },
  { id: 'dns-toolbox', label: 'DNS Toolbox',   icon: Wrench },
  { id: 'dns-history', label: 'DNS History',   icon: History },
  { id: 'tickets',     label: 'Talepler',      icon: Ticket },
  { id: 'new-ticket',  label: 'Yeni Talep',    icon: Plus },
]

export default function Sidebar({ activeView, onNavigate, ticketCount = 0 }) {
  return (
    <aside
      className="flex flex-col h-full w-60 px-3 py-5 gap-1"
      style={{ background: '#1a1c20' }}
    >
      {/* Logo */}
      <div className="px-3 pb-6 pt-1">
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #adc6ff 0%, #4d8eff 100%)' }}
          >
            <Server className="w-4 h-4" style={{ color: '#002e6a' }} />
          </div>
          <div>
            <p className="font-semibold text-on-surface-DEFAULT text-body-md" style={{ color: '#e3e5ef' }}>
              HostCheck
            </p>
            <p className="text-label-sm" style={{ color: '#8d9099' }}>
              Destek Paneli
            </p>
          </div>
        </div>
      </div>

      {/* System health indicator */}
      <div
        className="mx-0 mb-4 px-3 py-3 rounded-card flex items-center gap-3"
        style={{ background: '#111317' }}
      >
        <div className="relative flex items-center justify-center">
          <span className="status-dot status-dot-healthy" />
          <span
            className="absolute w-2 h-2 rounded-full animate-ping"
            style={{ background: 'rgba(177, 198, 249, 0.3)' }}
          />
        </div>
        <div>
          <p className="text-label-sm font-medium" style={{ color: '#b1c6f9' }}>
            Sistem Sağlıklı
          </p>
          <p className="text-label-sm" style={{ color: '#8d9099' }}>
            API bağlantısı aktif
          </p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-0.5 flex-1">
        <p className="px-3 pt-1 pb-2 text-label-sm font-medium uppercase tracking-wider" style={{ color: '#424754' }}>
          Navigasyon
        </p>

        {navItems.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => onNavigate(id)}
            className={clsx('nav-item w-full text-left', {
              'nav-item-active': activeView === id,
            })}
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            <span className="flex-1">{label}</span>
            {id === 'tickets' && ticketCount > 0 && (
              <span
                className="text-label-sm px-1.5 py-0.5 rounded"
                style={{ background: 'rgba(173, 198, 255, 0.1)', color: '#adc6ff' }}
              >
                {ticketCount}
              </span>
            )}
            {activeView === id && (
              <ChevronRight className="w-3 h-3" style={{ color: '#adc6ff' }} />
            )}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="pt-4">
        <div className="tonal-divider mb-4" />
        <div className="px-3 flex items-center gap-2">
          <div
            className="w-7 h-7 rounded-full flex items-center justify-center text-label-sm font-semibold"
            style={{ background: 'rgba(173, 198, 255, 0.15)', color: '#adc6ff' }}
          >
            D
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-body-sm font-medium truncate" style={{ color: '#e3e5ef' }}>
              Destek Uzmanı
            </p>
            <p className="text-label-sm truncate" style={{ color: '#8d9099' }}>
              Aktif oturum
            </p>
          </div>
        </div>
      </div>
    </aside>
  )
}
