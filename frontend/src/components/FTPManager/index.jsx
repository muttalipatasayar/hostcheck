import { useEffect, useRef, useState } from 'react'
import {
  FolderOpen, Plug, X, RefreshCw, FolderPlus, Upload,
  Star, Loader2, AlertTriangle,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { useTarget } from '../../context/TargetContext'
import { useSavedConnections } from '../../hooks/useSavedConnections'
import { useFtpSession, joinPath, parentPath } from '../../hooks/useFtpSession'
import { useHotkeys } from '../../hooks/useHotkeys'
import RemoteWindowFrame from '../remote/RemoteWindowFrame'
import SavedConnectionsList from '../remote/SavedConnectionsList'
import ConnectionHeader from '../remote/ConnectionHeader'
import Breadcrumb from './Breadcrumb'
import FileTable from './FileTable'
import InlineEditor from './InlineEditor'
import { DropOverlay, UploadQueue } from './UploadDrop'

const EDIT_LIMIT = 1024 * 1024  // backend MAX_INLINE_EDIT_BYTES ile uyumlu

// Küçük eylem diyaloğu (yeni klasör / yeniden adlandır / chmod / silme onayı)
function ActionDialog({ title, label, initial = '', placeholder, confirmLabel, danger, message, onConfirm, onClose }) {
  const [value, setValue] = useState(initial)
  const inputRef = useRef(null)
  useEffect(() => { inputRef.current?.focus(); inputRef.current?.select() }, [])
  useHotkeys({ escape: () => onClose() })

  const confirm = () => onConfirm(value.trim())

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,6,30,0.35)', backdropFilter: 'blur(4px)' }} onClick={onClose}>
      <div className="w-full max-w-sm rounded-xl p-5 animate-slide-up"
        style={{ background: '#ffffff', boxShadow: '0 24px 64px rgba(0,6,30,0.18)' }}
        onClick={e => e.stopPropagation()}>
        <p className="text-body-md font-semibold mb-3" style={{ color: '#1a1d2e' }}>{title}</p>
        {message && (
          <p className="text-body-sm mb-3 flex items-start gap-2" style={{ color: '#6b7388' }}>
            {danger && <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: '#ffb4ab' }} />}
            {message}
          </p>
        )}
        {label != null && (
          <>
            <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>{label}</label>
            <input
              ref={inputRef}
              type="text"
              className="input-field w-full font-mono mb-4"
              value={value}
              placeholder={placeholder}
              onChange={e => setValue(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && confirm()}
            />
          </>
        )}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-2 rounded-btn text-body-sm" style={{ color: '#6b7388' }}>
            İptal
          </button>
          <button
            onClick={confirm}
            className="px-4 py-2 rounded-btn text-body-sm font-medium"
            style={danger
              ? { background: 'rgba(239,68,68,0.1)', color: '#dc2626' }
              : { background: '#3b7eff', color: '#002e6a' }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function FTPManager() {
  const ftp = useFtpSession()
  const [form, setForm] = useState({ host: '', port: '22', username: '', password: '' })
  const [dialog, setDialog] = useState(null)       // { type, entry? }
  const [editorPath, setEditorPath] = useState(null)
  const [uploads, setUploads] = useState([])
  const [dragActive, setDragActive] = useState(false)
  const [bookmarks, setBookmarks] = useState([])
  const [bookmarksOpen, setBookmarksOpen] = useState(false)
  const fileInputRef = useRef(null)
  const dragCounter = useRef(0)

  const saved = useSavedConnections(
    'ftp_saved_connections',
    (a, b) => a.host === b.host && a.port === b.port && a.username === b.username,
  )

  // Paylaşılan hedefi TEK YÖNLÜ tüket: mount'ta host alanına ön-doldur
  const { target } = useTarget()
  useEffect(() => {
    const t = target.trim()
    if (t) setForm(f => f.host ? f : { ...f, host: t })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const bookmarksKey = ftp.session ? `ftp_bookmarks::${ftp.session.server}` : null
  useEffect(() => {
    if (!bookmarksKey) return
    try { setBookmarks(JSON.parse(localStorage.getItem(bookmarksKey) || '[]')) }
    catch { setBookmarks([]) }
  }, [bookmarksKey])

  const persistBookmarks = (list) => {
    setBookmarks(list)
    if (bookmarksKey) localStorage.setItem(bookmarksKey, JSON.stringify(list.slice(0, 20)))
  }

  const connect = async (overrideForm) => {
    const f = overrideForm || form
    if (!f.host?.trim() || !f.username?.trim()) return
    const ok = await ftp.connect(f)
    if (ok) {
      saved.save({ host: f.host.trim(), port: String(f.port || 22), username: f.username.trim() })
    }
  }

  const newConnection = () => {
    ftp.disconnect()
    setForm({ host: '', port: '22', username: '', password: '' })
    setUploads([])
  }

  const opError = (err, fallback) => toast.error(err.response?.data?.detail || fallback)

  // ── Dosya eylemleri ────────────────────────────────────────────────────────
  const doMkdir = async (name) => {
    if (!name) return
    try {
      await ftp.mkdir(joinPath(ftp.cwd, name))
      setDialog(null)
      await ftp.refresh()
    } catch (err) { opError(err, 'Dizin oluşturulamadı') }
  }

  const doRename = async (entry, dst) => {
    if (!dst) return
    const dstPath = dst.startsWith('/') ? dst : joinPath(ftp.cwd, dst)
    try {
      await ftp.rename(joinPath(ftp.cwd, entry.name), dstPath)
      setDialog(null)
      await ftp.refresh()
    } catch (err) { opError(err, 'Yeniden adlandırılamadı') }
  }

  const doChmod = async (entry, mode) => {
    if (!/^[0-7]{3,4}$/.test(mode)) { toast.error('Geçersiz mod — örn. 755 veya 0644'); return }
    try {
      await ftp.chmodPath(joinPath(ftp.cwd, entry.name), mode)
      setDialog(null)
      await ftp.refresh()
    } catch (err) { opError(err, 'İzinler değiştirilemedi') }
  }

  const doDelete = async (entry) => {
    try {
      await ftp.remove(joinPath(ftp.cwd, entry.name), entry.type === 'dir')
      setDialog(null)
      await ftp.refresh()
    } catch (err) { opError(err, 'Silinemedi') }
  }

  const doDownload = async (entry) => {
    try { await ftp.download(joinPath(ftp.cwd, entry.name)) }
    catch (err) { opError(err, 'İndirme bileti alınamadı') }
  }

  // ── Yükleme (çoklu + sürükle-bırak) ───────────────────────────────────────
  const uploadFiles = async (fileList) => {
    const files = [...fileList]
    if (!files.length) return
    const targetDir = ftp.cwd
    const items = files.map((f, i) => ({ id: `${Date.now()}-${i}`, name: f.name, pct: 0, status: 'yükleniyor' }))
    setUploads(prev => [...prev, ...items])
    for (let i = 0; i < files.length; i++) {
      const id = items[i].id
      try {
        await ftp.upload(files[i], targetDir, (pct) =>
          setUploads(prev => prev.map(u => u.id === id ? { ...u, pct } : u)))
        setUploads(prev => prev.map(u => u.id === id ? { ...u, pct: 100, status: 'tamam' } : u))
      } catch (err) {
        setUploads(prev => prev.map(u => u.id === id
          ? { ...u, status: 'hata', error: err.response?.data?.detail || 'Yükleme başarısız' } : u))
      }
    }
    await ftp.refresh()
  }

  const onDrop = (e) => {
    e.preventDefault()
    dragCounter.current = 0
    setDragActive(false)
    if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files)
  }

  const isBookmarked = bookmarks.includes(ftp.cwd)
  const toggleBookmark = () => {
    persistBookmarks(isBookmarked ? bookmarks.filter(b => b !== ftp.cwd) : [...bookmarks, ftp.cwd])
  }

  const connected = !!ftp.session

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <ConnectionHeader
        icon={<FolderOpen className="w-4 h-4" style={{ color: '#f5c04a' }} />}
        iconBg="linear-gradient(135deg, rgba(245,192,74,0.2) 0%, rgba(245,158,11,0.12) 100%)"
        title="FTP Dosyaları"
        subtitle={connected
          ? `${ftp.session.server} — SFTP oturumu aktif`
          : 'Sunucu dosyalarını tarayıcıdan yönetin — SFTP (FTP/FTPS sonraki sürümde)'}
        showNewConnection={connected}
        onNewConnection={newConnection}
      />

      {/* ── Bağlantı formu ─────────────────────────────────────────────────── */}
      {!connected && (
        <div className="px-8 pb-5 flex-shrink-0 overflow-y-auto">
          <div className="rounded-card p-5" style={{ background: '#ffffff' }}>
            <div className="flex items-center justify-between mb-4">
              <p className="text-label-sm font-medium" style={{ color: '#6b7388' }}>
                BAĞLANTI BİLGİLERİ
              </p>
              <span className="text-label-sm px-2 py-0.5 rounded font-mono"
                style={{ background: 'rgba(59,127,255,0.08)', color: '#3b7eff' }}>
                SFTP
              </span>
            </div>

            <div className="grid grid-cols-3 gap-3 mb-3">
              <div className="col-span-2">
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>
                  Sunucu (Host / IP)
                </label>
                <input type="text" className="input-field w-full"
                  placeholder="192.168.1.1 veya sunucu.com"
                  value={form.host}
                  onChange={e => setForm(f => ({ ...f, host: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && connect()} />
              </div>
              <div>
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>Port</label>
                <input type="number" className="input-field w-full" placeholder="22"
                  value={form.port}
                  onChange={e => setForm(f => ({ ...f, port: e.target.value }))}
                  min="1" max="65535" />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <div>
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>Kullanıcı Adı</label>
                <input type="text" className="input-field w-full" placeholder="root"
                  value={form.username}
                  onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && connect()}
                  autoComplete="username" />
              </div>
              <div>
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>Şifre</label>
                <input type="password" className="input-field w-full" placeholder="••••••••"
                  value={form.password}
                  onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && connect()}
                  autoComplete="current-password" />
              </div>
            </div>

            {ftp.error && (
              <div className="rounded-btn px-4 py-2.5 mb-4 text-body-sm flex items-start gap-2"
                style={{ background: 'rgba(255,180,171,0.08)', color: '#ffb4ab', border: '1px solid rgba(255,180,171,0.2)' }}>
                <X className="w-4 h-4 mt-0.5 flex-shrink-0" />
                {ftp.error}
              </div>
            )}

            <button
              onClick={() => connect()}
              disabled={ftp.connecting || !form.host || !form.username}
              className="btn-primary flex items-center gap-2"
            >
              {ftp.connecting
                ? <><Loader2 className="w-4 h-4 animate-spin" /> Bağlanıyor…</>
                : <><Plug className="w-4 h-4" /> Bağlan</>}
            </button>
          </div>

          <SavedConnectionsList
            items={saved.items}
            icon={<FolderOpen className="w-3.5 h-3.5" style={{ color: '#f5c04a' }} />}
            iconBg="rgba(245,192,74,0.1)"
            subtitle={(c) => `SFTP · port ${c.port}`}
            onSelect={(c) => setForm({ ...c, password: '' })}
            onRemove={saved.remove}
          />
        </div>
      )}

      {/* ── Dosya yöneticisi penceresi ─────────────────────────────────────── */}
      <RemoteWindowFrame
        tabIcon={<FolderOpen className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#f5c04a' }} />}
        tabLabel={connected ? ftp.session.server : 'sftp'}
        isFullscreen={false}
        isConnected={connected}
        isConnecting={ftp.connecting}
        onToggleFullscreen={() => {}}
        onDisconnect={newConnection}
      >
        {!connected ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3" style={{ background: '#0d0f13' }}>
            <FolderOpen className="w-16 h-16" style={{ color: '#f2f4fa' }} />
            <p className="text-body-md" style={{ color: '#9da5be' }}>SFTP bağlantısı bekleniyor</p>
          </div>
        ) : (
          <div
            className="flex-1 min-h-0 flex flex-col relative"
            onDragEnter={(e) => { e.preventDefault(); dragCounter.current += 1; setDragActive(true) }}
            onDragOver={(e) => e.preventDefault()}
            onDragLeave={(e) => {
              e.preventDefault()
              dragCounter.current -= 1
              if (dragCounter.current <= 0) { dragCounter.current = 0; setDragActive(false) }
            }}
            onDrop={onDrop}
          >
            {/* Araç çubuğu */}
            <div className="flex items-center gap-2 px-4 py-2 flex-shrink-0"
              style={{ background: '#ffffff', borderBottom: '1px solid rgba(0,6,30,0.08)' }}>
              <Breadcrumb path={ftp.cwd} onNavigate={(p) => ftp.list(p).catch(() => {})} />
              <div className="flex-1" />
              <ToolbarBtn title="Yenile" onClick={() => ftp.refresh().catch(() => {})}>
                <RefreshCw className="w-3.5 h-3.5" />
              </ToolbarBtn>
              <ToolbarBtn title="Yeni klasör" onClick={() => setDialog({ type: 'mkdir' })}>
                <FolderPlus className="w-3.5 h-3.5" />
              </ToolbarBtn>
              <ToolbarBtn title="Dosya yükle" onClick={() => fileInputRef.current?.click()}>
                <Upload className="w-3.5 h-3.5" />
              </ToolbarBtn>
              <div className="relative">
                <ToolbarBtn
                  title={isBookmarked ? 'Yer imini kaldır' : 'Bu dizini yer imlerine ekle'}
                  onClick={toggleBookmark}
                  onContextMenu={(e) => { e.preventDefault(); setBookmarksOpen(v => !v) }}
                >
                  <Star className="w-3.5 h-3.5" style={isBookmarked ? { fill: '#f5c04a', color: '#f5c04a' } : {}} />
                </ToolbarBtn>
              </div>
              {bookmarks.length > 0 && (
                <select
                  className="text-label-sm rounded-btn px-2 py-1 outline-none font-mono"
                  style={{ background: '#f0f2f7', color: '#6b7388', border: '1px solid rgba(0,6,30,0.08)', maxWidth: 180 }}
                  value=""
                  onChange={(e) => { if (e.target.value) ftp.list(e.target.value).catch(() => {}) }}
                  title="Yer imleri"
                >
                  <option value="">Yer imleri…</option>
                  {bookmarks.map(b => <option key={b} value={b}>{b}</option>)}
                </select>
              )}
              <input
                ref={fileInputRef}
                type="file"
                multiple
                className="hidden"
                onChange={(e) => { uploadFiles(e.target.files); e.target.value = '' }}
              />
            </div>

            {/* Hata bandı */}
            {ftp.error && connected && (
              <div className="px-4 py-2 text-body-sm flex-shrink-0 flex items-center gap-2"
                style={{ background: 'rgba(255,180,171,0.08)', color: '#c14953' }}>
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                {ftp.error}
              </div>
            )}

            <FileTable
              entries={ftp.entries}
              cwd={ftp.cwd}
              loading={ftp.loading}
              features={ftp.session.features}
              editableLimit={EDIT_LIMIT}
              onOpenDir={(name) => ftp.list(joinPath(ftp.cwd, name)).catch(() => {})}
              onGoUp={() => ftp.list(parentPath(ftp.cwd)).catch(() => {})}
              onDownload={doDownload}
              onEdit={(e) => setEditorPath(joinPath(ftp.cwd, e.name))}
              onRename={(e) => setDialog({ type: 'rename', entry: e })}
              onChmod={(e) => setDialog({ type: 'chmod', entry: e })}
              onDelete={(e) => setDialog({ type: 'delete', entry: e })}
            />

            <UploadQueue uploads={uploads} onClear={() => setUploads([])} />

            {/* Durum çubuğu */}
            <div className="flex items-center gap-3 px-4 py-1.5 flex-shrink-0"
              style={{ background: '#f8f9fc', borderTop: '1px solid rgba(0,6,30,0.06)' }}>
              <span className="text-label-sm" style={{ color: '#9da5be' }}>
                {ftp.entries.length} öğe
              </span>
              {ftp.truncated && (
                <span className="text-label-sm flex items-center gap-1" style={{ color: '#ffb786' }}>
                  <AlertTriangle className="w-3 h-3" />
                  Liste kırpıldı — dizinde daha fazla girdi var
                </span>
              )}
              <div className="flex-1" />
              <span className="text-label-sm font-mono" style={{ color: '#9da5be' }}>
                SFTP · {ftp.session.features.join(' · ') || 'temel'}
              </span>
            </div>

            <DropOverlay active={dragActive} />
          </div>
        )}
      </RemoteWindowFrame>

      {/* ── Diyaloglar ─────────────────────────────────────────────────────── */}
      {dialog?.type === 'mkdir' && (
        <ActionDialog
          title="Yeni Klasör"
          label={`${ftp.cwd} içinde oluşturulacak klasör adı`}
          placeholder="yeni-klasor"
          confirmLabel="Oluştur"
          onConfirm={doMkdir}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.type === 'rename' && (
        <ActionDialog
          title="Yeniden Adlandır / Taşı"
          label="Yeni ad (veya / ile başlayan hedef yol)"
          initial={dialog.entry.name}
          confirmLabel="Uygula"
          onConfirm={(v) => doRename(dialog.entry, v)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.type === 'chmod' && (
        <ActionDialog
          title={`İzinler — ${dialog.entry.name}`}
          label="Sekizlik mod"
          initial={dialog.entry.perm_octal || '644'}
          placeholder="755"
          confirmLabel="Uygula"
          onConfirm={(v) => doChmod(dialog.entry, v)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.type === 'delete' && (
        <ActionDialog
          title="Silinsin mi?"
          message={dialog.entry.type === 'dir'
            ? `"${dialog.entry.name}" dizini ve İÇİNDEKİ HER ŞEY kalıcı olarak silinecek.`
            : `"${dialog.entry.name}" kalıcı olarak silinecek.`}
          confirmLabel="Evet, sil"
          danger
          onConfirm={() => doDelete(dialog.entry)}
          onClose={() => setDialog(null)}
        />
      )}

      {editorPath && (
        <InlineEditor path={editorPath} ftp={ftp} onClose={() => setEditorPath(null)} />
      )}
    </div>
  )
}

function ToolbarBtn({ title, onClick, onContextMenu, children }) {
  return (
    <button
      onClick={onClick}
      onContextMenu={onContextMenu}
      title={title}
      className="p-1.5 rounded-btn hover:bg-black/5 flex-shrink-0"
      style={{ color: '#6b7388' }}
    >
      {children}
    </button>
  )
}
