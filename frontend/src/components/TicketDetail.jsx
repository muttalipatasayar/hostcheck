import { useState, useEffect } from 'react'
import {
  ArrowLeft, Globe, Mail, User, Clock, Tag,
  Server, Edit2, Check, X, ChevronDown
} from 'lucide-react'
import { format } from 'date-fns'
import { tr } from 'date-fns/locale'
import toast from 'react-hot-toast'
import { ticketsApi } from '../api/client'
import CheckResults from './CheckResults'
import AIResponsePanel from './AIResponsePanel'

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
  return <span className={`badge badge-${priority}`}>{PRIORITY_LABELS[priority] || priority}</span>
}

function MetaItem({ icon: Icon, label, value, mono }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-label-sm" style={{ color: '#9da5be' }}>{label}</p>
      <div className="flex items-center gap-1.5">
        <Icon className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#6b7388' }} />
        <p
          className={mono ? 'text-label-md font-mono' : 'text-body-sm'}
          style={{ color: '#4a5068' }}
        >
          {value || <span style={{ color: '#9da5be' }}>—</span>}
        </p>
      </div>
    </div>
  )
}

export default function TicketDetail({ ticketId, onBack, onTicketUpdated }) {
  const [ticket, setTicket] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editingStatus, setEditingStatus] = useState(false)
  const [editingNotes, setEditingNotes] = useState(false)
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadTicket()
  }, [ticketId])

  const loadTicket = async () => {
    setLoading(true)
    try {
      const res = await ticketsApi.get(ticketId)
      setTicket(res.data)
      setNotes(res.data.notes || '')
    } catch {
      toast.error('Talep yüklenemedi')
    } finally {
      setLoading(false)
    }
  }

  const updateStatus = async (newStatus) => {
    setSaving(true)
    try {
      const res = await ticketsApi.update(ticketId, { status: newStatus })
      setTicket(res.data)
      onTicketUpdated && onTicketUpdated(res.data)
      toast.success('Durum güncellendi')
      setEditingStatus(false)
    } catch {
      toast.error('Durum güncellenemedi')
    } finally {
      setSaving(false)
    }
  }

  const saveNotes = async () => {
    setSaving(true)
    try {
      const res = await ticketsApi.update(ticketId, { notes })
      setTicket(res.data)
      setEditingNotes(false)
      toast.success('Notlar kaydedildi')
    } catch {
      toast.error('Notlar kaydedilemedi')
    } finally {
      setSaving(false)
    }
  }

  const handleCheckResultsSaved = (data) => {
    setTicket(prev => ({ ...prev, check_results: data }))
  }

  const handleAiResponseSaved = (response) => {
    setTicket(prev => ({ ...prev, ai_response: response }))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-3">
          <div className="spinner w-6 h-6" />
          <p className="text-body-md" style={{ color: '#6b7388' }}>Yükleniyor...</p>
        </div>
      </div>
    )
  }

  if (!ticket) return null

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Top bar */}
      <div className="flex items-center gap-4 px-8 pt-7 pb-5 flex-shrink-0">
        <button onClick={onBack} className="btn-ghost -ml-1">
          <ArrowLeft className="w-4 h-4" />
          Talepler
        </button>
        <span style={{ color: '#9da5be' }}>/</span>
        <p className="text-body-sm font-mono" style={{ color: '#6b7388' }}>
          {ticket.ticket_no}
        </p>
        <div className="flex-1" />
        <PriorityBadge priority={ticket.priority} />
      </div>

      {/* Main content */}
      <div className="flex-1 px-8 pb-10 flex flex-col gap-6">
        {/* Title + status */}
        <div
          className="rounded-card px-6 py-5"
          style={{ background: '#ffffff' }}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <h1
                className="text-title-lg font-semibold mb-1"
                style={{ color: '#1a1d2e' }}
              >
                {ticket.subject}
              </h1>
              <div className="flex items-center gap-4">
                <p className="text-label-md" style={{ color: '#6b7388' }}>
                  {format(new Date(ticket.created_at), "d MMMM yyyy, HH:mm", { locale: tr })}
                </p>
                {ticket.category && (
                  <span
                    className="text-label-sm px-2 py-0.5 rounded"
                    style={{ background: 'rgba(173,198,255,0.08)', color: '#3b7eff' }}
                  >
                    {ticket.category}
                  </span>
                )}
              </div>
            </div>

            {/* Status control */}
            <div className="relative flex-shrink-0">
              {editingStatus ? (
                <div
                  className="absolute right-0 top-0 z-10 rounded-card overflow-hidden shadow-float py-1"
                  style={{ background: '#f2f4fa', minWidth: '140px' }}
                >
                  {Object.entries(STATUS_LABELS).map(([val, label]) => (
                    <button
                      key={val}
                      onClick={() => updateStatus(val)}
                      disabled={saving}
                      className="flex items-center w-full px-4 py-2.5 text-left text-body-sm transition-colors"
                      style={{ color: ticket.status === val ? '#3b7eff' : '#4a5068' }}
                      onMouseEnter={e => e.currentTarget.style.background = '#e8eaf3'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      {label}
                    </button>
                  ))}
                  <div className="tonal-divider my-1" />
                  <button
                    onClick={() => setEditingStatus(false)}
                    className="flex items-center gap-2 w-full px-4 py-2 text-body-sm"
                    style={{ color: '#6b7388' }}
                  >
                    <X className="w-3.5 h-3.5" /> İptal
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setEditingStatus(true)}
                  className={`badge badge-${ticket.status} flex items-center gap-1.5 cursor-pointer`}
                >
                  {STATUS_LABELS[ticket.status]}
                  <ChevronDown className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          {/* Meta grid */}
          <div
            className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-4 mt-5 pt-5"
            style={{ borderTop: '1px solid rgba(0,6,30,0.06)' }}
          >
            <MetaItem icon={User} label="Müşteri" value={ticket.customer_name} />
            <MetaItem icon={Mail} label="E-posta" value={ticket.customer_email} mono />
            <MetaItem icon={Globe} label="Domain" value={ticket.domain} mono />
            <MetaItem icon={Server} label="Sunucu IP" value={ticket.server_ip} mono />
          </div>
        </div>

        {/* Description */}
        <div
          className="rounded-card px-6 py-5"
          style={{ background: '#ffffff' }}
        >
          <p className="text-label-sm font-medium mb-3" style={{ color: '#9da5be' }}>
            MÜŞTERİ AÇIKLAMASI
          </p>
          <p
            className="text-body-md whitespace-pre-wrap"
            style={{ color: '#4a5068', lineHeight: '1.7' }}
          >
            {ticket.description}
          </p>
        </div>

        {/* Two-column: checks + AI */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <CheckResults
            ticket={ticket}
            onResultsSaved={handleCheckResultsSaved}
          />
          <AIResponsePanel
            ticket={ticket}
            onResponseSaved={handleAiResponseSaved}
          />
        </div>

        {/* Internal notes */}
        <div
          className="rounded-card overflow-hidden"
          style={{ background: '#ffffff' }}
        >
          <div
            className="flex items-center justify-between px-5 py-4"
            style={{ borderBottom: '1px solid rgba(0,6,30,0.06)' }}
          >
            <div className="flex items-center gap-2">
              <Tag className="w-4 h-4" style={{ color: '#3b7eff' }} />
              <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>
                Dahili Notlar
              </p>
            </div>
            {!editingNotes ? (
              <button onClick={() => setEditingNotes(true)} className="btn-ghost">
                <Edit2 className="w-3.5 h-3.5" /> Düzenle
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  onClick={saveNotes}
                  disabled={saving}
                  className="btn-primary py-1.5 px-3 text-label-md"
                >
                  {saving ? <span className="spinner" /> : <Check className="w-3.5 h-3.5" />}
                  Kaydet
                </button>
                <button
                  onClick={() => { setEditingNotes(false); setNotes(ticket.notes || '') }}
                  className="btn-secondary py-1.5 px-3 text-label-md"
                >
                  <X className="w-3.5 h-3.5" /> İptal
                </button>
              </div>
            )}
          </div>

          <div className="px-5 py-4">
            {editingNotes ? (
              <textarea
                className="textarea-field w-full"
                rows={5}
                placeholder="Dahili notlarınızı buraya yazın... (müşteriye gösterilmez)"
                value={notes}
                onChange={e => setNotes(e.target.value)}
              />
            ) : (
              <p
                className="text-body-md whitespace-pre-wrap"
                style={{ color: notes ? '#4a5068' : '#9da5be' }}
              >
                {notes || 'Henüz not eklenmemiş. Düzenle butonuna tıklayın.'}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
