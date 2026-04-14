import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import {
  MessageSquare, Search, Copy, Check, Pencil, Trash2, Plus, Star,
  X, Download, Globe, Server, Shield, Mail, Network, Database,
  Layers, AlertTriangle, Save, Hash, Tag, Eye, Loader2,
} from 'lucide-react'
import axios from 'axios'

// ─── Sabit kategoriler (built-in, API'den gelmiyor) ───────────────────────────

const BUILT_IN_CATS = [
  { id: 'Tümü',       label: 'Tümü',       icon: Layers,        color: '#3b7eff' },
  { id: 'Alan Adı',   label: 'Alan Adı',   icon: Globe,         color: '#3b7eff' },
  { id: 'Hosting',    label: 'Hosting',    icon: Server,        color: '#22c55e' },
  { id: 'SSL',        label: 'SSL',        icon: Shield,        color: '#0ea5e9' },
  { id: 'E-posta',    label: 'E-posta',    icon: Mail,          color: '#f59e0b' },
  { id: 'DNS',        label: 'DNS',        icon: Network,       color: '#a855f7' },
  { id: 'Veritabanı', label: 'Veritabanı', icon: Database,      color: '#ef4444' },
  { id: 'Genel',      label: 'Genel',      icon: MessageSquare, color: '#6b7388' },
]

const CAT_COLORS = [
  '#3b7eff','#22c55e','#f59e0b','#a855f7',
  '#ef4444','#0ea5e9','#ec4899','#14b8a6',
]

const trLower = s => s.toLocaleLowerCase('tr-TR')

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
          ? <mark key={i} style={{ background: 'rgba(245,158,11,0.2)', color: '#d97706', borderRadius: 2, padding: '0 1px' }}>{p}</mark>
          : p
      )}
    </>
  )
}

// ─── Ana bileşen ──────────────────────────────────────────────────────────────

