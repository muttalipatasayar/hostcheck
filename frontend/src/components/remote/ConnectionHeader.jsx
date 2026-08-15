import { RotateCcw } from 'lucide-react'

// SSH/RDP sayfa başlığı: araç ikonu, başlık, durum alt metni ve bağlıyken
// görünen "Yeni Bağlantı" düğmesi.
export default function ConnectionHeader({ icon, iconBg, title, subtitle, showNewConnection, onNewConnection }) {
  return (
    <div className="px-8 pt-8 pb-5 flex-shrink-0 flex items-start justify-between">
      <div>
        <div className="flex items-center gap-3 mb-1">
          <div
            className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: iconBg }}
          >
            {icon}
          </div>
          <h1 className="text-headline-md font-semibold" style={{ color: '#1a1d2e' }}>
            {title}
          </h1>
        </div>
        <p className="text-body-md pl-11" style={{ color: '#6b7388' }}>
          {subtitle}
        </p>
      </div>

      {showNewConnection && (
        <button
          onClick={onNewConnection}
          className="flex items-center gap-2 px-3 py-2 rounded-btn text-body-sm font-medium flex-shrink-0"
          style={{
            background: 'rgba(255,180,171,0.1)',
            color: '#ffb4ab',
            border: '1px solid rgba(255,180,171,0.25)',
          }}
        >
          <RotateCcw className="w-3.5 h-3.5" />
          Yeni Bağlantı
        </button>
      )}
    </div>
  )
}
