import { useState } from 'react'
import {
  Folder, File, Link2, ArrowUp, Download, Pencil, Trash2,
  FileEdit, KeySquare, Loader2,
} from 'lucide-react'

export function humanSize(bytes) {
  if (bytes == null) return ''
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = bytes
  for (const u of units) {
    v /= 1024
    if (v < 1024) return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${u}`
  }
  return `${Math.round(v)} PB`
}

function fmtDate(epoch) {
  if (!epoch) return '—'
  return new Date(epoch * 1000).toLocaleString('tr-TR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

const TYPE_ICON = {
  dir:  { icon: Folder, color: '#f5c04a' },
  file: { icon: File,   color: '#9da5be' },
  link: { icon: Link2,  color: '#7dd5f4' },
}

// Dosya listesi — çift tık: dizine gir / dosyayı düzenle; satır ucunda
// eylem düğmeleri (indir, yeniden adlandır, izinler, sil).
export default function FileTable({
  entries, cwd, loading, features, editableLimit,
  onOpenDir, onGoUp, onDownload, onEdit, onRename, onChmod, onDelete,
}) {
  const [selected, setSelected] = useState(null)

  const handleDoubleClick = (e) => {
    if (e.type === 'dir') onOpenDir(e.name)
    else if (e.type === 'file' && e.size <= editableLimit) onEdit(e)
    else if (e.type === 'file') onDownload(e)
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto" style={{ background: '#ffffff' }}>
      {/* Başlık satırı */}
      <div
        className="flex items-center gap-3 px-4 py-2 sticky top-0 z-10"
        style={{ background: '#f0f2f7', borderBottom: '1px solid rgba(0,6,30,0.08)' }}
      >
        <span className="text-label-sm font-medium flex-1" style={{ color: '#9da5be' }}>Ad</span>
        <span className="text-label-sm font-medium text-right" style={{ color: '#9da5be', width: 80 }}>Boyut</span>
        <span className="text-label-sm font-medium" style={{ color: '#9da5be', width: 130 }}>Değiştirilme</span>
        <span className="text-label-sm font-medium font-mono" style={{ color: '#9da5be', width: 90 }}>İzinler</span>
        <span style={{ width: 132 }} />
      </div>

      {loading && (
        <div className="flex items-center justify-center py-16" style={{ color: '#9da5be' }}>
          <Loader2 className="w-5 h-5 animate-spin mr-2" />
          <span className="text-body-sm">Listeleniyor…</span>
        </div>
      )}

      {!loading && (
        <>
          {/* Üst dizin */}
          {cwd !== '/' && (
            <div
              className="flex items-center gap-3 px-4 py-2 cursor-pointer hover:bg-black/[0.02]"
              style={{ borderBottom: '1px solid rgba(0,6,30,0.04)' }}
              onDoubleClick={onGoUp}
              onClick={onGoUp}
            >
              <ArrowUp className="w-4 h-4 flex-shrink-0" style={{ color: '#9da5be' }} />
              <span className="text-body-sm font-mono" style={{ color: '#6b7388' }}>..</span>
            </div>
          )}

          {entries.length === 0 && (
            <p className="text-body-sm text-center py-16" style={{ color: '#9da5be' }}>
              Bu dizin boş.
            </p>
          )}

          {entries.map((e) => {
            const cfg = TYPE_ICON[e.type] || TYPE_ICON.file
            const Icon = cfg.icon
            const isSel = selected === e.name
            return (
              <div
                key={e.name}
                className="group flex items-center gap-3 px-4 py-1.5 cursor-default select-none"
                style={{
                  borderBottom: '1px solid rgba(0,6,30,0.04)',
                  background: isSel ? 'rgba(59,127,255,0.07)' : undefined,
                }}
                onClick={() => setSelected(e.name)}
                onDoubleClick={() => handleDoubleClick(e)}
              >
                <Icon className="w-4 h-4 flex-shrink-0" style={{ color: cfg.color }} />
                <span
                  className="text-body-sm font-mono flex-1 truncate"
                  style={{ color: '#1a1d2e' }}
                  title={e.name}
                >
                  {e.name}
                </span>
                <span className="text-label-sm font-mono text-right flex-shrink-0" style={{ color: '#6b7388', width: 80 }}>
                  {e.type === 'dir' ? '—' : humanSize(e.size)}
                </span>
                <span className="text-label-sm font-mono flex-shrink-0" style={{ color: '#6b7388', width: 130 }}>
                  {fmtDate(e.mtime)}
                </span>
                <span className="text-label-sm font-mono flex-shrink-0" style={{ color: '#9da5be', width: 90 }} title={e.perms}>
                  {e.perm_octal || '—'}
                </span>

                {/* Satır eylemleri */}
                <span className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" style={{ width: 132 }}>
                  {e.type !== 'dir' && (
                    <RowBtn title="İndir" onClick={() => onDownload(e)}>
                      <Download className="w-3.5 h-3.5" />
                    </RowBtn>
                  )}
                  {e.type === 'file' && e.size <= editableLimit && (
                    <RowBtn title="Düzenle" onClick={() => onEdit(e)}>
                      <FileEdit className="w-3.5 h-3.5" />
                    </RowBtn>
                  )}
                  <RowBtn title="Yeniden adlandır / taşı" onClick={() => onRename(e)}>
                    <Pencil className="w-3.5 h-3.5" />
                  </RowBtn>
                  {features.includes('chmod') && (
                    <RowBtn title="İzinler (chmod)" onClick={() => onChmod(e)}>
                      <KeySquare className="w-3.5 h-3.5" />
                    </RowBtn>
                  )}
                  <RowBtn title="Sil" color="#ffb4ab" onClick={() => onDelete(e)}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </RowBtn>
                </span>
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}

function RowBtn({ title, color = '#6b7388', onClick, children }) {
  return (
    <button
      onClick={(ev) => { ev.stopPropagation(); onClick() }}
      title={title}
      className="p-1 rounded hover:bg-black/5"
      style={{ color }}
    >
      {children}
    </button>
  )
}