export default function HazirYanitlar() {
  const [responses,   setResponses]   = useState([])
  const [customCats,  setCustomCats]  = useState([])   // { id, name, color }
  const [loading,     setLoading]     = useState(true)
  const [savingId,    setSavingId]    = useState(null)  // şu an API çağrısı yapılan kart id'si

  const [activeCat,  setActiveCat]  = useState('Tümü')
  const [query,      setQuery]      = useState('')
  const [detailId,   setDetailId]   = useState(null)
  const [copiedId,   setCopiedId]   = useState(null)
  const [modal,      setModal]      = useState(null)
  const [addCatMode, setAddCatMode] = useState(false)
  const [newCatName, setNewCatName] = useState('')

  const searchRef = useRef(null)
  const newCatRef = useRef(null)

  // ── API yükle ──────────────────────────────────────────────────────────────

  const loadAll = useCallback(async () => {
    try {
      // Bağımsız istekler — biri hata verse diğeri yüklenmeye devam eder
      const [rRes, kRes] = await Promise.allSettled([
        axios.get('/api/hazir-yanitlar'),
        axios.get('/api/hazir-yanitlar/kategoriler'),
      ])
      if (rRes.status === 'fulfilled') setResponses(rRes.value.data)
      if (kRes.status === 'fulfilled') setCustomCats(kRes.value.data)
    } catch {
      // beklenmedik hata
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  // "/" kısayol tuşu
  useEffect(() => {
    const h = e => {
      if (e.key === '/' && !['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)) {
        e.preventDefault(); searchRef.current?.focus()
      }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  useEffect(() => {
    if (addCatMode) newCatRef.current?.focus()
  }, [addCatMode])

  // ── Türev veriler ──────────────────────────────────────────────────────────

  const allCats = useMemo(() => [
    ...BUILT_IN_CATS,
    ...customCats.map(c => ({ id: c.name, label: c.name, icon: Tag, color: c.color, custom: true, dbId: c.id })),
  ], [customCats])

  const CAT_META = useMemo(() => Object.fromEntries(allCats.map(c => [c.id, c])), [allCats])

  const catCounts = useMemo(() => {
    const m = {}
    responses.forEach(r => { m[r.category] = (m[r.category] || 0) + 1 })
    return m
  }, [responses])

  // Arama varsa kategori filtresi yok — tüm yanıtlarda ara
  const filtered = useMemo(() => {
    const q = trLower(query.trim())
    if (q) {
      return responses.filter(r =>
        trLower(r.title).includes(q) ||
        trLower(r.content).includes(q) ||
        trLower(r.category).includes(q)
      )
    }
    if (activeCat === 'Tümü') return [...responses]
    return responses.filter(r => r.category === activeCat)
  }, [responses, activeCat, query])

  const grouped = useMemo(() => {
    if (activeCat !== 'Tümü' || query.trim()) return null
    const pinned = filtered.filter(r => r.is_pinned)
    const byCat = {}
    allCats.filter(c => c.id !== 'Tümü').forEach(c => {
      const items = filtered.filter(r => r.category === c.id && !r.is_pinned)
      if (items.length) byCat[c.id] = items
    })
    return { pinned, byCat }
  }, [filtered, activeCat, query, allCats])

  const pinCount = responses.filter(r => r.is_pinned).length

  // ── Mutators ──────────────────────────────────────────────────────────────

  const handleSave = useCallback(async (form, id = null) => {
    try {
      if (id) {
        const { data } = await axios.put(`/api/hazir-yanitlar/${id}`, form)
        setResponses(prev => prev.map(r => r.id === id ? data : r))
      } else {
        const { data } = await axios.post('/api/hazir-yanitlar', form)
        setResponses(prev => [data, ...prev])
      }
      setModal(null)
    } catch {
      // hata mesajı gösterilebilir
    }
  }, [])

  const handleDelete = useCallback(async id => {
    try {
      await axios.delete(`/api/hazir-yanitlar/${id}`)
      setResponses(prev => prev.filter(r => r.id !== id))
      if (detailId === id) setDetailId(null)
    } catch {}
  }, [detailId])

  const handleCopy = useCallback(r => {
    navigator.clipboard.writeText(r.content).then(async () => {
      setCopiedId(r.id)
      setTimeout(() => setCopiedId(null), 1800)
      // Kullanım sayacını artır (sessizce, UI'ı bloklama)
      try {
        const { data } = await axios.post(`/api/hazir-yanitlar/${r.id}/use`)
        setResponses(prev => prev.map(x => x.id === r.id ? data : x))
      } catch {}
    })
  }, [])

  const handlePin = useCallback(async id => {
    setSavingId(id)
    try {
      const { data } = await axios.patch(`/api/hazir-yanitlar/${id}/pin`)
      setResponses(prev => prev.map(r => r.id === id ? data : r))
    } catch {} finally {
      setSavingId(null)
    }
  }, [])

  const handleExport = useCallback(() => {
    const text = responses.map(r => `=== ${r.title} ===\n${r.content}`).join('\n\n')
    const url  = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
    Object.assign(document.createElement('a'), { href: url, download: 'hazir_yanitlar.txt' }).click()
    URL.revokeObjectURL(url)
  }, [responses])

  const handleAddCat = useCallback(async () => {
    const name = newCatName.trim()
    if (!name || allCats.some(c => trLower(c.id) === trLower(name))) return
    const color = CAT_COLORS[customCats.length % CAT_COLORS.length]
    try {
      const { data } = await axios.post('/api/hazir-yanitlar/kategoriler', { name, color })
      setCustomCats(prev => [...prev, data])
      setNewCatName('')
      setAddCatMode(false)
    } catch {}
  }, [newCatName, allCats, customCats])

  const handleDeleteCat = useCallback(async (dbId, catName) => {
    try {
      await axios.delete(`/api/hazir-yanitlar/kategoriler/${dbId}`)
      setCustomCats(prev => prev.filter(c => c.id !== dbId))
      if (activeCat === catName) setActiveCat('Tümü')
    } catch {}
  }, [activeCat])

  const detailResponse = detailId ? responses.find(r => r.id === detailId) : null

  const mkCard = r => ({
    r, catMeta: CAT_META,
    isCopied:  copiedId === r.id,
    isPinned:  r.is_pinned,
    isSaving:  savingId === r.id,
    useCount:  r.use_count,
    query,
    onClick:  () => setDetailId(r.id),
    onCopy:   () => handleCopy(r),
    onPin:    () => handlePin(r.id),
    onEdit:   () => setModal({ mode: 'edit', response: r }),
    onDelete: () => handleDelete(r.id),
  })

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 animate-spin" style={{ color: '#3b7eff' }} />
          <p className="text-body-md" style={{ color: '#6b7388' }}>Yanıtlar yükleniyor…</p>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="flex h-full overflow-hidden">

        {/* ═══ SOL SIDEBAR ════════════════════════════════════════════ */}
        <aside className="flex flex-col w-56 flex-shrink-0 h-full"
          style={{ background: '#ffffff', borderRight: '1px solid rgba(0,6,30,0.08)' }}>

          {/* Başlık */}
          <div className="px-4 pt-5 pb-3 flex-shrink-0">
            <div className="flex items-center gap-2 mb-0.5">
              <div className="w-6 h-6 rounded flex items-center justify-center"
                style={{ background: 'rgba(245,158,11,0.12)' }}>
                <MessageSquare className="w-3.5 h-3.5" style={{ color: '#d97706' }} />
              </div>
              <p className="text-body-sm font-semibold" style={{ color: '#1a1d2e' }}>Hazır Yanıtlar</p>
            </div>
            <p className="text-label-sm pl-8" style={{ color: '#9da5be' }}>
              {responses.length} yanıt{pinCount > 0 ? ` · ${pinCount} sabitlenmiş` : ''}
            </p>
          </div>

          {/* Arama */}
          <div className="px-3 pb-3 flex-shrink-0">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 pointer-events-none"
                style={{ color: '#9da5be' }} />
              <input
                ref={searchRef}
                type="text"
                className="w-full text-body-sm outline-none rounded-btn py-2 pr-8"
                style={{ paddingLeft: '2rem', background: '#f0f2f8', border: '1px solid rgba(0,6,30,0.08)', color: '#1a1d2e' }}
                placeholder="Tümünde ara…"
                value={query}
                onChange={e => setQuery(e.target.value)}
              />
              {query
                ? <button onClick={() => setQuery('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 hover:opacity-70"
                    style={{ color: '#9da5be' }}>
                    <X className="w-3.5 h-3.5" />
                  </button>
                : <kbd className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-label-sm px-1 py-0.5 rounded"
                    style={{ background: 'rgba(0,6,30,0.06)', color: '#9da5be', fontSize: 10 }}>/</kbd>
              }
            </div>
          </div>

          {/* Kategoriler */}
          <nav className="flex-1 overflow-y-auto px-2 pb-2">
            <div className="flex items-center justify-between px-2 pt-1 pb-1.5">
              <p className="text-label-sm font-medium uppercase tracking-wider" style={{ color: '#9da5be' }}>
                Kategoriler
              </p>
              <button
                onClick={() => { setAddCatMode(v => !v); setNewCatName('') }}
                className="w-5 h-5 rounded flex items-center justify-center transition-colors hover:opacity-80"
                style={{ background: addCatMode ? 'rgba(37,99,235,0.1)' : 'rgba(0,6,30,0.06)', color: addCatMode ? '#2563eb' : '#6b7388' }}
                title="Yeni kategori ekle"
              >
                {addCatMode ? <X className="w-3 h-3" /> : <Plus className="w-3 h-3" />}
              </button>
            </div>

            {allCats.map(({ id, label, icon: Icon, color, custom, dbId }) => {
              const count    = id === 'Tümü' ? responses.length : (catCounts[id] || 0)
              const isActive = activeCat === id && !query
              if (count === 0 && id !== 'Tümü' && !custom) return null
              return (
                <div key={id} className="group/catrow flex items-center mb-0.5">
                  <button
                    onClick={() => { setActiveCat(id); setQuery('') }}
                    className="flex-1 flex items-center gap-2.5 px-2.5 py-2 rounded-btn text-left transition-all"
                    style={isActive ? { background: `${color}15`, color } : { color: '#6b7388' }}
                  >
                    <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                    <span className="flex-1 text-body-sm font-medium truncate">{label}</span>
                    <span className="text-label-sm px-1.5 py-0.5 rounded tabular-nums"
                      style={isActive
                        ? { background: `${color}22`, color }
                        : { background: 'rgba(0,6,30,0.06)', color: '#9da5be' }}>
                      {count}
                    </span>
                  </button>
                  {custom && (
                    <button
                      onClick={() => handleDeleteCat(dbId, id)}
                      className="opacity-0 group-hover/catrow:opacity-100 transition-opacity w-5 h-5 flex items-center justify-center rounded hover:opacity-60 ml-0.5 flex-shrink-0"
                      style={{ color: '#9da5be' }}
                      title="Kategoriyi sil"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>
              )
            })}

            {/* Yeni kategori formu */}
            {addCatMode && (
              <div className="mt-1 px-1">
                <div className="flex items-center gap-1.5">
                  <input
                    ref={newCatRef}
                    type="text"
                    className="flex-1 text-body-sm rounded-btn px-2.5 py-1.5 outline-none"
                    style={{ background: '#f0f2f8', border: '1px solid rgba(0,6,30,0.1)', color: '#1a1d2e' }}
                    placeholder="Kategori adı…"
                    value={newCatName}
                    onChange={e => setNewCatName(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleAddCat()
                      if (e.key === 'Escape') { setAddCatMode(false); setNewCatName('') }
                    }}
                    maxLength={30}
                  />
                  <button
                    onClick={handleAddCat}
                    disabled={!newCatName.trim()}
                    className="w-7 h-7 rounded-btn flex items-center justify-center transition-colors disabled:opacity-40"
                    style={{ background: 'rgba(37,99,235,0.1)', color: '#2563eb' }}
                  >
                    <Check className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            )}
          </nav>

          {/* Alt butonlar */}
          <div className="px-3 py-3 flex-shrink-0 flex flex-col gap-2"
            style={{ borderTop: '1px solid rgba(0,6,30,0.08)' }}>
            <button onClick={() => setModal({ mode: 'add' })}
              className="btn-primary w-full flex items-center justify-center gap-2 text-body-sm">
              <Plus className="w-4 h-4" />Yeni Yanıt
            </button>
            <button onClick={handleExport}
              className="btn-ghost w-full flex items-center justify-center gap-2 text-label-sm">
              <Download className="w-3.5 h-3.5" />Dışa Aktar
            </button>
          </div>
        </aside>

        {/* ═══ İÇERİK ALANI ═══════════════════════════════════════════ */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">

          {/* Üst bar */}
          <div className="px-6 pt-5 pb-3 flex-shrink-0 flex items-center justify-between"
            style={{ background: '#ffffff', borderBottom: '1px solid rgba(0,6,30,0.08)' }}>
            <div className="flex items-center gap-2.5">
              {!query && activeCat !== 'Tümü' && (() => {
                const m = CAT_META[activeCat]; const Icon = m?.icon
                return Icon ? <Icon className="w-4 h-4" style={{ color: m.color }} /> : null
              })()}
              <h2 className="text-headline-md font-semibold" style={{ color: '#1a1d2e' }}>
                {query ? `"${query}" sonuçları` : activeCat === 'Tümü' ? 'Tüm Yanıtlar' : activeCat}
              </h2>
              <span className="text-label-sm px-2 py-0.5 rounded tabular-nums"
                style={{ background: 'rgba(0,6,30,0.06)', color: '#6b7388' }}>
                {filtered.length}
              </span>
              {query && (
                <span className="text-label-sm" style={{ color: '#9da5be' }}>tüm kategorilerde</span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {query && (
                <button onClick={() => setQuery('')}
                  className="btn-ghost flex items-center gap-1.5 text-label-sm">
                  <X className="w-3.5 h-3.5" /> Temizle
                </button>
              )}
              <button onClick={() => setModal({ mode: 'add' })}
                className="btn-ghost flex items-center gap-1.5 text-body-sm">
                <Plus className="w-4 h-4" /> Yeni
              </button>
            </div>
          </div>

          {/* Kart listesi */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20">
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
                  style={{ background: 'rgba(0,6,30,0.04)' }}>
                  <Search className="w-6 h-6 opacity-20" style={{ color: '#1a1d2e' }} />
                </div>
                <p className="text-title-md font-medium mb-1" style={{ color: '#1a1d2e' }}>
                  {query ? 'Sonuç bulunamadı' : 'Bu kategoride yanıt yok'}
                </p>
                <p className="text-body-md" style={{ color: '#6b7388' }}>
                  {query ? `"${query}" ile eşleşen yanıt bulunamadı` : 'Yeni Yanıt ile ekleyebilirsiniz'}
                </p>
                {query && (
                  <button onClick={() => setQuery('')} className="mt-4 btn-ghost text-body-sm">
                    Aramayı temizle
                  </button>
                )}
              </div>
            ) : grouped ? (
              <GroupedContent grouped={grouped} catMeta={CAT_META} mkCard={mkCard} />
            ) : (
              <div className="flex flex-col gap-2">
                {filtered.map(r => (
                  <ResponseCard key={r.id}
                    {...mkCard(r)}
                    showCategory={activeCat === 'Tümü' || !!query}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ═══ DETAY MODALİ ════════════════════════════════════════════ */}
      {detailResponse && (
        <DetailModal
          r={detailResponse}
          catMeta={CAT_META}
          isCopied={copiedId === detailResponse.id}
          isPinned={detailResponse.is_pinned}
          useCount={detailResponse.use_count}
          onClose={() => setDetailId(null)}
          onCopy={() => handleCopy(detailResponse)}
          onPin={() => handlePin(detailResponse.id)}
          onEdit={() => { setDetailId(null); setModal({ mode: 'edit', response: detailResponse }) }}
          onDelete={() => handleDelete(detailResponse.id)}
        />
      )}

      {/* ═══ EKLE / DÜZENLE MODALİ ══════════════════════════════════ */}
      {modal && (
        <ResponseModal
          mode={modal.mode}
          initialData={modal.mode === 'edit' ? modal.response : null}
          categories={allCats.filter(c => c.id !== 'Tümü')}
          onSave={form => handleSave(form, modal.mode === 'edit' ? modal.response.id : null)}
          onClose={() => setModal(null)}
        />
      )}
    </>
  )
}

// ─── Gruplandırılmış içerik ───────────────────────────────────────────────────

function GroupedContent({ grouped, catMeta, mkCard }) {
  const { pinned, byCat } = grouped
  return (
    <div className="flex flex-col gap-6">
      {pinned.length > 0 && (
        <section>
          <SectionHeader icon={Star} label="Sabitlenmiş" count={pinned.length} color="#f59e0b" />
          <div className="flex flex-col gap-2">
            {pinned.map(r => <ResponseCard key={r.id} {...mkCard(r)} showCategory />)}
          </div>
        </section>
      )}
      {Object.entries(byCat).map(([catId, items]) => {
        const meta = catMeta[catId]; if (!meta) return null
        return (
          <section key={catId}>
            <SectionHeader icon={meta.icon} label={catId} count={items.length} color={meta.color} />
            <div className="flex flex-col gap-2">
              {items.map(r => <ResponseCard key={r.id} {...mkCard(r)} />)}
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
      <span className="text-label-sm font-semibold uppercase tracking-wider" style={{ color }}>{label}</span>
      <span className="text-label-sm tabular-nums" style={{ color: `${color}99` }}>({count})</span>
      <div className="flex-1 h-px ml-1" style={{ background: `${color}25` }} />
    </div>
  )
}

// ─── Yanıt kartı ─────────────────────────────────────────────────────────────

function ResponseCard({
  r, catMeta, isCopied, isPinned, isSaving, useCount, showCategory, query,
  onClick, onCopy, onPin, onEdit, onDelete,
}) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const color   = catMeta[r.category]?.color ?? '#6b7388'
  const preview = r.content.slice(0, 180)
  const isLong  = r.content.length > 180

  return (
    <article
      onClick={() => { if (!confirmDelete) onClick() }}
      className="group relative rounded-card overflow-hidden transition-all cursor-pointer"
      style={{
        background: '#ffffff',
        border:     `1px solid ${isCopied ? color + '55' : 'rgba(0,6,30,0.08)'}`,
        borderLeft: `3px solid ${isCopied ? color : color + '50'}`,
        boxShadow:  '0 1px 3px rgba(0,6,30,0.05)',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderLeftColor = color
        e.currentTarget.style.boxShadow = '0 3px 10px rgba(0,6,30,0.09)'
        e.currentTarget.style.transform = 'translateY(-1px)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderLeftColor = isCopied ? color : color + '50'
        e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,6,30,0.05)'
        e.currentTarget.style.transform = ''
      }}
    >
      <div className="px-4 py-3">
        <div className="flex items-start justify-between gap-2 mb-1.5">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            {isPinned && <Star className="w-3 h-3 flex-shrink-0" style={{ color: '#f59e0b', fill: '#f59e0b' }} />}
            <h3 className="text-body-sm font-semibold leading-snug" style={{ color: '#1a1d2e' }}>
              <Highlight text={r.title} query={query} />
            </h3>
          </div>
          {!confirmDelete && (
            <div className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
              onClick={e => e.stopPropagation()}>
              <ActionBtn onClick={e => { e.stopPropagation(); onCopy() }} title="Hızlı kopyala" color="#6b7388">
                <Copy className="w-3.5 h-3.5" />
              </ActionBtn>
              <ActionBtn onClick={e => { e.stopPropagation(); onPin() }} title={isPinned ? 'Sabitlemeyi kaldır' : 'Sabitle'}
                color={isPinned ? '#f59e0b' : '#6b7388'}>
                {isSaving
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Star className="w-3.5 h-3.5" style={isPinned ? { fill: '#f59e0b' } : {}} />
                }
              </ActionBtn>
              <ActionBtn onClick={e => { e.stopPropagation(); onEdit() }} title="Düzenle" color="#6b7388">
                <Pencil className="w-3.5 h-3.5" />
              </ActionBtn>
              <ActionBtn onClick={e => { e.stopPropagation(); setConfirmDelete(true) }} title="Sil" color="#6b7388">
                <Trash2 className="w-3.5 h-3.5" />
              </ActionBtn>
            </div>
          )}
        </div>

        {showCategory && (
          <span className="inline-block text-label-sm px-2 py-0.5 rounded mb-2 font-medium"
            style={{ background: `${color}15`, color }}>
            {r.category}
          </span>
        )}

        <p className="text-body-sm" style={{
          color: '#6b7388', lineHeight: '1.6',
          display: '-webkit-box', WebkitLineClamp: 3,
          WebkitBoxOrient: 'vertical', overflow: 'hidden',
        }}>
          <Highlight text={preview + (isLong ? '…' : '')} query={query} />
        </p>

        <div className="flex items-center justify-between mt-2">
          <div className="flex items-center gap-3">
            {useCount > 0 && (
              <span className="flex items-center gap-1 text-label-sm" style={{ color: '#9da5be' }}>
                <Hash className="w-3 h-3" />{useCount}
              </span>
            )}
            <span className="flex items-center gap-1 text-label-sm opacity-0 group-hover:opacity-100 transition-opacity"
              style={{ color: '#9da5be' }}>
              <Eye className="w-3 h-3" />Görüntüle
            </span>
          </div>
          {isCopied && (
            <span className="flex items-center gap-1 text-label-sm font-medium animate-fade-in" style={{ color: '#16a34a' }}>
              <Check className="w-3.5 h-3.5" />Kopyalandı!
            </span>
          )}
        </div>

        {confirmDelete && (
          <div className="mt-3 flex items-center gap-2 px-3 py-2.5 rounded-btn"
            style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.15)' }}
            onClick={e => e.stopPropagation()}>
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#dc2626' }} />
            <p className="text-label-sm flex-1" style={{ color: '#dc2626' }}>Silinsin mi?</p>
            <button onClick={e => { e.stopPropagation(); onDelete() }}
              className="text-label-sm font-semibold px-2 py-1 rounded"
              style={{ background: 'rgba(239,68,68,0.1)', color: '#dc2626' }}>Sil</button>
            <button onClick={e => { e.stopPropagation(); setConfirmDelete(false) }}
              className="text-label-sm px-2 py-1 rounded"
              style={{ color: '#6b7388' }}>İptal</button>
          </div>
        )}
      </div>
    </article>
  )
}

function ActionBtn({ onClick, title, color, children }) {
  return (
    <button onClick={onClick} title={title}
      className="p-1.5 rounded transition-colors hover:opacity-70"
      style={{ color }}>
      {children}
    </button>
  )
}

// ─── Detay modalı ─────────────────────────────────────────────────────────────

function DetailModal({ r, catMeta, isCopied, isPinned, useCount, onClose, onCopy, onPin, onEdit, onDelete }) {
  const color = catMeta[r.category]?.color ?? '#6b7388'
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,6,30,0.4)', backdropFilter: 'blur(6px)' }}
      onClick={onClose}>
      <div
        className="w-full max-w-2xl max-h-[80vh] flex flex-col rounded-xl overflow-hidden animate-slide-up"
        style={{ background: '#ffffff', boxShadow: '0 24px 64px rgba(0,6,30,0.18)', borderTop: `4px solid ${color}` }}
        onClick={e => e.stopPropagation()}
      >
        <div className="px-6 py-5 flex-shrink-0" style={{ borderBottom: '1px solid rgba(0,6,30,0.08)' }}>
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-label-sm px-2 py-0.5 rounded font-medium"
                  style={{ background: `${color}15`, color }}>{r.category}</span>
                {isPinned && (
                  <span className="flex items-center gap-1 text-label-sm" style={{ color: '#f59e0b' }}>
                    <Star className="w-3 h-3" style={{ fill: '#f59e0b' }} />Sabitlenmiş
                  </span>
                )}
                {useCount > 0 && (
                  <span className="flex items-center gap-1 text-label-sm" style={{ color: '#9da5be' }}>
                    <Hash className="w-3 h-3" />{useCount} kez kullanıldı
                  </span>
                )}
              </div>
              <h2 className="text-title-lg font-semibold leading-snug" style={{ color: '#1a1d2e' }}>{r.title}</h2>
            </div>
            <button onClick={onClose} className="p-2 rounded-btn transition-colors flex-shrink-0 hover:opacity-70"
              style={{ color: '#9da5be', background: 'rgba(0,6,30,0.05)' }}>
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          <p className="text-body-md whitespace-pre-wrap leading-relaxed select-text"
            style={{ color: '#3d4257', lineHeight: '1.8' }}>
            {r.content}
          </p>
        </div>

        <div className="px-6 py-4 flex-shrink-0 flex items-center justify-between flex-wrap gap-3"
          style={{ borderTop: '1px solid rgba(0,6,30,0.08)', background: '#f8f9fc' }}>
          <div className="flex items-center gap-2 flex-wrap">
            <button onClick={onPin}
              className="flex items-center gap-1.5 px-3 py-2 rounded-btn text-body-sm transition-colors"
              style={isPinned ? { background: 'rgba(245,158,11,0.1)', color: '#d97706' } : { background: 'rgba(0,6,30,0.05)', color: '#6b7388' }}>
              <Star className="w-3.5 h-3.5" style={isPinned ? { fill: '#d97706' } : {}} />
              {isPinned ? 'Sabitleme kaldır' : 'Sabitle'}
            </button>
            <button onClick={onEdit}
              className="flex items-center gap-1.5 px-3 py-2 rounded-btn text-body-sm transition-colors"
              style={{ background: 'rgba(0,6,30,0.05)', color: '#6b7388' }}>
              <Pencil className="w-3.5 h-3.5" />Düzenle
            </button>
            {!confirmDelete ? (
              <button onClick={() => setConfirmDelete(true)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-btn text-body-sm"
                style={{ background: 'rgba(0,6,30,0.05)', color: '#9da5be' }}>
                <Trash2 className="w-3.5 h-3.5" />Sil
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <button onClick={onDelete}
                  className="flex items-center gap-1.5 px-3 py-2 rounded-btn text-body-sm"
                  style={{ background: 'rgba(239,68,68,0.1)', color: '#dc2626' }}>
                  <AlertTriangle className="w-3.5 h-3.5" />Evet, sil
                </button>
                <button onClick={() => setConfirmDelete(false)} className="px-3 py-2 rounded-btn text-body-sm"
                  style={{ color: '#6b7388' }}>İptal</button>
              </div>
            )}
          </div>
          <button onClick={onCopy}
            className="flex items-center gap-2 px-6 py-2.5 rounded-btn font-semibold text-body-md transition-all"
            style={isCopied
              ? { background: 'rgba(22,163,74,0.1)', color: '#16a34a' }
              : { background: 'linear-gradient(135deg, #4d8eff 0%, #2563eb 100%)', color: '#ffffff', boxShadow: '0 3px 10px rgba(37,99,235,0.3)' }}>
            {isCopied ? <><Check className="w-4 h-4" />Kopyalandı!</> : <><Copy className="w-4 h-4" />Kopyala</>}
          </button>
        </div>
      </div>
    </div>
  )
}

// ─── Ekle / Düzenle modalı ────────────────────────────────────────────────────

function ResponseModal({ mode, initialData, categories, onSave, onClose }) {
  const [title,    setTitle]    = useState(initialData?.title    ?? '')
  const [content,  setContent]  = useState(initialData?.content  ?? '')
  const [category, setCategory] = useState(initialData?.category ?? (categories[0]?.id ?? 'Genel'))
  const [saving,   setSaving]   = useState(false)

  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const canSave = title.trim() && content.trim() && !saving

  const handleSubmit = async () => {
    if (!canSave) return
    setSaving(true)
    await onSave({ title: title.trim(), content: content.trim(), category })
    setSaving(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,6,30,0.4)', backdropFilter: 'blur(6px)' }}
      onClick={onClose}>
      <div className="w-full max-w-lg rounded-xl overflow-hidden animate-slide-up"
        style={{ background: '#ffffff', boxShadow: '0 24px 64px rgba(0,6,30,0.18)' }}
        onClick={e => e.stopPropagation()}>

        <div className="px-6 py-4 flex items-center justify-between"
          style={{ borderBottom: '1px solid rgba(0,6,30,0.08)' }}>
          <h2 className="text-title-md font-semibold" style={{ color: '#1a1d2e' }}>
            {mode === 'add' ? 'Yeni Yanıt Ekle' : 'Yanıtı Düzenle'}
          </h2>
          <button onClick={onClose} className="p-1.5 rounded hover:opacity-70" style={{ color: '#9da5be' }}>
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-6 py-5 flex flex-col gap-4">
          <div>
            <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>Başlık</label>
            <input type="text" value={title} onChange={e => setTitle(e.target.value)}
              className="input-field" placeholder="Yanıt başlığı…" maxLength={120} />
          </div>
          <div>
            <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>Kategori</label>
            <select value={category} onChange={e => setCategory(e.target.value)}
              className="input-field" style={{ cursor: 'pointer' }}>
              {categories.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-label-sm font-medium block mb-1.5" style={{ color: '#6b7388' }}>İçerik</label>
            <textarea value={content} onChange={e => setContent(e.target.value)}
              className="textarea-field" placeholder="Hazır yanıt metni…" style={{ minHeight: 140 }} />
          </div>
        </div>

        <div className="px-6 py-4 flex items-center justify-end gap-3"
          style={{ borderTop: '1px solid rgba(0,6,30,0.08)', background: '#f8f9fc' }}>
          <button onClick={onClose} className="btn-ghost">İptal</button>
          <button onClick={handleSubmit} disabled={!canSave} className="btn-primary flex items-center gap-2">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {mode === 'add' ? 'Ekle' : 'Kaydet'}
          </button>
        </div>
      </div>
    </div>
  )
}
