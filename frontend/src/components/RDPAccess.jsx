import { useEffect, useRef, useState, useCallback } from 'react'
import Guacamole from 'guacamole-common-js'
import {
  Monitor, Plug, PlugZap, X, RotateCcw, Clock,
  Maximize2, Minimize2, AlertTriangle, Info,
} from 'lucide-react'

const SAVED_KEY = 'rdp_saved_connections'
const MAX_SAVED = 8

function loadSaved() {
  try { return JSON.parse(localStorage.getItem(SAVED_KEY) || '[]') }
  catch { return [] }
}

function persistSaved(list) {
  localStorage.setItem(SAVED_KEY, JSON.stringify(list.slice(0, MAX_SAVED)))
}

export default function RDPAccess() {
  const [status, setStatus]         = useState('idle') // idle | connecting | connected | error
  const [errorMsg, setErrorMsg]     = useState('')
  const [isFullscreen, setFullscreen] = useState(false)
  const [savedConns, setSavedConns] = useState(loadSaved)
  const [activeConn, setActiveConn] = useState(null)
  const [form, setForm] = useState({
    host: '', port: '3389', username: '', password: '', domain: '',
  })

  const displayContainerRef = useRef(null) // <div> where Guacamole canvas is mounted
  const clientRef            = useRef(null)
  const keyboardRef          = useRef(null)

  // ── Cleanup on unmount ───────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (clientRef.current) {
        try { clientRef.current.disconnect() } catch {}
      }
      if (keyboardRef.current) {
        try { keyboardRef.current.reset() } catch {}
      }
    }
  }, [])

  // ── Scale display to fit container ──────────────────────────────────────────
  const fitDisplay = useCallback(() => {
    const client = clientRef.current
    const container = displayContainerRef.current
    if (!client || !container) return
    const display = client.getDisplay()
    const remoteW = display.getWidth()
    const remoteH = display.getHeight()
    if (!remoteW || !remoteH) return
    const containerW = container.clientWidth
    const containerH = container.clientHeight
    const scale = Math.min(containerW / remoteW, containerH / remoteH)
    display.scale(scale)
  }, [])

  // ── Connect ──────────────────────────────────────────────────────────────────
  const connect = useCallback((overrideForm) => {
    const f = overrideForm || form
    if (!f.host?.trim() || !f.username?.trim()) return

    // Tear down any existing session
    if (clientRef.current) {
      try { clientRef.current.disconnect() } catch {}
      clientRef.current = null
    }
    if (keyboardRef.current) {
      try { keyboardRef.current.reset() } catch {}
      keyboardRef.current = null
    }
    if (displayContainerRef.current) {
      displayContainerRef.current.innerHTML = ''
    }

    setStatus('connecting')
    setErrorMsg('')
    setActiveConn({ host: f.host.trim(), port: f.port || '3389', username: f.username.trim(), domain: f.domain || '' })

    const container = displayContainerRef.current
    const w = container?.clientWidth  || 1280
    const h = container?.clientHeight || 720

    // Build WebSocket URL — goes through Vite proxy in dev
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsBase = `${proto}//${window.location.host}/api/rdp/ws`

    const tunnel = new Guacamole.WebSocketTunnel(wsBase)
    const client = new Guacamole.Client(tunnel)

    // Mount canvas
    const displayEl = client.getDisplay().getElement()
    displayEl.style.display = 'block'
    container.appendChild(displayEl)

    // Keyboard — attach to display element only (won't steal focus from UI inputs)
    const keyboard = new Guacamole.Keyboard(displayEl)
    keyboard.onkeydown = (keysym) => client.sendKeyEvent(1, keysym)
    keyboard.onkeyup   = (keysym) => client.sendKeyEvent(0, keysym)
    keyboardRef.current = keyboard

    // Mouse
    const mouse = new Guacamole.Mouse(displayEl)
    mouse.onmousedown = (state) => client.sendMouseState(state)
    mouse.onmouseup   = (state) => client.sendMouseState(state)
    mouse.onmousemove = (state) => client.sendMouseState(state)

    // Click on canvas to capture keyboard focus
    displayEl.setAttribute('tabindex', '0')
    displayEl.addEventListener('click', () => displayEl.focus())

    // Display resize → re-scale
    client.getDisplay().onresize = fitDisplay

    // State changes
    client.onstatechange = (state) => {
      // 3 = CONNECTED
      if (state === 3) {
        setStatus('connected')
        fitDisplay()

        // Kaydet (şifresiz)
        const entry = {
          host: f.host.trim(),
          port: f.port || '3389',
          username: f.username.trim(),
          domain: f.domain || '',
          lastUsed: Date.now(),
        }
        setSavedConns(prev => {
          const deduped = prev.filter(
            c => !(c.host === entry.host && c.port === entry.port && c.username === entry.username)
          )
          const updated = [entry, ...deduped]
          persistSaved(updated)
          return updated
        })
      }
      // 5 = DISCONNECTED
      if (state === 5) {
        setStatus(s => (s === 'connected' || s === 'connecting') ? 'idle' : s)
        setActiveConn(null)
      }
    }

    // Errors
    client.onerror = (status) => {
      const msg = status?.message || 'Bilinmeyen hata'
      setStatus('error')
      setErrorMsg(msg)
    }

    clientRef.current = client

    // Connect params appended to WS URL as query string
    const params = new URLSearchParams({
      hostname: f.host.trim(),
      port:     String(f.port || 3389),
      username: f.username.trim(),
      password: f.password || '',
      domain:   f.domain   || '',
      width:    String(w),
      height:   String(h),
    })
    client.connect(params.toString())
  }, [form, fitDisplay])

  // ── Disconnect ───────────────────────────────────────────────────────────────
  const disconnect = useCallback(() => {
    if (clientRef.current) {
      try { clientRef.current.disconnect() } catch {}
      clientRef.current = null
    }
    if (keyboardRef.current) {
      try { keyboardRef.current.reset() } catch {}
      keyboardRef.current = null
    }
    if (displayContainerRef.current) {
      displayContainerRef.current.innerHTML = ''
    }
    setStatus('idle')
    setErrorMsg('')
    setActiveConn(null)
  }, [])

  const newConnection = () => {
    disconnect()
    setForm({ host: '', port: '3389', username: '', password: '', domain: '' })
    setFullscreen(false)
  }

  const toggleFullscreen = () => {
    setFullscreen(v => !v)
    setTimeout(fitDisplay, 80)
  }

  const removeSaved = (i, e) => {
    e.stopPropagation()
    setSavedConns(prev => {
      const updated = prev.filter((_, idx) => idx !== i)
      persistSaved(updated)
      return updated
    })
  }

  const loadSavedConn = (c) => {
    setForm({ host: c.host, port: c.port, username: c.username, password: '', domain: c.domain || '' })
  }

  // ResizeObserver for display container
  useEffect(() => {
    if (!displayContainerRef.current) return
    const ro = new ResizeObserver(fitDisplay)
    ro.observe(displayContainerRef.current)
    return () => ro.disconnect()
  }, [fitDisplay])

  const isConnected  = status === 'connected'
  const isConnecting = status === 'connecting'
  const showForm     = !isConnected && !isConnecting

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Page Header ────────────────────────────────────────────────────────── */}
      <div className="px-8 pt-8 pb-5 flex-shrink-0 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div
              className="w-8 h-8 rounded-btn flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg,rgba(212,168,255,.2) 0%,rgba(168,85,247,.15) 100%)' }}
            >
              <Monitor className="w-4 h-4" style={{ color: '#d4a8ff' }} />
            </div>
            <h1 className="text-headline-md font-semibold" style={{ color: '#1a1d2e' }}>
              RDP Uzak Masaüstü
            </h1>
          </div>
          <p className="text-body-md pl-11" style={{ color: '#6b7388' }}>
            {isConnected
              ? `${activeConn?.username}@${activeConn?.host}:${activeConn?.port} — aktif oturum`
              : 'Windows sunucularına tarayıcı üzerinden uzak masaüstü bağlantısı açın.'}
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

            {/* Row 1: Host + Port */}
            <div className="grid grid-cols-3 gap-3 mb-3">
              <div className="col-span-2">
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>
                  Sunucu (Host / IP)
                </label>
                <input
                  type="text"
                  className="input-field w-full"
                  placeholder="192.168.1.10 veya sunucu.com"
                  value={form.host}
                  onChange={e => setForm(f => ({ ...f, host: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && connect()}
                />
              </div>
              <div>
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>Port</label>
                <input
                  type="number"
                  className="input-field w-full"
                  placeholder="3389"
                  value={form.port}
                  onChange={e => setForm(f => ({ ...f, port: e.target.value }))}
                  min="1"
                  max="65535"
                />
              </div>
            </div>

            {/* Row 2: Username + Password */}
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>Kullanıcı Adı</label>
                <input
                  type="text"
                  className="input-field w-full"
                  placeholder="Administrator"
                  value={form.username}
                  onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && connect()}
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
                  onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  onKeyDown={e => e.key === 'Enter' && connect()}
                  autoComplete="current-password"
                />
              </div>
            </div>

            {/* Row 3: Domain (optional) */}
            <div className="mb-4">
              <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>
                Domain <span style={{ color: '#9da5be' }}>(isteğe bağlı)</span>
              </label>
              <input
                type="text"
                className="input-field w-full"
                placeholder="WORKGROUP veya domain.local"
                value={form.domain}
                onChange={e => setForm(f => ({ ...f, domain: e.target.value }))}
                onKeyDown={e => e.key === 'Enter' && connect()}
              />
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

            <div className="flex items-center gap-3">
              <button
                onClick={() => connect()}
                disabled={!form.host?.trim() || !form.username?.trim()}
                className="btn-primary flex items-center gap-2"
              >
                <Plug className="w-4 h-4" />
                Bağlan
              </button>

              {/* guacd info */}
              <div
                className="flex items-center gap-1.5 text-label-sm"
                style={{ color: '#9da5be' }}
                title="guacd Docker: docker run -d -p 4822:4822 guacamole/guacd"
              >
                <Info className="w-3.5 h-3.5" />
                guacd gerektirir
              </div>
            </div>

            {/* guacd setup hint */}
            <div
              className="mt-4 px-3 py-2.5 rounded-btn text-label-sm"
              style={{ background: 'rgba(59,127,255,0.05)', color: '#6b7388', border: '1px solid rgba(59,127,255,0.09)' }}
            >
              <span style={{ color: '#3b7eff' }}>guacd kurulum:</span>
              {'  '}
              <code style={{ color: '#c9cdd6', background: 'rgba(0,6,30,0.04)', padding: '1px 6px', borderRadius: 4 }}>
                docker run -d -p 4822:4822 guacamole/guacd
              </code>
            </div>
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
                    onClick={() => loadSavedConn(c)}
                    className="group flex items-center gap-3 px-4 py-3 rounded-btn text-left w-full transition-colors"
                    style={{ background: '#ffffff' }}
                  >
                    <div
                      className="w-7 h-7 rounded flex items-center justify-center flex-shrink-0"
                      style={{ background: 'rgba(212,168,255,0.08)' }}
                    >
                      <Monitor className="w-3.5 h-3.5" style={{ color: '#d4a8ff' }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-body-sm font-medium truncate" style={{ color: '#1a1d2e' }}>
                        {c.username}@{c.host}
                      </p>
                      <p className="text-label-sm" style={{ color: '#9da5be' }}>
                        port {c.port}{c.domain ? ` · ${c.domain}` : ''}
                      </p>
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

      {/* ── Connecting banner ────────────────────────────────────────────────── */}
      {isConnecting && (
        <div className="px-8 pb-4 flex-shrink-0">
          <div
            className="rounded-btn px-4 py-2.5 flex items-center gap-2.5 text-body-sm"
            style={{ background: 'rgba(212,168,255,0.07)', border: '1px solid rgba(212,168,255,0.12)', color: '#d4a8ff' }}
          >
            <PlugZap className="w-4 h-4 animate-pulse" />
            {form.username}@{form.host}:{form.port} — bağlanıyor…
          </div>
        </div>
      )}

      {/* ── RDP Window ───────────────────────────────────────────────────────── */}
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
              style={{ background: 'rgba(255,255,255,0.06)', color: '#c9cdd6', maxWidth: '320px' }}
            >
              <Monitor className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#d4a8ff' }} />
              <span className="truncate">
                {isConnected || isConnecting
                  ? `${activeConn?.username || form.username}@${activeConn?.host || form.host}:${activeConn?.port || form.port}`
                  : 'rdp'}
              </span>
            </div>

            <div className="flex-1" />

            {/* Status + controls */}
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

          {/* ── Display area ── */}
          <div
            className="flex-1 min-h-0 overflow-hidden flex items-center justify-center"
            style={{ background: '#0d0f13', cursor: isConnected ? 'default' : 'default' }}
          >
            {/* Guacamole canvas is mounted here imperatively */}
            <div
              ref={displayContainerRef}
              style={{ width: '100%', height: '100%', overflow: 'hidden', position: 'relative' }}
            />

            {/* Idle placeholder */}
            {!isConnected && !isConnecting && (
              <div
                className="absolute flex flex-col items-center gap-3 pointer-events-none"
                style={{ color: '#f2f4fa' }}
              >
                <Monitor className="w-16 h-16" />
                <p className="text-body-md" style={{ color: '#9da5be' }}>
                  Uzak masaüstü bekleniyor
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
