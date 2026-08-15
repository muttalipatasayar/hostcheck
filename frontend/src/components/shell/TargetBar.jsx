import { Search, Play, Filter } from 'lucide-react'
import { useTarget } from '../../context/TargetContext'
import { getTool } from '../../lib/tools'

// Kalıcı hedef çubuğu — sabit yükseklikte bir kabuk bölgesi; gizlenmez,
// bağlama göre İÇERİĞİ değişir (gizle/göster layout zıplatır):
// - target:'domain' araçlar → hedef girişi + Çalıştır
// - target:'host' (SSH/RDP) → hedef girişi; bağlantı formuna tek yönlü ön-doldurulur
// - target:'none' (Hazır Yanıtlar) → yerel filtre; sorgu tetiklemez
export default function TargetBar({ view }) {
  const { target, setTarget, commitTarget, filter, setFilter } = useTarget()
  const mode = getTool(view)?.target ?? 'none'

  return (
    <div
      className="flex-shrink-0 flex items-center px-8"
      style={{ height: 56, background: '#ffffff', borderBottom: '1px solid rgba(0,6,30,0.09)' }}
    >
      {mode === 'none' ? (
        <div className="flex items-center gap-3 w-full max-w-2xl">
          <Filter className="w-4 h-4 flex-shrink-0" style={{ color: '#6b7388' }} />
          <input
            id="target-bar-input"
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Yanıtlarda ara — başlık, içerik veya kategori"
            className="flex-1 bg-transparent outline-none text-body-md"
            style={{ color: '#1a1d2e', caretColor: '#2d6be4' }}
          />
          {filter && (
            <button
              onClick={() => setFilter('')}
              className="text-label-sm flex-shrink-0 hover:opacity-70"
              style={{ color: '#9da5be' }}
            >
              Temizle
            </button>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-3 w-full max-w-2xl">
          <Search className="w-4 h-4 flex-shrink-0" style={{ color: '#6b7388' }} />
          <input
            id="target-bar-input"
            type="text"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && target.trim()) commitTarget() }}
            placeholder="example.com veya IP adresi"
            className="flex-1 bg-transparent outline-none text-body-md font-mono"
            style={{ color: '#1a1d2e', caretColor: '#2d6be4' }}
            autoFocus
          />
          {mode === 'domain' ? (
            <button
              onClick={commitTarget}
              disabled={!target.trim()}
              className="btn-primary flex items-center gap-2 flex-shrink-0"
            >
              <Play className="w-3.5 h-3.5" />
              Çalıştır
            </button>
          ) : (
            <span className="text-label-sm flex-shrink-0" style={{ color: '#9da5be' }}>
              Bağlantı formuna ön-doldurulur
            </span>
          )}
        </div>
      )}
    </div>
  )
}
