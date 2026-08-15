import { X, Maximize2, Minimize2 } from 'lucide-react'

// SSH/RDP (ileride FTP) araçlarının paylaştığı macOS tarzı pencere çerçevesi:
// trafik ışıkları, sekme etiketi, durum rozeti, tam ekran ve kapat düğmeleri.
// Pencerenin gövdesi `children` ile verilir.
export default function RemoteWindowFrame({
  tabIcon,            // sekme etiketinin solundaki küçük ikon (JSX)
  tabLabel,           // sekme etiketi metni (ör. "root@10.0.0.5:22")
  isFullscreen,
  isConnected,
  isConnecting,
  onToggleFullscreen,
  onDisconnect,
  children,
}) {
  return (
    <div
      className={`min-h-0 flex-1 flex flex-col ${
        isFullscreen ? 'fixed inset-0 z-50 bg-black' : 'px-8 pb-8'
      }`}
    >
      <div
        className="rounded-card overflow-hidden flex flex-col h-full"
        style={{
          background: '#f0f2f7',
          border: '1px solid rgba(66,71,84,0.5)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
        }}
      >
        {/* ── macOS tarzı başlık çubuğu ── */}
        <div
          className="flex items-center gap-3 px-4 py-2.5 flex-shrink-0 select-none"
          style={{ background: '#1e2025', borderBottom: '1px solid rgba(66,71,84,0.5)' }}
        >
          {/* Trafik ışıkları */}
          <div className="flex items-center gap-2">
            <button
              onClick={onDisconnect}
              title="Bağlantıyı kes"
              className="w-3 h-3 rounded-full transition-opacity hover:opacity-75 active:scale-95"
              style={{ background: '#ff5f57' }}
            />
            <div className="w-3 h-3 rounded-full" style={{ background: '#febc2e' }} />
            <div
              className="w-3 h-3 rounded-full cursor-pointer transition-opacity hover:opacity-75"
              onClick={onToggleFullscreen}
              title="Tam ekran"
              style={{ background: '#28c840' }}
            />
          </div>

          {/* Sekme */}
          <div
            className="flex items-center gap-2 px-3 py-1 rounded text-label-sm"
            style={{ background: 'rgba(255,255,255,0.06)', color: '#c9cdd6', maxWidth: '320px' }}
          >
            {tabIcon}
            <span className="truncate">{tabLabel}</span>
          </div>

          <div className="flex-1" />

          {/* Durum + kontroller */}
          <div className="flex items-center gap-3">
            {/* Uzak oturum odaktayken Ctrl+K uzağa gider — paletin kaçış
                kısayolu görünür olmalı, yoksa "palet bozuk" sanılır */}
            <span
              className="hidden sm:flex items-center gap-1 text-label-sm select-none"
              style={{ color: '#6b7388' }}
              title="Uzak oturum odaktayken Ctrl+K uzak makineye gider; komut paleti için Ctrl+Alt+K kullanın"
            >
              Palet:
              <kbd className="px-1 py-0.5 rounded" style={{ background: 'rgba(255,255,255,0.08)', color: '#9da5be', fontSize: 10 }}>
                Ctrl+Alt+K
              </kbd>
            </span>
            {isConnected && (
              <span className="flex items-center gap-1.5 text-label-sm" style={{ color: '#28c840' }}>
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
                Bağlı
              </span>
            )}
            {isConnecting && (
              <span className="flex items-center gap-1.5 text-label-sm" style={{ color: '#febc2e' }}>
                <span className="w-1.5 h-1.5 rounded-full bg-current animate-ping" />
                Bağlanıyor
              </span>
            )}

            <button
              onClick={onToggleFullscreen}
              className="p-1 rounded transition-opacity hover:opacity-70"
              style={{ color: '#6b7388' }}
              title={isFullscreen ? 'Küçült' : 'Tam ekran'}
            >
              {isFullscreen
                ? <Minimize2 className="w-3.5 h-3.5" />
                : <Maximize2 className="w-3.5 h-3.5" />
              }
            </button>

            <button
              onClick={onDisconnect}
              className="p-1 rounded transition-opacity hover:opacity-70"
              style={{ color: '#6b7388' }}
              title="Kapat"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {children}
      </div>
    </div>
  )
}
