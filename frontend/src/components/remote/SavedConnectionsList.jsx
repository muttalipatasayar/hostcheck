import { Clock, X } from 'lucide-react'

// "Son Bağlantılar" listesi — SSH ve RDP'nin ortak görünümü.
// `icon` satır ikonu (JSX), `iconBg` ikon kutusunun arka planı,
// `subtitle(conn)` satırın alt metnini üretir (ör. "port 22").
export default function SavedConnectionsList({ items, icon, iconBg, subtitle, onSelect, onRemove }) {
  if (!items.length) return null

  return (
    <div className="mt-5">
      <p
        className="text-label-sm font-medium uppercase tracking-wider mb-2 flex items-center gap-1.5"
        style={{ color: '#9da5be' }}
      >
        <Clock className="w-3.5 h-3.5" />
        Son Bağlantılar
      </p>
      <div className="flex flex-col gap-1.5">
        {items.map((c, i) => (
          <button
            key={i}
            onClick={() => onSelect(c)}
            className="group flex items-center gap-3 px-4 py-3 rounded-btn text-left w-full transition-colors"
            style={{ background: '#ffffff' }}
          >
            <div
              className="w-7 h-7 rounded flex items-center justify-center flex-shrink-0"
              style={{ background: iconBg }}
            >
              {icon}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-body-sm font-medium truncate" style={{ color: '#1a1d2e' }}>
                {c.username}@{c.host}
              </p>
              <p className="text-label-sm" style={{ color: '#9da5be' }}>{subtitle(c)}</p>
            </div>
            <span
              role="button"
              onClick={(e) => { e.stopPropagation(); onRemove(i) }}
              className="opacity-0 group-hover:opacity-100 p-1 rounded transition-opacity cursor-pointer"
              style={{ color: '#9da5be' }}
              title="Sil"
            >
              <X className="w-3.5 h-3.5" />
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
