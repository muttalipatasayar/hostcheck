import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import {
  MessageSquare, Search, Copy, Check, Pencil, Trash2, Plus, Star,
  X, ChevronDown, ChevronUp, Download, Globe, Server, Shield,
  Mail, Network, Database, Layers, AlertTriangle, Save, Hash,
  Command, CornerDownLeft,
} from 'lucide-react'
import defaultData from '../data/hazirYanitlar.json'

// ─── Sabitler ─────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'hazir_yanitlar_v3'
const USAGE_KEY   = 'hazir_yanitlar_usage'
const PINS_KEY    = 'hazir_yanitlar_pins'

const CATEGORIES = [
  { id: 'Tümü',       label: 'Tümü',       icon: Layers,       color: '#adc6ff' },
  { id: 'Alan Adı',   label: 'Alan Adı',   icon: Globe,        color: '#adc6ff' },
  { id: 'Hosting',    label: 'Hosting',    icon: Server,       color: '#a8d5a2' },
  { id: 'SSL',        label: 'SSL',        icon: Shield,       color: '#7dd5f4' },
  { id: 'E-posta',    label: 'E-posta',    icon: Mail,         color: '#f5d37a' },
  { id: 'DNS',        label: 'DNS',        icon: Network,      color: '#d4a8ff' },
  { id: 'Veritabanı', label: 'Veritabanı', icon: Database,     color: '#ffb4ab' },
  { id: 'Genel',      label: 'Genel',      icon: MessageSquare, color: '#8d9099' },
]

const CAT_META = Object.fromEntries(CATEGORIES.map(c => [c.id, c]))

const trLower = s => s.toLocaleLowerCase('tr-TR')

// ─── Storage ──────────────────────────────────────────────────────────────────

const store = {
  load: (key, fb) => { try { return JSON.parse(localStorage.getItem(key)) ?? fb } catch { return fb } },
  save: (key, v)  => { try { localStorage.setItem(key, JSON.stringify(v)) } catch {} },
}

// ─── Arama vurgulama ──────────────────────────────────────────────────────────

function Highlight({ text, query }) {
  if (!query || !text) return <>{text}</>
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  let parts
  try { parts = text.split(new RegExp(`(${escaped})`, 'gi')) }
  catch { return <>{text}</> }
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1
          ? <mark key={i} style={{ background: 'rgba(245,211,122,0.25)', color: '#f5d37a', borderRadius: 2, padding: '0 1px' }}>{p}</mark>
          : p
      )}
    </>
  )
}

// ─── Ana bileşen ──────────────────────────────────────────────────────────────

