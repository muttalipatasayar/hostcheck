import { useRef, useState } from 'react'
import axios from 'axios'
import { ensureAdminAccess } from '../lib/adminAuth'

// FTP oturumu: session_id yalnızca X-FTP-Session header'ında taşınır (URL'ye
// yazılmaz). İndirme istisnadır: backend'den tek kullanımlık bilet alınır ve
// native Save dialog için <a href> o bileti taşır.

export const joinPath = (dir, name) => (dir === '/' ? `/${name}` : `${dir}/${name}`)

export const parentPath = (p) => {
  if (p === '/' || !p) return '/'
  const cut = p.replace(/\/+$/, '').split('/')
  cut.pop()
  return cut.join('/') || '/'
}

export function useFtpSession() {
  const [session, setSession] = useState(null)  // { session_id, features, server, home }
  const [cwd, setCwd] = useState('/')
  const [entries, setEntries] = useState([])
  const [truncated, setTruncated] = useState(false)
  const [loading, setLoading] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState('')
  const sessionRef = useRef(null)

  const clear = () => {
    sessionRef.current = null
    setSession(null)
    setCwd('/')
    setEntries([])
    setTruncated(false)
  }

  const api = async (cfg) => {
    try {
      return await axios({
        ...cfg,
        headers: { ...(cfg.headers || {}), 'X-FTP-Session': sessionRef.current?.session_id || '' },
      })
    } catch (err) {
      // 410 = oturum süpürülmüş/kapanmış → bağlantı ekranına dön
      if (err.response?.status === 410 && cfg.url !== '/api/ftp/session') {
        clear()
      }
      throw err
    }
  }

  const errMsg = (err, fallback) => err.response?.data?.detail || fallback

  const connect = async (form) => {
    setConnecting(true)
    setError('')
    // Prod'da reverse proxy Basic Auth'unu tetikle (kimlik cache'lensin)
    if (!(await ensureAdminAccess())) {
      setError('Yönetici erişimi gerekli — FTP aracı için kimlik doğrulaması iptal edildi.')
      setConnecting(false)
      return false
    }
    try {
      const res = await axios.post('/api/ftp/session', {
        protocol: 'sftp',
        host: form.host.trim(),
        port: parseInt(form.port, 10) || 22,
        username: form.username.trim(),
        password: form.password || '',
      })
      sessionRef.current = res.data
      setSession(res.data)
      await list('/')
      return true
    } catch (err) {
      setError(errMsg(err, 'Bağlantı kurulamadı — sunucu erişilebilir mi?'))
      return false
    } finally {
      setConnecting(false)
    }
  }

  const disconnect = async () => {
    try { await api({ method: 'delete', url: '/api/ftp/session' }) } catch { /* boş */ }
    clear()
  }

  const list = async (path) => {
    setLoading(true)
    setError('')
    try {
      const res = await api({ method: 'get', url: '/api/ftp/list', params: { path } })
      setEntries(res.data.entries)
      setTruncated(res.data.truncated)
      setCwd(path)
    } catch (err) {
      setError(errMsg(err, 'Dizin listelenemedi'))
      throw err
    } finally {
      setLoading(false)
    }
  }

  const refresh = () => list(cwd)

  const mkdir  = (path) => api({ method: 'post', url: '/api/ftp/mkdir', data: { path } })
  const rename = (src, dst) => api({ method: 'post', url: '/api/ftp/rename', data: { src, dst } })
  const remove = (path, recursive) => api({ method: 'post', url: '/api/ftp/delete', data: { path, recursive } })
  const chmodPath = (path, mode) => api({ method: 'post', url: '/api/ftp/chmod', data: { path, mode } })
  const readFile  = (path) => api({ method: 'get', url: '/api/ftp/file', params: { path } })
  const writeFile = (path, content) => api({ method: 'put', url: '/api/ftp/file', data: { path, content } })

  const upload = async (file, targetDir, onProgress) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('path', targetDir)
    return api({
      method: 'post', url: '/api/ftp/upload', data: fd,
      onUploadProgress: (e) => {
        if (e.total && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
      },
    })
  }

  const download = async (path) => {
    const res = await api({ method: 'post', url: '/api/ftp/download-ticket', data: { path } })
    // Bilet tek kullanımlık ve 60 sn ömürlü — URL'de kimlik bilgisi yok
    const a = document.createElement('a')
    a.href = `/api/ftp/download?ticket=${encodeURIComponent(res.data.ticket)}`
    a.download = ''
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  return {
    session, cwd, entries, truncated, loading, connecting, error, setError,
    connect, disconnect, list, refresh,
    mkdir, rename, remove, chmodPath, readFile, writeFile, upload, download,
  }
}
