import { useEffect, useRef, useState } from 'react'
import { Terminal, Plug, PlugZap, X, RotateCcw, Clock, Maximize2, Minimize2 } from 'lucide-react'
import { Terminal as XTerm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'

const WS_URL = 'ws://localhost:8000/api/ssh/ws'
const SAVED_KEY = 'ssh_saved_connections'

function loadSaved() {
  try { return JSON.parse(localStorage.getItem(SAVED_KEY) || '[]') }
  catch { return [] }
}

function persistSaved(list) {
  localStorage.setItem(SAVED_KEY, JSON.stringify(list.slice(0, 8)))
}

export default function SSHAccess() {
  const [status, setStatus] = useState('idle') // idle | connecting | connected | error
  const [errorMsg, setErrorMsg] = useState('')
  const [form, setForm] = useState({ host: '', port: '22', username: '', password: '' })
  const [savedConns, setSavedConns] = useState(loadSaved)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [activeConn, setActiveConn] = useState({ host: '', port: '22', username: '' })

  const termRef = useRef(null)
  const xtermRef = useRef(null)
  const fitAddonRef = useRef(null)
  const wsRef = useRef(null)

  // ── xterm instance (once) ──────────────────────────────────────────────────
  useEffect(() => {
    const xterm = new XTerm({
      theme: {
        background: '#111520',
        foreground: '#e8eaf4',
        cursor: '#3b7eff',
        cursorAccent: '#111520',
        selectionBackground: 'rgba(59,127,255,0.25)',
        black: '#1a1d2e',
        brightBlack: '#6b7388',
        white: '#e8eaf4',
        brightWhite: '#ffffff',
        blue: '#3b7eff',
        brightBlue: '#4a6cf7',
        cyan: '#7dd5f4',
        brightCyan: '#9eeaf9',
        green: '#a8d5a2',
        brightGreen: '#c5e8c1',
        red: '#ffb4ab',
        brightRed: '#ffc9c4',
        yellow: '#f5d37a',
        brightYellow: '#fde68a',
        magenta: '#d4a8ff',
        brightMagenta: '#e5c7ff',
      },
      fontFamily: '"Cascadia Code", "Fira Code", "JetBrains Mono", "Consolas", monospace',
      fontSize: 14,
      lineHeight: 1.45,
      cursorBlink: true,
      cursorStyle: 'block',
      scrollback: 5000,
      convertEol: true,
      allowProposedApi: true,
    })
    const fit = new FitAddon()
    xterm.loadAddon(fit)
    xtermRef.current = xterm
    fitAddonRef.current = fit
    return () => xterm.dispose()
  }, [])

  // ── Mount xterm to DOM ─────────────────────────────────────────────────────
  useEffect(() => {
    if (!termRef.current || !xtermRef.current) return
    xtermRef.current.open(termRef.current)
    try { fitAddonRef.current.fit() } catch (_) {}

    const ro = new ResizeObserver(() => {
      try { fitAddonRef.current.fit() } catch (_) {}
    })
    ro.observe(termRef.current)
    return () => ro.disconnect()
  }, [])

  // ── Connect ────────────────────────────────────────────────────────────────
  const connect = (overrideForm) => {
    const f = overrideForm || form
    if (!f.host || !f.username) return
    if (wsRef.current) wsRef.current.close()

    setStatus('connecting')
    setErrorMsg('')
    setActiveConn({ host: f.host.trim(), port: String(f.port || 22), username: f.username.trim() })

    const ws = new WebSocket(WS_URL)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify({
        host: f.host.trim(),
        port: parseInt(f.port, 10) || 22,
        username: f.username.trim(),
        password: f.password,
      }))
    }

    ws.onmessage = (ev) => {
      if (!xtermRef.current) return
      const data = ev.data instanceof ArrayBuffer
        ? new TextDecoder().decode(ev.data)
        : ev.data

      xtermRef.current.write(data)

      if (data.includes('Bağlantı kuruldu')) {
        setStatus('connected')
        // Kaydedilmiş bağlantılara ekle (şifresiz)
        const entry = { host: f.host.trim(), port: String(f.port || 22), username: f.username.trim() }
        setSavedConns(prev => {
          const deduped = prev.filter(c => !(c.host === entry.host && c.username === entry.username))
          const updated = [entry, ...deduped]
          persistSaved(updated)
          return updated
        })
      }

      if (data.includes('Hata:') || data.includes('başarısız') || data.includes('hatası')) {
        setStatus('error')
        const msg = data.split('Hata:')[1] || data
        setErrorMsg(msg.replace(/[\r\n]/g, ' ').trim())
      }
    }

    ws.onerror = () => {
      setStatus('error')
      setErrorMsg('WebSocket bağlantısı kurulamadı — backend çalışıyor mu?')
    }

    ws.onclose = () => {
      setStatus(prev => (prev === 'connecting' || prev === 'connected') ? 'idle' : prev)
    }

    xtermRef.current?.onData((d) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(new TextEncoder().encode(d))
    })

    xtermRef.current?.onResize(({ cols, rows }) => {
      if (ws.readyState === WebSocket.OPEN)
        ws.send(JSON.stringify({ type: 'resize', cols, rows }))
    })
  }

  const disconnect = () => {
    wsRef.current?.close()
    wsRef.current = null
    setStatus('idle')
    setErrorMsg('')
    xtermRef.current?.writeln('\r\n\x1b[38;2;141;144;153mBağlantı kapatıldı.\x1b[0m\r\n')
  }

  const newConnection = () => {
    disconnect()
    setForm({ host: '', port: '22', username: '', password: '' })
    setIsFullscreen(false)
  }

  const toggleFullscreen = () => {
    setIsFullscreen(f => !f)
    setTimeout(() => { try { fitAddonRef.current?.fit() } catch (_) {} }, 60)
  }

  const removeSaved = (i, e) => {
    e.stopPropagation()
    setSavedConns(prev => {
      const updated = prev.filter((_, idx) => idx !== i)
      persistSaved(updated)
      return updated
    })
  }

  const isConnected = status === 'connected'
  const isConnecting = status === 'connecting'
  const showForm = !isConnected && !isConnecting

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Page Header ──────────────────────────────────────────────────────── */}
      <div className="px-8 pt-8 pb-5 flex-shrink-0 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div
              className="w-8 h-8 rounded-btn flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, rgba(173,198,255,0.2) 0%, rgba(77,142,255,0.15) 100%)' }}
            >
              <Terminal className="w-4 h-4" style={{ color: '#3b7eff' }} />
            </div>
            <h1 className="text-headline-md font-semibold" style={{ color: '#1a1d2e' }}>
              SSH Terminal
            </h1>
          </div>
          <p className="text-body-md pl-11" style={{ color: '#6b7388' }}>
            {isConnected
              ? `${activeConn.username}@${activeConn.host}:${activeConn.port} — aktif oturum`
              : 'Sunucularınıza tarayıcı üzerinden SSH ile bağlanın.'}
          </p>
        </div>

        {isConnected && (
          <button
            onClick={newConnection}
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

      {/* ── Connection Form ───────────────────────────────────────────────────── */}
      {showForm && (
        <div className="px-8 pb-5 flex-shrink-0 overflow-y-auto">
          <div className="rounded-card p-5" style={{ background: '#ffffff' }}>
            <p className="text-label-sm font-medium mb-4" style={{ color: '#6b7388' }}>
              BAĞLANTI BİLGİLERİ
            </p>

            <div className="grid grid-cols-3 gap-3 mb-3">
              <div className="col-span-2">
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>
                  Sunucu (Host / IP)
                </label>
                <input
                  type="text"
                  className="input-field w-full"
                  placeholder="192.168.1.1 veya sunucu.com"
                  value={form.host}
                  onChange={(e) => setForm(f => ({ ...f, host: e.target.value }))}
                  onKeyDown={(e) => e.key === 'Enter' && connect()}
                />
              </div>
              <div>
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>Port</label>
                <input
                  type="number"
                  className="input-field w-full"
                  placeholder="22"
                  value={form.port}
                  onChange={(e) => setForm(f => ({ ...f, port: e.target.value }))}
                  min="1" max="65535"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <div>
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>Kullanıcı Adı</label>
                <input
                  type="text"
                  className="input-field w-full"
                  placeholder="root"
                  value={form.username}
                  onChange={(e) => setForm(f => ({ ...f, username: e.target.value }))}
                  onKeyDown={(e) => e.key === 'Enter' && connect()}
                  autoComplete="username"
                />
              </div>
              <div>
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>Şifre</label>
                <input
                  type="password"
                  className="input-field w-full"
                  placeholder="••••••••"
                  value={form.password}
                  onChange={(e) => setForm(f => ({ ...f, password: e.target.value }))}
                  onKeyDown={(e) => e.key === 'Enter' && connect()}
                  autoComplete="current-password"
                />
              </div>
            </div>

            {/* Error */}
            {errorMsg && (
              <div
                className="rounded-btn px-4 py-2.5 mb-4 text-body-sm flex items-start gap-2"
                style={{ background: 'rgba(255,180,171,0.08)', color: '#ffb4ab', border: '1px solid rgba(255,180,171,0.2)' }}
              >
                <X className="w-4 h-4 mt-0.5 flex-shrink-0" />
                {errorMsg}
              </div>
            )}

            <button
              onClick={() => connect()}
              disabled={!form.host || !form.username}
              className="btn-primary flex items-center gap-2"
            >
              <Plug className="w-4 h-4" />
              Bağlan
            </button>
          </div>

          {/* Saved Connections */}
          {savedConns.length > 0 && (
            <div className="mt-5">
              <p
                className="text-label-sm font-medium uppercase tracking-wider mb-2 flex items-center gap-1.5"
                style={{ color: '#9da5be' }}
              >
                <Clock className="w-3.5 h-3.5" />
                Son Bağlantılar
              </p>
              <div className="flex flex-col gap-1.5">
                {savedConns.map((c, i) => (
                  <button
                    key={i}
                    onClick={() => setForm({ ...c, password: '' })}
                    className="group flex items-center gap-3 px-4 py-3 rounded-btn text-left w-full transition-colors"
                    style={{ background: '#ffffff' }}
                  >
                    <div
                      className="w-7 h-7 rounded flex items-center justify-center flex-shrink-0"
                      style={{ background: 'rgba(173,198,255,0.08)' }}
                    >
                      <Terminal className="w-3.5 h-3.5" style={{ color: '#3b7eff' }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-body-sm font-medium truncate" style={{ color: '#1a1d2e' }}>
                        {c.username}@{c.host}
                      </p>
                      <p className="text-label-sm" style={{ color: '#9da5be' }}>port {c.port}</p>
                    </div>
                    <button
                      onClick={(e) => removeSaved(i, e)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded transition-opacity"
                      style={{ color: '#9da5be' }}
                      title="Sil"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Connecting banner ─────────────────────────────────────────────────── */}
      {isConnecting && (
        <div className="px-8 pb-4 flex-shrink-0">
          <div
            className="rounded-btn px-4 py-2.5 flex items-center gap-2.5 text-body-sm"
            style={{ background: 'rgba(59,127,255,0.06)', border: '1px solid rgba(59,127,255,0.10)', color: '#3b7eff' }}
          >
            <PlugZap className="w-4 h-4 animate-pulse" />
            {form.username}@{form.host}:{form.port} — bağlanıyor…
          </div>
        </div>
      )}

      {/* ── Terminal Window ───────────────────────────────────────────────────── */}
      <div
        className={`min-h-0 flex-1 flex flex-col ${
          isFullscreen
            ? 'fixed inset-0 z-50 bg-black'
            : 'px-8 pb-8'
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
          {/* ── macOS-style title bar ── */}
          <div
            className="flex items-center gap-3 px-4 py-2.5 flex-shrink-0 select-none"
            style={{ background: '#1e2025', borderBottom: '1px solid rgba(66,71,84,0.5)' }}
          >
            {/* Traffic lights */}
            <div className="flex items-center gap-2">
              <button
                onClick={disconnect}
                title="Bağlantıyı kes"
                className="w-3 h-3 rounded-full transition-opacity hover:opacity-75 active:scale-95"
                style={{ background: '#ff5f57' }}
              />
              <div className="w-3 h-3 rounded-full" style={{ background: '#febc2e' }} />
              <div
                className="w-3 h-3 rounded-full cursor-pointer transition-opacity hover:opacity-75"
                onClick={toggleFullscreen}
                title="Tam ekran"
                style={{ background: '#28c840' }}
              />
            </div>

            {/* Tab */}
            <div
              className="flex items-center gap-2 px-3 py-1 rounded text-label-sm"
              style={{
                background: 'rgba(255,255,255,0.06)',
                color: '#c9cdd6',
                maxWidth: '300px',
              }}
            >
              <span className="font-bold" style={{ color: '#3b7eff', letterSpacing: '-0.5px' }}>{'>'}_</span>
              <span className="truncate">
                {isConnected || isConnecting
                  ? `${activeConn.username || form.username}@${activeConn.host || form.host}:${activeConn.port || form.port}`
                  : 'terminal'}
              </span>
            </div>

            <div className="flex-1" />

            {/* Right controls */}
            <div className="flex items-center gap-3">
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
                onClick={toggleFullscreen}
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
                onClick={disconnect}
                className="p-1 rounded transition-opacity hover:opacity-70"
                style={{ color: '#6b7388' }}
                title="Kapat"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* ── xterm body ── */}
          <div className="flex-1 min-h-0 px-2 pt-2 pb-2" style={{ background: '#0d0f13' }}>
            <div ref={termRef} style={{ height: '100%', width: '100%' }} />
          </div>
        </div>
      </div>
    </div>
  )
}
