import { useMemo } from 'react'
import { Ticket, AlertCircle, Clock, CheckCircle2, TrendingUp } from 'lucide-react'
import { format } from 'date-fns'
import { tr } from 'date-fns/locale'

const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 }

function StatCard({ label, value, sub, accent }) {
  return (
    <div
      className="rounded-card px-5 py-4 flex flex-col gap-1"
      style={{ background: '#1a1c20' }}
    >
      <p className="text-label-md" style={{ color: '#8d9099' }}>{label}</p>
      <p
        className="text-headline-lg font-semibold"
        style={{ color: accent || '#e3e5ef', letterSpacing: '-0.015em' }}
      >
        {value}
      </p>
      {sub && (
        <p className="text-label-sm" style={{ color: '#424754' }}>{sub}</p>
      )}
    </div>
  )
}

export default function Dashboard({ tickets, onNavigate }) {
  const stats = useMemo(() => {
    const open = tickets.filter(t => t.status === 'open').length
    const inProgress = tickets.filter(t => t.status === 'in_progress').length
    const resolved = tickets.filter(t => t.status === 'resolved').length
    const critical = tickets.filter(t => t.priority === 'critical').length
    return { open, inProgress, resolved, critical, total: tickets.length }
  }, [tickets])

  const recentTickets = useMemo(() => {
    return [...tickets]
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
      .slice(0, 5)
  }, [tickets])

  const urgentTickets = useMemo(() => {
    return tickets
      .filter(t => t.status !== 'resolved' && t.status !== 'closed')
      .sort((a, b) => priorityOrder[a.priority] - priorityOrder[b.priority])
      .slice(0, 3)
  }, [tickets])

  return (
    <div className="flex flex-col gap-8 p-8 animate-fade-in">
      {/* Header */}
      <div>
        <h1
          className="text-headline-md font-semibold"
          style={{ color: '#e3e5ef', letterSpacing: '-0.01em' }}
        >
          Dashboard
        </h1>
        <p className="text-body-md mt-1" style={{ color: '#8d9099' }}>
          {format(new Date(), "d MMMM yyyy, EEEE", { locale: tr })}
        </p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Toplam Talep"
          value={stats.total}
          sub="Tüm zamanlar"
          accent="#e3e5ef"
        />
        <StatCard
          label="Açık"
          value={stats.open}
          sub="Yanıt bekliyor"
          accent="#adc6ff"
        />
        <StatCard
          label="İşlemde"
          value={stats.inProgress}
          sub="Aktif çalışma"
          accent="#ffb786"
        />
        <StatCard
          label="Kritik"
          value={stats.critical}
          sub="Yüksek öncelik"
          accent="#ffb4ab"
        />
      </div>

      {/* Two column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Recent tickets */}
        <div
          className="lg:col-span-3 rounded-card p-5"
          style={{ background: '#1a1c20' }}
        >
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-title-md font-medium" style={{ color: '#e3e5ef' }}>
              Son Talepler
            </h2>
            <button
              onClick={() => onNavigate('tickets')}
              className="text-label-md transition-colors"
              style={{ color: '#adc6ff' }}
            >
              Tümünü gör →
            </button>
          </div>

          {recentTickets.length === 0 ? (
            <div className="py-8 text-center" style={{ color: '#8d9099' }}>
              <Ticket className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-body-md">Henüz talep yok</p>
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {recentTickets.map((ticket) => (
                <button
                  key={ticket.id}
                  onClick={() => onNavigate('ticket-detail', ticket.id)}
                  className="flex items-center gap-4 py-3 px-3 rounded-btn text-left transition-all duration-150 group"
                  style={{ background: 'transparent' }}
                  onMouseEnter={e => e.currentTarget.style.background = '#282a2e'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <StatusDot status={ticket.status} />
                  <div className="flex-1 min-w-0">
                    <p className="text-body-sm font-medium truncate" style={{ color: '#e3e5ef' }}>
                      {ticket.subject}
                    </p>
                    <p className="text-label-sm truncate" style={{ color: '#8d9099' }}>
                      {ticket.customer_name} · {ticket.ticket_no}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1 flex-shrink-0">
                    <PriorityBadge priority={ticket.priority} />
                    <p className="text-label-sm" style={{ color: '#424754' }}>
                      {format(new Date(ticket.created_at), 'dd.MM HH:mm')}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Urgent tickets */}
        <div
          className="lg:col-span-2 rounded-card p-5"
          style={{ background: '#1a1c20' }}
        >
          <div className="flex items-center gap-2 mb-5">
            <AlertCircle className="w-4 h-4" style={{ color: '#ffb4ab' }} />
            <h2 className="text-title-md font-medium" style={{ color: '#e3e5ef' }}>
              Acil Talepler
            </h2>
          </div>

          {urgentTickets.length === 0 ? (
            <div className="py-8 text-center" style={{ color: '#8d9099' }}>
              <CheckCircle2 className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-body-md">Acil talep yok</p>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {urgentTickets.map((ticket) => (
                <button
                  key={ticket.id}
                  onClick={() => onNavigate('ticket-detail', ticket.id)}
                  className="flex flex-col gap-1.5 p-3 rounded-btn text-left transition-all duration-150"
                  style={{ background: '#282a2e' }}
                  onMouseEnter={e => e.currentTarget.style.background = '#333539'}
                  onMouseLeave={e => e.currentTarget.style.background = '#282a2e'}
                >
                  <div className="flex items-center justify-between">
                    <PriorityBadge priority={ticket.priority} />
                    <p className="text-label-sm" style={{ color: '#8d9099' }}>
                      {ticket.ticket_no}
                    </p>
                  </div>
                  <p className="text-body-sm font-medium line-clamp-2" style={{ color: '#e3e5ef' }}>
                    {ticket.subject}
                  </p>
                  <p className="text-label-sm" style={{ color: '#8d9099' }}>
                    {ticket.customer_name}
                    {ticket.domain && ` · ${ticket.domain}`}
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StatusDot({ status }) {
  const map = {
    open: 'status-dot-healthy',
    in_progress: 'status-dot-warning',
    resolved: 'status-dot-pending',
    closed: 'status-dot-pending',
  }
  return <span className={`status-dot ${map[status] || 'status-dot-pending'}`} />
}

function PriorityBadge({ priority }) {
  const map = {
    critical: { label: 'Kritik', cls: 'badge-critical' },
    high: { label: 'Yüksek', cls: 'badge-high' },
    medium: { label: 'Orta', cls: 'badge-medium' },
    low: { label: 'Düşük', cls: 'badge-low' },
  }
  const { label, cls } = map[priority] || { label: priority, cls: 'badge-low' }
  return <span className={`badge ${cls}`}>{label}</span>
}
