import { useState, useMemo, useEffect, useRef } from 'react'
import {
  MessageSquare, Search, Copy, Check, Pencil, Trash2, Plus, Star,
  X, ChevronDown, ChevronUp, Download, Hash, Globe, Server, Shield,
  Mail, Network, Database, Layers, AlertTriangle, Save,
} from 'lucide-react'
import defaultData from '../data/hazirYanitlar.json'

// ─── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'hazir_yanitlar_v3'
const USAGE_KEY   = 'hazir_yanitlar_usage'
const PINS_KEY    = 'hazir_yanitlar_pins'

const CATEGORIES = [
  { id: 'Tümü',       label: 'Tümü',       icon: Layers      },
  { id: 'Alan Adı',   label: 'Alan Adı',   icon: Globe       },
  { id: 'Hosting',    label: 'Hosting',    icon: Server      },
  { id: 'SSL',        label: 'SSL',        icon: Shield      },
  { id: 'E-posta',    label: 'E-posta',    icon: Mail        },
  { id: 'DNS',        label: 'DNS',        icon: Network     },
  { id: 'Veritabanı', label: 'Veritabanı', icon: Database    },
  { id: 'Genel',      label: 'Genel',      icon: MessageSquare },
]

const CAT_COLORS = {
  'Alan Adı':   '#adc6ff',
  'Hosting':    '#a8d5a2',
  'SSL':        '#7dd5f4',
  'E-posta':    '#f5d37a',
  'DNS':        '#d4a8ff',
  'Veritabanı': '#ffb4ab',
  'Genel':      '#8d9099',
  'Tümü':       '#adc6ff',
}

const trLower = (s) => s.toLocaleLowerCase('tr-TR')

// ─── Storage helpers ──────────────────────────────────────────────────────────

const storage = {
  load(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback }
    catch { return fallback }
  },
  save(key, val) {
    try { localStorage.setItem(key, JSON.stringify(val)) } catch {}
  },
}

const EMPTY_FORM = { title: '', content: '', category: 'Genel' }

// ─── Main component ───────────────────────────────────────────────────────────

