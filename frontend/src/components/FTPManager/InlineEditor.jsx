import { useEffect, useState } from 'react'
import { Save, X, Loader2, FileEdit } from 'lucide-react'
import toast from 'react-hot-toast'
import { useHotkeys } from '../../hooks/useHotkeys'
import { apiHataMesaji } from '../../lib/apiHata'

// Satır içi metin düzenleyici — bilinçli olarak sade bir <textarea>
// (CodeMirror yok); 1 MB üstü dosyalar backend'de 413 ile reddedilir.
export default function InlineEditor({ path, ftp, onClose }) {
  const [content, setContent] = useState('')
  const [original, setOriginal] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState('')

  const dirty = content !== original

  useEffect(() => {
    ftp.readFile(path)
      .then(res => { setContent(res.data.content); setOriginal(res.data.content) })
      .catch(err => setLoadError(apiHataMesaji(err, 'Dosya okunamadı')))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path])

  const save = async () => {
    setSaving(true)
    try {
      await ftp.writeFile(path, content)
      setOriginal(content)
      toast.success('Kaydedildi')
    } catch (err) {
      toast.error(apiHataMesaji(err, 'Kaydedilemedi'))
    } finally {
      setSaving(false)
    }
  }

  const close = () => {
    if (dirty && !window.confirm('Kaydedilmemiş değişiklikler var — yine de kapatılsın mı?')) return
    onClose()
  }

  // Scope stack: Escape yalnızca bu modalı kapatır; Ctrl+S kaydeder
  useHotkeys({
    'escape': () => close(),
    'ctrl+s': () => { if (dirty && !saving) save() },
  })

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,6,30,0.4)', backdropFilter: 'blur(6px)' }}
      onClick={close}
    >
      <div
        className="w-full max-w-3xl h-[80vh] flex flex-col rounded-xl overflow-hidden animate-slide-up"
        style={{ background: '#ffffff', boxShadow: '0 24px 64px rgba(0,6,30,0.18)' }}
        onClick={e => e.stopPropagation()}
      >
        <div className="px-5 py-3 flex items-center gap-3 flex-shrink-0"
          style={{ borderBottom: '1px solid rgba(0,6,30,0.08)' }}>
          <FileEdit className="w-4 h-4 flex-shrink-0" style={{ color: '#3b7eff' }} />
          <span className="text-body-sm font-mono flex-1 truncate" style={{ color: '#1a1d2e' }}>
            {path}{dirty ? ' •' : ''}
          </span>
          <button
            onClick={save}
            disabled={!dirty || saving || loading || !!loadError}
            className="btn-primary flex items-center gap-2 text-body-sm py-1.5"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            Kaydet
          </button>
          <button onClick={close} className="p-1.5 rounded hover:opacity-70" style={{ color: '#9da5be' }}>
            <X className="w-4 h-4" />
          </button>
        </div>

        {loading && (
          <div className="flex-1 flex items-center justify-center" style={{ color: '#9da5be' }}>
            <Loader2 className="w-5 h-5 animate-spin mr-2" /> Yükleniyor…
          </div>
        )}
        {loadError && (
          <div className="flex-1 flex items-center justify-center px-6 text-center text-body-sm" style={{ color: '#ffb4ab' }}>
            {loadError}
          </div>
        )}
        {!loading && !loadError && (
          <textarea
            value={content}
            onChange={e => setContent(e.target.value)}
            spellCheck={false}
            className="flex-1 w-full outline-none resize-none px-5 py-4 font-mono text-body-sm"
            style={{ color: '#1a1d2e', background: '#fbfcfe', lineHeight: 1.6, tabSize: 4 }}
          />
        )}
      </div>
    </div>
  )
}
