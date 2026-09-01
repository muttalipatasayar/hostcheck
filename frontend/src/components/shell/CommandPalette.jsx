import { useEffect, useMemo, useRef, useState } from 'react'
import { Command, CornerDownLeft } from 'lucide-react'
import { COMMANDS } from '../../lib/commands'
import { fuzzyScore } from '../../lib/fuzzy'
import { useHotkeys } from '../../hooks/useHotkeys'
import { useAuth } from '../../context/AuthContext'
import { aracErisilebilir } from '../../lib/tools'

// Ctrl+K komut paleti. Açıkken hotkey yığınının tepesindedir: Escape ve ok
// tuşları yalnızca paleti yönetir, alttaki scope'lara düşmez.
export default function CommandPalette({ onRun, onClose }) {
  const { girisli, admin } = useAuth()
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef(null)
  const listRef = useRef(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  // Yetkisiz araçların komutları listelenmez. Filtre BURADA, `lib/commands.js`'te
  // değil: `COMMANDS` modül seviyesinde sabit bir dizi ve oturum durumunu göremez.
  const izinliKomutlar = useMemo(
    () => COMMANDS.filter(cmd => aracErisilebilir(cmd.view, { girisli, admin })),
    [girisli, admin])

  const matches = useMemo(() => {
    const q = query.trim()
    if (!q) return izinliKomutlar.slice(0, 12)
    return izinliKomutlar
      .map(cmd => ({ cmd, score: Math.max(fuzzyScore(q, cmd.label), fuzzyScore(q, cmd.hint || '') - 5) }))
      .filter(x => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 12)
      .map(x => x.cmd)
  }, [query, izinliKomutlar])

  // İmleci liste değişince sınırla
  useEffect(() => { setCursor(c => Math.min(c, Math.max(matches.length - 1, 0))) }, [matches])

  // Seçili öğe görünür kalsın
  useEffect(() => {
    listRef.current?.children[cursor]?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  const run = (cmd) => {
    if (!cmd) return
    onRun(cmd)
    onClose()
  }

  useHotkeys({
    'escape':    () => onClose(),
    'arrowdown': () => setCursor(c => Math.min(c + 1, matches.length - 1)),
    'arrowup':   () => setCursor(c => Math.max(c - 1, 0)),
    'enter':     () => run(matches[cursor]),
  })

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-24"
      style={{ background: 'rgba(0,6,30,0.35)', backdropFilter: 'blur(4px)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl overflow-hidden animate-slide-up"
        style={{ background: '#ffffff', boxShadow: '0 24px 64px rgba(0,6,30,0.25)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Arama girişi */}
        <div className="flex items-center gap-3 px-4 py-3.5" style={{ borderBottom: '1px solid rgba(0,6,30,0.08)' }}>
          <Command className="w-4 h-4 flex-shrink-0" style={{ color: '#3b7eff' }} />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Komut ara — örn. 'a kaydı', 'csr', 'ssh'"
            className="flex-1 bg-transparent outline-none text-body-md"
            style={{ color: '#1a1d2e', caretColor: '#2d6be4' }}
          />
          <kbd className="text-label-sm px-1.5 py-0.5 rounded" style={{ background: 'rgba(0,6,30,0.05)', color: '#9da5be' }}>Esc</kbd>
        </div>

        {/* Sonuçlar */}
        <div ref={listRef} className="max-h-80 overflow-y-auto py-1.5">
          {matches.length === 0 && (
            <p className="px-4 py-6 text-center text-body-sm" style={{ color: '#9da5be' }}>
              Eşleşen komut yok.
            </p>
          )}
          {matches.map((cmd, i) => {
            const Icon = cmd.icon
            const active = i === cursor
            return (
              <button
                key={cmd.id}
                onClick={() => run(cmd)}
                onMouseEnter={() => setCursor(i)}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-left"
                style={{ background: active ? 'rgba(59,127,255,0.08)' : 'transparent' }}
              >
                <Icon className="w-4 h-4 flex-shrink-0" style={{ color: active ? '#3b7eff' : '#9da5be' }} />
                <span className="flex-1 text-body-sm" style={{ color: '#1a1d2e' }}>{cmd.label}</span>
                {cmd.hint && (
                  <span className="text-label-sm flex-shrink-0" style={{ color: '#9da5be' }}>{cmd.hint}</span>
                )}
                {active && <CornerDownLeft className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#9da5be' }} />}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