export default function HazirYanitlar() {
  const [responses, setResponses] = useState(() => storage.load(STORAGE_KEY, defaultData))
  const [usage,     setUsage]     = useState(() => storage.load(USAGE_KEY,   {}))
  const [pins,      setPins]      = useState(() => new Set(storage.load(PINS_KEY, [])))

  const [activeCat,   setActiveCat]   = useState('Tümü')
  const [query,       setQuery]       = useState('')
  const [expandedId,  setExpandedId]  = useState(null)
  const [copiedId,    setCopiedId]    = useState(null)
  const [deleteId,    setDeleteId]    = useState(null)

  // Modal state — single source of truth
  const [modal, setModal] = useState(null)
  // modal = null | { mode: 'add' } | { mode: 'edit', response: {...} }

  // ── Derived data ────────────────────────────────────────────────────────
  const catCounts = useMemo(() => {
    const m = {}
    responses.forEach(r => { m[r.category] = (m[r.category] || 0) + 1 })
    return m
  }, [responses])

  const filtered = useMemo(() => {
    let list = [...responses]
    if (activeCat !== 'Tümü') list = list.filter(r => r.category === activeCat)
    if (query.trim()) {
      const q = trLower(query.trim())
      list = list.filter(r =>
        trLower(r.title).includes(q) || trLower(r.content).includes(q)
      )
    }
    list.sort((a, b) => (pins.has(b.id) ? 1 : 0) - (pins.has(a.id) ? 1 : 0))
    return list
  }, [responses, activeCat, query, pins])

  // ── Mutators ────────────────────────────────────────────────────────────
  const saveResponses = (next) => {
    setResponses(next)
    storage.save(STORAGE_KEY, next)
  }

  const handleSave = (form, id = null) => {
    let next
    if (id) {
      next = responses.map(r => r.id === id ? { ...r, ...form } : r)
    } else {
      const newId = Math.max(0, ...responses.map(r => r.id)) + 1
      next = [{ id: newId, ...form }, ...responses]
    }
    saveResponses(next)
    setModal(null)
  }

  const handleDelete = (id) => {
    saveResponses(responses.filter(r => r.id !== id))
    setDeleteId(null)
  }

  const handleCopy = (r) => {
    navigator.clipboard.writeText(r.content).then(() => {
      setCopiedId(r.id)
      setTimeout(() => setCopiedId(null), 2000)
      const next = { ...usage, [r.id]: (usage[r.id] || 0) + 1 }
      setUsage(next)
      storage.save(USAGE_KEY, next)
    })
  }

  const handlePin = (id) => {
    const next = new Set(pins)
    next.has(id) ? next.delete(id) : next.add(id)
    setPins(next)
    storage.save(PINS_KEY, [...next])
  }

  const handleExport = () => {
    const text = responses.map(r => `=== ${r.title} ===\n${r.content}`).join('\n\n')
    const url  = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
    Object.assign(document.createElement('a'), { href: url, download: 'hazir_yanitlar.txt' }).click()
    URL.revokeObjectURL(url)
  }

  const activeCatColor = CAT_COLORS[activeCat] ?? CAT_COLORS['Genel']

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <>
      <div className="flex h-full overflow-hidden">

        {/* ═══ LEFT SIDEBAR ═══════════════════════════════════════════════ */}
        <aside
          className="flex flex-col w-52 flex-shrink-0 h-full"
          style={{ background: '#1a1c20', borderRight: '1px solid rgba(66,71,84,0.4)' }}
        >
          {/* Title */}
          <div className="px-4 pt-6 pb-3 flex-shrink-0">
            <div className="flex items-center gap-2.5">
              <div
                className="w-7 h-7 rounded-btn flex items-center justify-center flex-shrink-0"
                style={{ background: 'linear-gradient(135deg,rgba(245,211,122,.25),rgba(255,195,100,.15))' }}
              >
                <MessageSquare className="w-3.5 h-3.5" style={{ color: '#f5d37a' }} />
              </div>
              <div>
                <p className="text-body-sm font-semibold" style={{ color: '#e3e5ef' }}>Hazır Yanıtlar</p>
                <p className="text-label-sm" style={{ color: '#424754' }}>{responses.length} yanıt</p>
              </div>
            </div>
          </div>

          {/* Search */}
          <div className="px-3 pb-3 flex-shrink-0">
            <div className="relative">
              <Search
                className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 pointer-events-none"
                style={{ color: '#424754' }}
              />
              <input
                type="text"
                className="input-field w-full text-body-sm"
                style={{ paddingLeft: '2rem', paddingRight: query ? '2rem' : undefined }}
                placeholder="Ara…"
                value={query}
                onChange={e => setQuery(e.target.value)}
              />
              {query && (
                <button
                  onClick={() => setQuery('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 hover:opacity-70"
                  style={{ color: '#424754' }}
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            {query && (
              <p className="text-label-sm mt-1.5 px-1" style={{ color: '#424754' }}>
                {filtered.length} sonuç
              </p>
            )}
          </div>

          {/* Categories */}
          <nav className="flex-1 overflow-y-auto px-2 pb-2">
            <p
              className="px-2 pt-1 pb-2 text-label-sm font-medium uppercase tracking-wider"
              style={{ color: '#424754' }}
            >
              Kategoriler
            </p>
            {CATEGORIES.map(({ id, label, icon: Icon }) => {
              const count    = id === 'Tümü' ? responses.length : (catCounts[id] || 0)
              const isActive = activeCat === id
              const color    = CAT_COLORS[id] ?? CAT_COLORS['Genel']
              if (count === 0 && id !== 'Tümü') return null
              return (
                <button
                  key={id}
                  onClick={() => { setActiveCat(id); setQuery('') }}
                  className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-btn text-left mb-0.5 transition-colors"
                  style={isActive ? { background: `${color}18`, color } : { color: '#8d9099' }}
                >
                  <Icon className="w-4 h-4 flex-shrink-0" />
                  <span className="flex-1 text-body-sm font-medium">{label}</span>
                  <span
                    className="text-label-sm px-1.5 py-0.5 rounded"
                    style={isActive
                      ? { background: `${color}25`, color }
                      : { background: 'rgba(66,71,84,0.4)', color: '#424754' }
                    }
                  >
                    {count}
                  </span>
                </button>
              )
            })}
          </nav>

          {/* Footer */}
          <div className="px-3 py-4 flex-shrink-0" style={{ borderTop: '1px solid rgba(66,71,84,0.4)' }}>
            <button
              onClick={() => setModal({ mode: 'add' })}
              className="btn-primary w-full flex items-center justify-center gap-2 mb-2"
            >
              <Plus className="w-4 h-4" />
              Yeni Yanıt Ekle
            </button>
            <button
              onClick={handleExport}
              className="btn-ghost w-full flex items-center justify-center gap-2 text-label-sm"
            >
              <Download className="w-3.5 h-3.5" />
              Dışa Aktar
            </button>
          </div>
        </aside>

        {/* ═══ CONTENT AREA ═══════════════════════════════════════════════ */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

          {/* Header */}
          <div
            className="px-6 pt-6 pb-4 flex-shrink-0 flex items-center justify-between"
            style={{ borderBottom: '1px solid rgba(66,71,84,0.3)' }}
          >
            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="text-headline-md font-semibold" style={{ color: '#e3e5ef' }}>
                  {activeCat === 'Tümü' ? 'Tüm Yanıtlar' : activeCat}
                </h2>
                <span
                  className="text-label-sm px-2 py-0.5 rounded"
                  style={{ background: `${activeCatColor}18`, color: activeCatColor }}
                >
                  {filtered.length}
                </span>
              </div>
              {query && (
                <p className="text-body-sm mt-0.5" style={{ color: '#8d9099' }}>
                  "<span style={{ color: activeCatColor }}>{query}</span>" için sonuçlar
                </p>
              )}
            </div>

            {/* Quick-add button visible in header too */}
            <button
              onClick={() => setModal({ mode: 'add' })}
              className="btn-ghost flex items-center gap-1.5 text-body-sm"
            >
              <Plus className="w-4 h-4" />
              Yeni
            </button>
          </div>

          {/* List */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-64 gap-3">
                <Search className="w-10 h-10" style={{ color: '#282a2e' }} />
                <p className="text-body-md" style={{ color: '#424754' }}>
                  {query ? `"${query}" ile eşleşen yanıt bulunamadı.` : 'Bu kategoride henüz yanıt yok.'}
                </p>
                {query && (
                  <button onClick={() => setQuery('')} className="btn-ghost text-body-sm">
                    Aramayı temizle
                  </button>
                )}
              </div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {filtered.map(r => (
                  <ResponseCard
                    key={r.id}
                    r={r}
                    isCopied={copiedId === r.id}
                    isPinned={pins.has(r.id)}
                    isDeleting={deleteId === r.id}
                    isExpanded={expandedId === r.id}
                    useCount={usage[r.id] || 0}
                    showCategory={activeCat === 'Tümü' || !!query}
                    onCopy={() => handleCopy(r)}
                    onPin={() => handlePin(r.id)}
                    onEdit={() => setModal({ mode: 'edit', response: r })}
                    onDeleteAsk={() => setDeleteId(r.id)}
                    onDeleteConfirm={() => handleDelete(r.id)}
                    onDeleteCancel={() => setDeleteId(null)}
                    onToggleExpand={() => setExpandedId(expandedId === r.id ? null : r.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══ MODAL ════════════════════════════════════════════════════════ */}
      {modal && (
        <ResponseModal
          mode={modal.mode}
          initialData={modal.mode === 'edit' ? modal.response : null}
          onSave={(form) => handleSave(form, modal.mode === 'edit' ? modal.response.id : null)}
          onClose={() => setModal(null)}
        />
      )}
    </>
  )
}

// ─── Response Card ────────────────────────────────────────────────────────────

function ResponseCard({
  r, isCopied, isPinned, isDeleting, isExpanded, useCount, showCategory,
  onCopy, onPin, onEdit, onDeleteAsk, onDeleteConfirm, onDeleteCancel, onToggleExpand,
}) {
  const color = CAT_COLORS[r.category] ?? CAT_COLORS['Genel']
  const isLong = r.content.length > 180

  return (
    <article
      className="rounded-card overflow-hidden transition-all"
      style={{
        background: '#1a1c20',
        border: isPinned
          ? '1px solid rgba(245,211,122,0.35)'
          : '1px solid rgba(66,71,84,0.25)',
      }}
    >
      {/* Card top bar — colored line for pinned */}
      {isPinned && (
        <div className="h-0.5 w-full" style={{ background: 'rgba(245,211,122,0.5)' }} />
      )}

      <div className="p-4">
        {/* Header */}
        <div className="flex items-start gap-3 mb-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <span className="text-body-sm font-semibold leading-snug" style={{ color: '#e3e5ef' }}>
                {r.title}
              </span>
              {isPinned && (
                <Star className="w-3 h-3 flex-shrink-0" style={{ color: '#f5d37a', fill: '#f5d37a' }} />
              )}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {showCategory && (
                <span
                  className="text-label-sm px-1.5 py-0.5 rounded"
                  style={{ background: `${color}18`, color }}
                >
                  {r.category}
                </span>
              )}
              {useCount > 0 && (
                <span
                  className="text-label-sm flex items-center gap-1"
                  style={{ color: '#424754' }}
                  title={`${useCount} kez kopyalandı`}
                >
                  <Hash className="w-3 h-3" />{useCount}
                </span>
              )}
            </div>
          </div>

          {/* Actions */}
          {!isDeleting && (
            <div className="flex items-center gap-1 flex-shrink-0">
              <ActionBtn
                onClick={onPin}
                title={isPinned ? 'Sabitlemeyi kaldır' : 'Sabitle'}
                color={isPinned ? '#f5d37a' : '#424754'}
              >
                <Star className="w-3.5 h-3.5" style={isPinned ? { fill: '#f5d37a' } : {}} />
              </ActionBtn>

              <ActionBtn onClick={onCopy} title="İçeriği kopyala" color={isCopied ? '#a8d5a2' : '#8d9099'}>
                {isCopied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              </ActionBtn>

              <button
                onClick={onEdit}
                title="Düzenle"
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-btn text-label-sm font-medium transition-colors hover:opacity-80"
                style={{ background: 'rgba(173,198,255,0.1)', color: '#adc6ff' }}
              >
                <Pencil className="w-3 h-3" />
                Düzenle
              </button>

              <ActionBtn onClick={onDeleteAsk} title="Sil" color='#8d9099'>
                <Trash2 className="w-3.5 h-3.5" />
              </ActionBtn>
            </div>
          )}
        </div>

        {/* Delete confirm */}
        {isDeleting && (
          <div
            className="flex items-center gap-3 px-3 py-2.5 rounded-btn mb-3"
            style={{ background: 'rgba(255,180,171,0.08)', border: '1px solid rgba(255,180,171,0.25)' }}
          >
            <AlertTriangle className="w-4 h-4 flex-shrink-0" style={{ color: '#ffb4ab' }} />
            <p className="text-body-sm flex-1" style={{ color: '#ffb4ab' }}>
              Bu yanıtı silmek istediğinizden emin misiniz?
            </p>
            <button
              onClick={onDeleteConfirm}
              className="text-label-sm px-3 py-1.5 rounded-btn font-medium"
              style={{ background: 'rgba(255,180,171,0.2)', color: '#ffb4ab' }}
            >
              Evet, Sil
            </button>
            <button
              onClick={onDeleteCancel}
              className="text-label-sm px-3 py-1.5 rounded-btn font-medium"
              style={{ background: 'rgba(255,255,255,0.06)', color: '#8d9099' }}
            >
              İptal
            </button>
          </div>
        )}

        {/* Content */}
        <div
          className="text-body-sm rounded-btn px-3 py-2.5 select-text"
          style={{
            background: '#111317',
            color: '#c9cdd6',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            lineHeight: '1.65',
            maxHeight: isExpanded ? 'none' : '76px',
            overflow: 'hidden',
            position: 'relative',
            cursor: isLong ? 'pointer' : 'default',
          }}
          onClick={() => isLong && onToggleExpand()}
        >
          {r.content}
          {!isExpanded && isLong && (
            <div
              className="absolute bottom-0 left-0 right-0 h-8 pointer-events-none"
              style={{ background: 'linear-gradient(transparent, #111317)' }}
            />
          )}
        </div>

        {/* Footer row */}
        <div className="flex items-center justify-between mt-1.5">
          <div>
            {isLong && (
              <button
                onClick={onToggleExpand}
                className="flex items-center gap-1 text-label-sm hover:opacity-70"
                style={{ color: '#424754' }}
              >
                {isExpanded
                  ? <><ChevronUp className="w-3 h-3" />Daralt</>
                  : <><ChevronDown className="w-3 h-3" />Tamamını Gör</>
                }
              </button>
            )}
          </div>
          {isCopied && (
            <span className="flex items-center gap-1 text-label-sm" style={{ color: '#a8d5a2' }}>
              <Check className="w-3 h-3" />Kopyalandı!
            </span>
          )}
        </div>
      </div>
    </article>
  )
}

// ─── Small icon button helper ─────────────────────────────────────────────────

function ActionBtn({ onClick, title, color, children }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="p-1.5 rounded hover:opacity-70 transition-opacity"
      style={{ color }}
    >
      {children}
    </button>
  )
}

// ─── Modal (Add / Edit) ───────────────────────────────────────────────────────

function ResponseModal({ mode, initialData, onSave, onClose }) {
  const isEdit = mode === 'edit'
  const titleText = isEdit ? 'Yanıtı Düzenle' : 'Yeni Yanıt Ekle'

  const [form,   setForm]   = useState(
    isEdit
      ? { title: initialData.title, content: initialData.content, category: initialData.category }
      : EMPTY_FORM
  )
  const [errors, setErrors] = useState({})
  const titleRef = useRef(null)

  useEffect(() => {
    setTimeout(() => titleRef.current?.focus(), 50)
  }, [])

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const validate = () => {
    const e = {}
    if (!form.title.trim())   e.title   = 'Başlık zorunludur.'
    if (!form.content.trim()) e.content = 'İçerik zorunludur.'
    setErrors(e)
    return Object.keys(e).length === 0
  }

  const handleSubmit = () => {
    if (!validate()) return
    onSave(form)
  }

  const cats = CATEGORIES.filter(c => c.id !== 'Tümü')
  const catColor = CAT_COLORS[form.category] ?? CAT_COLORS['Genel']

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(2px)' }}
      onMouseDown={e => e.target === e.currentTarget && onClose()}
    >
      <div
        className="w-full max-w-2xl flex flex-col rounded-card"
        style={{
          background: '#1e2025',
          border: '1px solid rgba(66,71,84,0.6)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
          maxHeight: '90vh',
        }}
      >
        {/* Modal header */}
        <div
          className="flex items-center justify-between px-6 py-4 flex-shrink-0"
          style={{ borderBottom: '1px solid rgba(66,71,84,0.4)' }}
        >
          <div className="flex items-center gap-3">
            <div
              className="w-7 h-7 rounded-btn flex items-center justify-center"
              style={{ background: isEdit ? 'rgba(173,198,255,0.12)' : 'rgba(168,213,162,0.12)' }}
            >
              {isEdit
                ? <Pencil className="w-3.5 h-3.5" style={{ color: '#adc6ff' }} />
                : <Plus   className="w-3.5 h-3.5" style={{ color: '#a8d5a2' }} />
              }
            </div>
            <h2 className="text-body-md font-semibold" style={{ color: '#e3e5ef' }}>
              {titleText}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded hover:opacity-70 transition-opacity"
            style={{ color: '#8d9099' }}
            title="Kapat (Esc)"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Modal body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-5">

          {/* Title field */}
          <div>
            <label className="text-label-sm font-medium mb-1.5 block" style={{ color: '#8d9099' }}>
              Başlık <span style={{ color: '#ffb4ab' }}>*</span>
            </label>
            <input
              ref={titleRef}
              type="text"
              className="input-field w-full"
              placeholder="Yanıt başlığını girin…"
              value={form.title}
              onChange={e => { setForm(f => ({ ...f, title: e.target.value })); setErrors(v => ({ ...v, title: '' })) }}
              onKeyDown={e => e.key === 'Enter' && handleSubmit()}
              style={errors.title ? { borderColor: 'rgba(255,180,171,0.5)' } : {}}
            />
            {errors.title && (
              <p className="text-label-sm mt-1 flex items-center gap-1" style={{ color: '#ffb4ab' }}>
                <AlertTriangle className="w-3 h-3" />{errors.title}
              </p>
            )}
          </div>

          {/* Category field */}
          <div>
            <label className="text-label-sm font-medium mb-1.5 block" style={{ color: '#8d9099' }}>
              Kategori
            </label>
            <div className="flex flex-wrap gap-2">
              {cats.map(c => {
                const cc = CAT_COLORS[c.id] ?? CAT_COLORS['Genel']
                const isSelected = form.category === c.id
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setForm(f => ({ ...f, category: c.id }))}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-label-sm font-medium transition-all"
                    style={isSelected
                      ? { background: `${cc}20`, color: cc, border: `1px solid ${cc}50` }
                      : { background: 'rgba(66,71,84,0.25)', color: '#8d9099', border: '1px solid rgba(66,71,84,0.4)' }
                    }
                  >
                    <c.icon className="w-3 h-3" />
                    {c.label}
                  </button>
                )
              })}
            </div>
            {/* Selected category preview */}
            <div
              className="mt-2 px-3 py-1.5 rounded-btn flex items-center gap-2 text-label-sm"
              style={{ background: `${catColor}12`, color: catColor }}
            >
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: catColor }} />
              Seçili: <strong>{form.category}</strong>
            </div>
          </div>

          {/* Content field */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-label-sm font-medium" style={{ color: '#8d9099' }}>
                İçerik <span style={{ color: '#ffb4ab' }}>*</span>
              </label>
              <span className="text-label-sm" style={{ color: '#424754' }}>
                {form.content.length} karakter
              </span>
            </div>
            <textarea
              className="input-field w-full font-mono text-body-sm"
              placeholder="Yanıt metnini buraya yazın…"
              value={form.content}
              onChange={e => { setForm(f => ({ ...f, content: e.target.value })); setErrors(v => ({ ...v, content: '' })) }}
              rows={10}
              style={{
                resize: 'vertical',
                minHeight: '180px',
                ...(errors.content ? { borderColor: 'rgba(255,180,171,0.5)' } : {}),
              }}
            />
            {errors.content && (
              <p className="text-label-sm mt-1 flex items-center gap-1" style={{ color: '#ffb4ab' }}>
                <AlertTriangle className="w-3 h-3" />{errors.content}
              </p>
            )}
          </div>
        </div>

        {/* Modal footer */}
        <div
          className="flex items-center justify-between px-6 py-4 flex-shrink-0"
          style={{ borderTop: '1px solid rgba(66,71,84,0.4)' }}
        >
          <p className="text-label-sm" style={{ color: '#424754' }}>
            Escape ile kapatabilirsiniz
          </p>
          <div className="flex items-center gap-2">
            <button onClick={onClose} className="btn-ghost">
              İptal
            </button>
            <button
              onClick={handleSubmit}
              className="btn-primary flex items-center gap-2"
            >
              <Save className="w-4 h-4" />
              {isEdit ? 'Değişiklikleri Kaydet' : 'Yanıt Ekle'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
