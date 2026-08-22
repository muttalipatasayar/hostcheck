import { useState } from 'react'
import { Search, Play, Filter } from 'lucide-react'
import { useTarget } from '../../context/TargetContext'
import { getTool } from '../../lib/tools'

// Kalıcı hedef çubuğu — sabit yükseklikte bir kabuk bölgesi; gizlenmez,
// bağlama göre İÇERİĞİ değişir (gizle/göster layout zıplatır):
// - target:'domain' araçlar → hedef girişi + Çalıştır
// - target:'host' (SSH/RDP) → hedef girişi; bağlantı formuna tek yönlü ön-doldurulur
// - target:'none' (Hazır Yanıtlar) → yerel filtre; sorgu tetiklemez
//
// Görünürlük: ikon, girdi ve düğme TEK bir çerçevenin içindedir. Daha önce
// girdi `bg-transparent` idi ve beyaz çubuğun üstünde gövdesiz duruyordu;
// büyüteç de bir sınırın dışında kaldığı için süs gibi okunuyordu.
const FIELD_MAX = 720

// Odakta alan "yükselir": dolgu beyaza döner, kenarlık mavileşir, halka çıkar.
function fieldStyle(focused) {
  return {
    height: 40,
    maxWidth: FIELD_MAX,
    background: focused ? '#ffffff' : '#f0f2f8',
    border: `1px solid ${focused ? 'rgba(59,127,255,0.45)' : 'rgba(0,6,30,0.10)'}`,
    borderRadius: 10,
    boxShadow: focused ? '0 0 0 3px rgba(59,127,255,0.10)' : 'none',
    transition: 'background 150ms ease, border-color 150ms ease, box-shadow 150ms ease',
  }
}

export default function TargetBar({ view }) {
  const { target, setTarget, commitTarget, filter, setFilter } = useTarget()
  const [focused, setFocused] = useState(false)
  const mode = getTool(view)?.target ?? 'none'

  const focusProps = {
    onFocus: () => setFocused(true),
    onBlur: () => setFocused(false),
  }

  return (
    <div
      className="flex-shrink-0 flex items-center px-8"
      style={{ height: 64, background: '#ffffff', borderBottom: '1px solid rgba(0,6,30,0.09)' }}
    >
      {mode === 'none' ? (
        <div
          className="flex items-center gap-2.5 w-full pl-3.5 pr-2"
          style={fieldStyle(focused)}
        >
          <Filter className="w-4 h-4 flex-shrink-0" style={{ color: '#6b7388' }} />
          <input
            id="target-bar-input"
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Yanıtlarda ara — başlık, içerik veya kategori"
            className="flex-1 min-w-0 bg-transparent outline-none text-body-md"
            style={{ color: '#1a1d2e', caretColor: '#2d6be4' }}
            {...focusProps}
          />
          {filter && (
            <button
              onClick={() => setFilter('')}
              className="flex-shrink-0 px-2 py-1 rounded text-label-sm hover:opacity-70"
              style={{ color: '#6b7388' }}
            >
              Temizle
            </button>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-3 w-full" style={{ maxWidth: FIELD_MAX }}>
          <div
            className="flex items-center gap-2.5 w-full pl-3.5 pr-1.5"
            style={fieldStyle(focused)}
          >
            <Search className="w-4 h-4 flex-shrink-0" style={{ color: '#6b7388' }} />
            <input
              id="target-bar-input"
              type="text"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && target.trim()) commitTarget() }}
              placeholder="example.com veya IP adresi"
              className="flex-1 min-w-0 bg-transparent outline-none text-body-md font-mono"
              style={{ color: '#1a1d2e', caretColor: '#2d6be4' }}
              autoFocus
              {...focusProps}
            />
            {mode === 'domain' && (
              <button
                onClick={commitTarget}
                disabled={!target.trim()}
                className="flex items-center gap-1.5 flex-shrink-0 font-medium text-white transition-all duration-200"
                style={{
                  height: 30,
                  padding: '0 14px',
                  borderRadius: 7,
                  fontSize: '0.8125rem',
                  background: target.trim()
                    ? 'linear-gradient(135deg, #4d8eff 0%, #2563eb 100%)'
                    : 'rgba(0,6,30,0.10)',
                  color: target.trim() ? '#ffffff' : '#9da5be',
                  cursor: target.trim() ? 'pointer' : 'not-allowed',
                }}
              >
                <Play className="w-3 h-3" />
                Çalıştır
              </button>
            )}
          </div>

          {mode === 'host' && (
            <span className="text-label-sm flex-shrink-0 whitespace-nowrap" style={{ color: '#9da5be' }}>
              Bağlantı formuna ön-doldurulur
            </span>
          )}
        </div>
      )}
    </div>
  )
}