export default function HazirYanitlar() {
  const [responses, setResponses] = useState(() => store.load(STORAGE_KEY, defaultData))
  const [usage,     setUsage]     = useState(() => store.load(USAGE_KEY, {}))
  const [pins,      setPins]      = useState(() => new Set(store.load(PINS_KEY, [])))

  const [activeCat, setActiveCat] = useState('Tümü')
  const [query,     setQuery]     = useState('')
  const [copiedId,  setCopiedId]  = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [modal,     setModal]     = useState(null)

  const searchRef = useRef(null)

  // "/" kısayol tuşu → aramaya odaklan
  useEffect(() => {
    const handler = e => {
      if (e.key === '/' && document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault()
        searchRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // ── Türev veri ────────────────────────────────────────────────────────────
  const catCounts = useMemo(() => {
    const m = {}
    responses.forEach(r => { m[r.category] = (m[r.category] || 0) + 1 })
    return m
  }, [responses])

  const filtered = useMemo(() => {
    let list = activeCat === 'Tümü' ? [...responses] : responses.filter(r => r.category === activeCat)
    if (query.trim()) {
      const q = trLower(query.trim())
      list = list.filter(r => trLower(r.title).includes(q) || trLower(r.content).includes(q))
    }
    return list
  }, [responses, activeCat, query])

  // Gruplandırılmış görünüm (Tümü + arama yok)
  const grouped = useMemo(() => {
    if (activeCat !== 'Tümü' || query.trim()) return null
    const pinned = filtered.filter(r => pins.has(r.id))
    const byCat = {}
    CATEGORIES.filter(c => c.id !== 'Tümü').forEach(c => {
      const items = filtered.filter(r => r.category === c.id && !pins.has(r.id))
      if (items.length) byCat[c.id] = items
    })
    return { pinned, byCat }
  }, [filtered, activeCat, query, pins])

  // ── Mutators ──────────────────────────────────────────────────────────────
  const saveResponses = useCallback(next => {
    setResponses(next)
    store.save(STORAGE_KEY, next)
  }, [])

  const handleSave = useCallback((form, id = null) => {
    const next = id
      ? responses.map(r => r.id === id ? { ...r, ...form } : r)
      : [{ id: Math.max(0, ...responses.map(r => r.id)) + 1, ...form }, ...responses]
    saveResponses(next)
    setModal(null)
  }, [responses, saveResponses])

  const handleDelete = useCallback(id => {
    saveResponses(responses.filter(r => r.id !== id))
  }, [responses, saveResponses])

  const handleCopy = useCallback(r => {
    navigator.clipboard.writeText(r.content).then(() => {
      setCopiedId(r.id)
      setTimeout(() => setCopiedId(null), 1800)
      const next = { ...usage, [r.id]: (usage[r.id] || 0) + 1 }
      setUsage(next)
      store.save(USAGE_KEY, next)
    })
  }, [usage])

  const handlePin = useCallback(id => {
    const next = new Set(pins)
    next.has(id) ? next.delete(id) : next.add(id)
    setPins(next)
    store.save(PINS_KEY, [...next])
  }, [pins])

  const handleExport = useCallback(() => {
    const text = responses.map(r => `=== ${r.title} ===\n${r.content}`).join('\n\n')
    const url  = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
    Object.assign(document.createElement('a'), { href: url, download: 'hazir_yanitlar.txt' }).click()
    URL.revokeObjectURL(url)
  }, [responses])

  const pinCount = [...pins].filter(id => responses.some(r => r.id === id)).length

  // Ortak kart props'ları
  const cardProps = r => ({
    r,
    isCopied:   copiedId  === r.id,
    isPinned:   pins.has(r.id),
    isExpanded: expandedId === r.id,
    useCount:   usage[r.id] || 0,
    query,
    onCopy:   () => handleCopy(r),
    onPin:    () => handlePin(r.id),
    onEdit:   () => setModal({ mode: 'edit', response: r }),
    onDelete: () => handleDelete(r.id),
    onToggleExpand: () => setExpandedId(expandedId === r.id ? null : r.id),
  })

  return (
    <>
      <div className="flex h-full overflow-hidden">

        {/* ═══ SOL SIDEBAR ════════════════════════════════════════════════ */}
        <aside
          className="flex flex-col w-56 flex-shrink-0 h-full"
          style={{ background: '#1a1c20', borderRight: '1px solid rgba(66,71,84,0.35)' }}
        >
          {/* Başlık */}
          <div className="px-4 pt-5 pb-3 flex-shrink-0">
            <div className="flex items-center gap-2 mb-0.5">
              <div className="w-6 h-6 rounded flex items-center justify-center"
                style={{ background: 'rgba(245,211,122,0.15)' }}>
                <MessageSquare className="w-3.5 h-3.5" style={{ color: '#f5d37a' }} />
              </div>
              <p className="text-body-sm font-semibold" style={{ color: '#e3e5ef' }}>Hazır Yanıtlar</p>
            </div>
            <p className="text-label-sm pl-8" style={{ color: '#424754' }}>
              {responses.length} yanıt{pinCount > 0 ? ` · ${pinCount} sabitlenmiş` : ''}
            </p>
          </div>

          {/* Arama */}
          <div className="px-3 pb-3 flex-shrink-0">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 pointer-events-none"
                style={{ color: '#424754' }} />
              <input
                ref={searchRef}
                type="text"
                className="input-field w-full text-body-sm"
                style={{ paddingLeft: '2rem', paddingRight: query ? '2rem' : '2.5rem' }}
                placeholder="Ara…"
                value={query}
                onChange={e => setQuery(e.target.value)}
              />
              {query
                ? <button onClick={() => setQuery('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 hover:opacity-70"
                    style={{ color: '#424754' }}>
                    <X className="w-3.5 h-3.5" />
                  </button>
                : <kbd className="absolute right-2.5 top-1/2 -translate-y-1/2 text-label-sm px-1 py-0.5 rounded pointer-events-none"
                    style={{ background: 'rgba(66,71,84,0.4)', color: '#424754', fontSize: 10 }}>
                    /
                  </kbd>
              }
            </div>
          </div>

          {/* Kategoriler */}
          <nav className="flex-1 overflow-y-auto px-2 pb-2">
            <p className="px-2 pt-1 pb-1.5 text-label-sm font-medium uppercase tracking-wider"
              style={{ color: '#424754' }}>
              Kategoriler
            </p>
            {CATEGORIES.map(({ id, label, icon: Icon, color }) => {
              const count    = id === 'Tümü' ? responses.length : (catCounts[id] || 0)
              const isActive = activeCat === id
              if (count === 0 && id !== 'Tümü') return null
              return (
                <button
                  key={id}
                  onClick={() => { setActiveCat(id); setQuery('') }}
                  className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-btn text-left mb-0.5 transition-all"
                  style={isActive
                    ? { background: `${color}15`, color }
                    : { color: '#8d9099' }}
                >
                  <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                  <span className="flex-1 text-body-sm font-medium">{label}</span>
                  <span className="text-label-sm px-1.5 py-0.5 rounded tabular-nums"
                    style={isActive
                      ? { background: `${color}22`, color }
                      : { background: 'rgba(66,71,84,0.35)', color: '#424754' }}>
                    {count}
                  </span>
                </button>
              )
            })}
          </nav>

          {/* Alt butonlar */}
          <div className="px-3 py-3 flex-shrink-0 flex flex-col gap-2"
            style={{ borderTop: '1px solid rgba(66,71,84,0.35)' }}>
            <button
              onClick={() => setModal({ mode: 'add' })}
              className="btn-primary w-full flex items-center justify-center gap-2 text-body-sm"
            >
              <Plus className="w-4 h-4" />
              Yeni Yanıt
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

        {/* ═══ İÇERİK ALANI ═══════════════════════════════════════════════ */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

          {/* Üst bar */}
          <div className="px-6 pt-5 pb-3 flex-shrink-0 flex items-center justify-between"
            style={{ borderBottom: '1px solid rgba(66,71,84,0.2)' }}>
            <div className="flex items-center gap-2.5">
              {activeCat !== 'Tümü' && (() => {
                const m = CAT_META[activeCat]
                const Icon = m?.icon
                return Icon ? <Icon className="w-4 h-4" style={{ color: m.color }} /> : null
              })()}
              <h2 className="text-headline-md font-semibold" style={{ color: '#e3e5ef' }}>
                {query
                  ? `"${query}" için sonuçlar`
                  : activeCat === 'Tümü' ? 'Tüm Yanıtlar' : activeCat}
              </h2>
              <span className="text-label-sm px-2 py-0.5 rounded tabular-nums"
                style={{ background: 'rgba(66,71,84,0.4)', color: '#8d9099' }}>
                {filtered.length}
              </span>
            </div>

            <div className="flex items-center gap-2">
              {/* Arama var + temizle */}
              {query && (
                <button onClick={() => setQuery('')}
                  className="btn-ghost flex items-center gap-1.5 text-label-sm">
                  <X className="w-3.5 h-3.5" /> Temizle
                </button>
              )}
              {/* Hızlı ekle */}
              <button onClick={() => setModal({ mode: 'add' })}
                className="btn-ghost flex items-center gap-1.5 text-body-sm">
                <Plus className="w-4 h-4" />
                Yeni
              </button>
            </div>
          </div>

          {/* Klavye ipucu — sadece boştayken */}
          {!query && filtered.length > 0 && (
            <div className="px-6 py-1.5 flex-shrink-0 flex items-center gap-3"
              style={{ borderBottom: '1px solid rgba(66,71,84,0.1)' }}>
              <span className="flex items-center gap-1 text-label-sm" style={{ color: '#2c2e34' }}>
                <kbd className="px-1.5 py-0.5 rounded text-label-sm"
                  style={{ background: 'rgba(66,71,84,0.3)', color: '#424754' }}>/</kbd>
                Ara
              </span>
              <span className="flex items-center gap-1 text-label-sm" style={{ color: '#2c2e34' }}>
                <Copy className="w-3 h-3" style={{ color: '#2c2e34' }} />
                Karta tıkla → kopyala
              </span>
            </div>
          )}

          {/* Kart listesi */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {filtered.length === 0 ? (
              <EmptyState query={query} onClear={() => setQuery('')} />
            ) : grouped ? (
              // ── Kategorilere göre gruplandırılmış ──
              <GroupedContent
                grouped={grouped}
                cardProps={cardProps}
              />
            ) : (
              // ── Düz liste (kategori seçili veya arama var) ──
              <div className="flex flex-col gap-2">
                {filtered.map(r => (
                  <ResponseCard
                    key={r.id}
                    {...cardProps(r)}
                    showCategory={activeCat === 'Tümü' || !!query}
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

// ─── Gruplandırılmış içerik ───────────────────────────────────────────────────

function GroupedContent({ grouped, cardProps }) {
  const { pinned, byCat } = grouped

  return (
    <div className="flex flex-col gap-6">
      {/* Sabitlenmiş */}
      {pinned.length > 0 && (
        <section>
          <SectionHeader icon={Star} label="Sabitlenmiş" count={pinned.length} color="#f5d37a" />
          <div className="flex flex-col gap-2">
            {pinned.map(r => (
              <ResponseCard key={r.id} {...cardProps(r)} showCategory />
            ))}
          </div>
        </section>
      )}

      {/* Kategoriler */}
      {Object.entries(byCat).map(([catId, items]) => {
        const meta = CAT_META[catId]
        if (!meta) return null
        return (
          <section key={catId}>
            <SectionHeader icon={meta.icon} label={catId} count={items.length} color={meta.color} />
            <div className="flex flex-col gap-2">
              {items.map(r => <ResponseCard key={r.id} {...cardProps(r)} />)}
            </div>
          </section>
        )
      })}
    </div>
  )
}

function SectionHeader({ icon: Icon, label, count, color }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="w-3.5 h-3.5" style={{ color, ...(label === 'Sabitlenmiş' ? { fill: color } : {}) }} />
      <span className="text-label-sm font-semibold uppercase tracking-wider" style={{ color }}>
        {label}
      </span>
      <span className="text-label-sm tabular-nums" style={{ color: `${color}80` }}>({count})</span>
      <div className="flex-1 h-px ml-1" style={{ background: `${color}20` }} />
    </div>
  )
}

// ─── Kart bileşeni ────────────────────────────────────────────────────────────

function ResponseCard({
  r, isCopied, isPinned, isExpanded, useCount, showCategory, query,
  onCopy, onPin, onEdit, onDelete, onToggleExpand,
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const color   = CAT_META[r.category]?.color ?? '#8d9099'
  const isLong  = r.content.length > 220
  const preview = r.content.slice(0, 300)

  const handleCardClick = () => {
    if (confirmDelete) return
    onCopy()
  }

  return (
    <article
      onClick={handleCardClick}
      className="group relative rounded-card overflow-hidden transition-all cursor-pointer select-none"
      style={{
        background:   isCopied ? `${color}08` : '#1a1c20',
        border:       `1px solid ${isCopied ? color + '45' : 'rgba(66,71,84,0.22)'}`,
        borderLeft:   `3px solid ${isCopied ? color : color + '60'}`,
        boxShadow:    isCopied ? `0 0 0 1px ${color}20` : 'none',
      }}
      onMouseEnter={e => { if (!isCopied && !confirmDelete) e.currentTarget.style.borderLeftColor = color }}
      onMouseLeave={e => { if (!isCopied) e.currentTarget.style.borderLeftColor = color + '60' }}
    >
      <div className="px-4 py-3">
        {/* ── Başlık satırı ── */}
        <div className="flex items-start justify-between gap-2 mb-1.5">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            {isPinned && <Star className="w-3 h-3 flex-shrink-0" style={{ color: '#f5d37a', fill: '#f5d37a' }} />}
            <h3 className="text-body-sm font-semibold leading-snug" style={{ color: '#e3e5ef' }}>
              <Highlight text={r.title} query={query} />
            </h3>
          </div>

          {/* Eylem butonları — hover'da görünür */}
          {!confirmDelete && (
            <div
              className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
              onClick={e => e.stopPropagation()}
            >
              <IconBtn onClick={onPin} title={isPinned ? 'Sabitlemeyi kaldır' : 'Sabitle'}
                color={isPinned ? '#f5d37a' : '#424754'}>
                <Star className="w-3.5 h-3.5" style={isPinned ? { fill: '#f5d37a' } : {}} />
              </IconBtn>
              <IconBtn onClick={onEdit} title="Düzenle" color="#424754">
                <Pencil className="w-3.5 h-3.5" />
              </IconBtn>
              <IconBtn onClick={() => setConfirmDelete(true)} title="Sil" color="#424754">
                <Trash2 className="w-3.5 h-3.5" />
              </IconBtn>
            </div>
          )}
        </div>

        {/* Kategori badge */}
        {showCategory && (
          <span className="inline-block text-label-sm px-2 py-0.5 rounded mb-2"
            style={{ background: `${color}18`, color }}>
            {r.category}
          </span>
        )}

        {/* İçerik önizleme */}
        <div
          className="text-body-sm select-text"
          style={{
            color: '#6b7280',
            lineHeight: '1.6',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
            maxHeight: isExpanded ? 'none' : '4.8em',  // ~3 satır
            overflow: isExpanded ? 'visible' : 'hidden',
          }}
          onClick={e => { if (isExpanded || !isLong) return; e.stopPropagation(); onToggleExpand() }}
        >
          {query
            ? <Highlight text={isExpanded ? r.content : preview} query={query} />
            : (isExpanded ? r.content : preview)
          }
        </div>

        {/* Alt satır */}
        <div className="flex items-center justify-between mt-2">
          <div className="flex items-center gap-2.5">
            {isLong && (
              <button
                onClick={e => { e.stopPropagation(); onToggleExpand() }}
                className="flex items-center gap-1 text-label-sm transition-opacity hover:opacity-80"
                style={{ color: '#424754' }}
              >
                {isExpanded
                  ? <><ChevronUp className="w-3 h-3" />Daralt</>
                  : <><ChevronDown className="w-3 h-3" />Tamamını Gör</>
                }
              </button>
            )}
            {useCount > 0 && (
              <span className="flex items-center gap-1 text-label-sm" style={{ color: '#2c2e34' }}>
                <Hash className="w-3 h-3" />{useCount}
              </span>
            )}
          </div>

          {/* Kopyala göstergesi */}
          {isCopied
            ? <span className="flex items-center gap-1 text-label-sm font-medium animate-fade-in" style={{ color }}>
                <Check className="w-3.5 h-3.5" />Kopyalandı!
              </span>
            : <span className="flex items-center gap-1 text-label-sm opacity-0 group-hover:opacity-40 transition-opacity"
                style={{ color: '#8d9099' }}>
                <Copy className="w-3 h-3" />Kopyala
              </span>
          }
        </div>

        {/* Silme onayı */}
        {confirmDelete && (
          <div
            className="mt-3 flex items-center gap-2 px-3 py-2.5 rounded-btn"
            style={{ background: 'rgba(255,180,171,0.08)', border: '1px solid rgba(255,180,171,0.2)' }}
            onClick={e => e.stopPropagation()}
          >
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#ffb4ab' }} />
            <p className="text-label-sm flex-1" style={{ color: '#ffb4ab' }}>
              Bu yanıtı silmek istediğinizden emin misiniz?
            </p>
            <button
              onClick={() => { onDelete(); setConfirmDelete(false) }}
              className="text-label-sm px-2.5 py-1 rounded font-medium"
              style={{ background: 'rgba(255,180,171,0.2)', color: '#ffb4ab' }}
            >Sil</button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="text-label-sm px-2.5 py-1 rounded font-medium"
              style={{ background: 'rgba(255,255,255,0.05)', color: '#8d9099' }}
            >İptal</button>
          </div>
        )}
      </div>
    </article>
  )
}

// ─── Küçük ikon buton ─────────────────────────────────────────────────────────

function IconBtn({ onClick, title, color, children }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="p-1.5 rounded transition-colors hover:opacity-80"
      style={{ color }}
    >
      {children}
    </button>
  )
}

// ─── Boş durum ────────────────────────────────────────────────────────────────

function EmptyState({ query, onClear }) {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <div className="w-14 h-14 rounded-2xl flex items-center justify-center"
        style={{ background: 'rgba(66,71,84,0.2)' }}>
        <Search className="w-6 h-6 opacity-30" style={{ color: '#8d9099' }} />
      </div>
      <p className="text-body-md font-medium" style={{ color: '#424754' }}>
        {query ? `"${query}" için yanıt bulunamadı` : 'Bu kategoride henüz yanıt yok'}
      </p>
      {query && (
        <button onClick={onClear} className="btn-ghost text-body-sm">
          Aramayı temizle
        </button>
      )}
    </div>
  )
}

// ─── Modal (Ekle / Düzenle) ───────────────────────────────────────────────────

const EMPTY_FORM = { title: '', content: '', category: 'Genel' }

function ResponseModal({ mode, initialData, onSave, onClose }) {
  const isEdit = mode === 'edit'
  const [form,   setForm]   = useState(isEdit
    ? { title: initialData.title, content: initialData.content, category: initialData.category }
    : EMPTY_FORM)
  const [errors, setErrors] = useState({})
  const titleRef = useRef(null)

  useEffect(() => { setTimeout(() => titleRef.current?.focus(), 50) }, [])

  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const validate = () => {
    const e = {}
    if (!form.title.trim())   e.title   = 'Başlık zorunludur.'
    if (!form.content.trim()) e.content = 'İçerik zorunludur.'
    setErrors(e)
    return !Object.keys(e).length
  }

  const handleSubmit = () => { if (validate()) onSave(form) }

  const cats = CATEGORIES.filter(c => c.id !== 'Tümü')

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(3px)' }}
      onMouseDown={e => e.target === e.currentTarget && onClose()}
    >
      <div
        className="w-full max-w-2xl flex flex-col rounded-card"
        style={{
          background: '#1e2025',
          border: '1px solid rgba(66,71,84,0.55)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.65)',
          maxHeight: '90vh',
        }}
      >
        {/* Başlık */}
        <div className="flex items-center justify-between px-6 py-4 flex-shrink-0"
          style={{ borderBottom: '1px solid rgba(66,71,84,0.35)' }}>
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-btn flex items-center justify-center"
              style={{ background: isEdit ? 'rgba(173,198,255,0.12)' : 'rgba(168,213,162,0.12)' }}>
              {isEdit
                ? <Pencil className="w-3.5 h-3.5" style={{ color: '#adc6ff' }} />
                : <Plus   className="w-3.5 h-3.5" style={{ color: '#a8d5a2' }} />}
            </div>
            <h2 className="text-body-md font-semibold" style={{ color: '#e3e5ef' }}>
              {isEdit ? 'Yanıtı Düzenle' : 'Yeni Yanıt Ekle'}
            </h2>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:opacity-70" style={{ color: '#8d9099' }} title="Kapat (Esc)">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Gövde */}
        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-5">

          {/* Başlık alanı */}
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

          {/* Kategori */}
          <div>
            <label className="text-label-sm font-medium mb-2 block" style={{ color: '#8d9099' }}>Kategori</label>
            <div className="flex flex-wrap gap-2">
              {cats.map(c => {
                const isSelected = form.category === c.id
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => setForm(f => ({ ...f, category: c.id }))}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-label-sm font-medium transition-all"
                    style={isSelected
                      ? { background: `${c.color}20`, color: c.color, border: `1px solid ${c.color}50` }
                      : { background: 'rgba(66,71,84,0.25)', color: '#8d9099', border: '1px solid rgba(66,71,84,0.4)' }
                    }
                  >
                    <c.icon className="w-3 h-3" />
                    {c.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* İçerik */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-label-sm font-medium" style={{ color: '#8d9099' }}>
                İçerik <span style={{ color: '#ffb4ab' }}>*</span>
              </label>
              <span className="text-label-sm" style={{ color: '#424754' }}>{form.content.length} karakter</span>
            </div>
            <textarea
              className="input-field w-full font-mono text-body-sm"
              placeholder="Yanıt metnini buraya yazın…"
              value={form.content}
              onChange={e => { setForm(f => ({ ...f, content: e.target.value })); setErrors(v => ({ ...v, content: '' })) }}
              rows={10}
              style={{
                resize: 'vertical', minHeight: '180px',
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

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 flex-shrink-0"
          style={{ borderTop: '1px solid rgba(66,71,84,0.35)' }}>
          <p className="text-label-sm flex items-center gap-1" style={{ color: '#2c2e34' }}>
            <kbd className="px-1.5 py-0.5 rounded text-label-sm"
              style={{ background: 'rgba(66,71,84,0.3)', color: '#424754' }}>Esc</kbd>
            ile kapatın
          </p>
          <div className="flex items-center gap-2">
            <button onClick={onClose} className="btn-ghost">İptal</button>
            <button onClick={handleSubmit} className="btn-primary flex items-center gap-2">
              <Save className="w-4 h-4" />
              {isEdit ? 'Kaydet' : 'Yanıt Ekle'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
