import { useState } from 'react'
import { Search, Filter, Plus, Ticket, ChevronRight } from 'lucide-react'
import { format } from 'date-fns'
import { clsx } from 'clsx'

const STATUS_LABELS = {
  open: 'Açık',
  in_progress: 'İşlemde',
  resolved: 'Çözüldü',
  closed: 'Kapalı',
}

const PRIORITY_LABELS = {
  critical: 'Kritik',
  high: 'Yüksek',
  medium: 'Orta',
  low: 'Düşük',
}

function PriorityBadge({ priority }) {
  const cls = `badge badge-${priority}`
  return <span className={cls}>{PRIORITY_LABELS[priority] || priority}</span>
}

function StatusBadge({ status }) {
  const cls = `badge badge-${status}`
  return <span className={cls}>{STATUS_LABELS[status] || status}</span>
}

function StatusDot({ status }) {
  const map = {
    open: 'status-dot-healthy',
    in_progress: 'status-dot-warning',
    resolved: 'status-dot-pending',
    closed: 'status-dot-pending',
  }
  return <span className={`status-dot ${map[status] || 'status-dot-pending'} flex-shrink-0`} />
}

export default function TicketList({ tickets, onSelect, onNewTicket, loading }) {
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [priorityFilter, setPriorityFilter] = useState('all')

  const filtered = tickets.filter(t => {
    const matchSearch =
      !search ||
      t.subject.toLowerCase().includes(search.toLowerCase()) ||
      t.customer_name.toLowerCase().includes(search.toLowerCase()) ||
      t.ticket_no.toLowerCase().includes(search.toLowerCase()) ||
      (t.domain || '').toLowerCase().includes(search.toLowerCase())

    const matchStatus = statusFilter === 'all' || t.status === statusFilter
    const matchPriority = priorityFilter === 'all' || t.priority === priorityFilter

    return matchSearch && matchStatus && matchPriority
  })

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-8 pt-8 pb-5">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1
              className="text-headline-md font-semibold"
              style={{ color: '#1a1d2e', letterSpacing: '-0.01em' }}
            >
              Destek Talepleri
            </h1>
            <p className="text-body-md mt-1" style={{ color: '#6b7388' }}>
              {tickets.length} talep · {tickets.filter(t => t.status === 'open').length} açık
            </p>
          </div>
          <button onClick={onNewTicket} className="btn-primary">
            <Plus className="w-4 h-4" />
            Yeni Talep
          </button>
        </div>

        {/* Search & filters */}
        <div className="flex gap-3 items-center">
          <div className="relative flex-1 max-w-xs">
            <Search
              className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5"
              style={{ color: '#6b7388' }}
            />
            <input
              type="text"
              placeholder="Talep, müşteri, domain ara..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="input-field pl-9"
            />
          </div>

          <select
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}
            className="input-field w-auto pr-8"
            style={{ background: '#eaedf5', color: '#4a5068', cursor: 'pointer' }}
          >
            <option value="all">Tüm Durumlar</option>
            <option value="open">Açık</option>
            <option value="in_progress">İşlemde</option>
            <option value="resolved">Çözüldü</option>
            <option value="closed">Kapalı</option>
          </select>

          <select
            value={priorityFilter}
            onChange={e => setPriorityFilter(e.target.value)}
            className="input-field w-auto pr-8"
            style={{ background: '#eaedf5', color: '#4a5068', cursor: 'pointer' }}
          >
            <option value="all">Tüm Öncelikler</option>
            <option value="critical">Kritik</option>
            <option value="high">Yüksek</option>
            <option value="medium">Orta</option>
            <option value="low">Düşük</option>
          </select>
        </div>
      </div>

      {/* Ticket list */}
      <div className="flex-1 overflow-y-auto px-8 pb-8">
        {loading ? (
          <div className="py-20 text-center">
            <div className="spinner mx-auto mb-3" />
            <p className="text-body-md" style={{ color: '#6b7388' }}>Yükleniyor...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="py-20 text-center">
            <Ticket className="w-10 h-10 mx-auto mb-3 opacity-20" style={{ color: '#4a5068' }} />
            <p className="text-title-md font-medium mb-1" style={{ color: '#4a5068' }}>
              {search || statusFilter !== 'all' || priorityFilter !== 'all'
                ? 'Filtrelerle eşleşen talep bulunamadı'
                : 'Henüz talep yok'}
            </p>
            <p className="text-body-md" style={{ color: '#6b7388' }}>
              {!search && statusFilter === 'all' && priorityFilter === 'all' && 'Yeni bir talep oluşturun'}
            </p>
          </div>
        ) : (
          /* Table-like layout */
          <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
            {/* Column headers */}
            <div
              className="grid gap-4 px-4 py-3 border-b"
              style={{
                gridTemplateColumns: '1fr 180px 100px 90px 110px 24px',
                borderColor: 'rgba(0,6,30,0.06)'
              }}
            >
              {['Konu / Müşteri', 'Domain', 'Durum', 'Öncelik', 'Tarih', ''].map(col => (
                <p key={col} className="text-label-sm font-medium" style={{ color: '#9da5be' }}>
                  {col}
                </p>
              ))}
            </div>

            {filtered.map((ticket, i) => (
              <button
                key={ticket.id}
                onClick={() => onSelect(ticket.id)}
                className="w-full grid gap-4 px-4 py-3.5 text-left transition-all duration-100 group"
                style={{
                  gridTemplateColumns: '1fr 180px 100px 90px 110px 24px',
                  background: 'transparent',
                  borderBottom: i < filtered.length - 1 ? '1px solid rgba(66,71,84,0.12)' : 'none',
                }}
                onMouseEnter={e => e.currentTarget.style.background = '#f2f4fa'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                {/* Subject + customer */}
                <div className="flex items-center gap-3 min-w-0">
                  <StatusDot status={ticket.status} />
                  <div className="min-w-0">
                    <p className="text-body-sm font-medium truncate" style={{ color: '#1a1d2e' }}>
                      {ticket.subject}
                    </p>
                    <p className="text-label-sm truncate mt-0.5" style={{ color: '#6b7388' }}>
                      {ticket.customer_name} · {ticket.ticket_no}
                    </p>
                  </div>
                </div>

                {/* Domain */}
                <div className="flex items-center">
                  <p className="text-label-md font-mono truncate" style={{ color: '#4a5068' }}>
                    {ticket.domain || <span style={{ color: '#9da5be' }}>—</span>}
                  </p>
                </div>

                {/* Status */}
                <div className="flex items-center">
                  <StatusBadge status={ticket.status} />
                </div>

                {/* Priority */}
                <div className="flex items-center">
                  <PriorityBadge priority={ticket.priority} />
                </div>

                {/* Date */}
                <div className="flex items-center">
                  <p className="text-label-md" style={{ color: '#6b7388' }}>
                    {format(new Date(ticket.created_at), 'dd.MM.yy HH:mm')}
                  </p>
                </div>

                {/* Arrow */}
                <div className="flex items-center justify-end">
                  <ChevronRight
                    className="w-4 h-4 transition-transform duration-150 group-hover:translate-x-0.5"
                    style={{ color: '#9da5be' }}
                  />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
