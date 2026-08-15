import { UploadCloud, CheckCircle2, XCircle, Loader2 } from 'lucide-react'

// Sürükle-bırak kaplaması + yükleme ilerleme listesi.
// Sürükleme durumu ve kuyruk state'i üst bileşende yaşar; bu bileşen görsel katman.
export function DropOverlay({ active }) {
  if (!active) return null
  return (
    <div
      className="absolute inset-0 z-20 flex flex-col items-center justify-center pointer-events-none"
      style={{ background: 'rgba(59,127,255,0.10)', border: '2px dashed #3b7eff' }}
    >
      <UploadCloud className="w-12 h-12 mb-2" style={{ color: '#3b7eff' }} />
      <p className="text-title-md font-medium" style={{ color: '#1a1d2e' }}>
        Yüklemek için bırakın
      </p>
      <p className="text-body-sm" style={{ color: '#6b7388' }}>
        Dosyalar bulunduğunuz dizine yüklenir
      </p>
    </div>
  )
}

// uploads: [{ id, name, pct, status: 'yükleniyor'|'tamam'|'hata', error }]
export function UploadQueue({ uploads, onClear }) {
  if (!uploads.length) return null
  const done = uploads.every(u => u.status !== 'yükleniyor')
  return (
    <div
      className="flex-shrink-0 px-4 py-2 flex flex-col gap-1.5"
      style={{ background: '#f8f9fc', borderTop: '1px solid rgba(0,6,30,0.08)', maxHeight: 140, overflowY: 'auto' }}
    >
      {uploads.map(u => (
        <div key={u.id} className="flex items-center gap-2">
          {u.status === 'yükleniyor' && <Loader2 className="w-3.5 h-3.5 animate-spin flex-shrink-0" style={{ color: '#3b7eff' }} />}
          {u.status === 'tamam' && <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#4a6cf7' }} />}
          {u.status === 'hata' && <XCircle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#ffb4ab' }} />}
          <span className="text-label-sm font-mono truncate" style={{ color: '#1a1d2e', width: 220 }}>{u.name}</span>
          <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(0,6,30,0.06)' }}>
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${u.pct}%`,
                background: u.status === 'hata' ? '#ffb4ab' : 'linear-gradient(90deg,#4a6cf7,#3b7eff)',
              }}
            />
          </div>
          <span className="text-label-sm font-mono flex-shrink-0" style={{ color: '#6b7388', width: 40, textAlign: 'right' }}>
            {u.status === 'hata' ? '—' : `%${u.pct}`}
          </span>
          {u.error && <span className="text-label-sm truncate" style={{ color: '#ffb4ab', maxWidth: 200 }}>{u.error}</span>}
        </div>
      ))}
      {done && (
        <button onClick={onClear} className="text-label-sm self-end hover:opacity-70" style={{ color: '#9da5be' }}>
          Listeyi temizle
        </button>
      )}
    </div>
  )
}
