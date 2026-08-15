import { Home, ChevronRight } from 'lucide-react'

// Tıklanabilir yol gezinmesi: / kökünden itibaren her parça bir bağlantı.
export default function Breadcrumb({ path, onNavigate }) {
  const parts = path.split('/').filter(Boolean)

  return (
    <div className="flex items-center gap-1 min-w-0 overflow-x-auto" style={{ scrollbarWidth: 'none' }}>
      <button
        onClick={() => onNavigate('/')}
        className="p-1 rounded hover:opacity-70 flex-shrink-0"
        style={{ color: '#3b7eff' }}
        title="Kök dizin"
      >
        <Home className="w-3.5 h-3.5" />
      </button>
      {parts.map((part, i) => {
        const target = '/' + parts.slice(0, i + 1).join('/')
        const last = i === parts.length - 1
        return (
          <span key={target} className="flex items-center gap-1 flex-shrink-0">
            <ChevronRight className="w-3 h-3" style={{ color: '#9da5be' }} />
            <button
              onClick={() => !last && onNavigate(target)}
              className={`text-body-sm font-mono px-1 rounded ${last ? '' : 'hover:opacity-70'}`}
              style={{ color: last ? '#1a1d2e' : '#3b7eff', cursor: last ? 'default' : 'pointer' }}
            >
              {part}
            </button>
          </span>
        )
      })}
    </div>
  )
}
