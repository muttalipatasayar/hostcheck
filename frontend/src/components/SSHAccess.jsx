import { useEffect, useRef, useState } from 'react'
import { Terminal, Plug, PlugZap, X } from 'lucide-react'
import { Terminal as XTerm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { wsUrl } from '../lib/ws'
import { ensureAdminAccess } from '../lib/adminAuth'
import { useTarget } from '../context/TargetContext'
import { useSavedConnections } from '../hooks/useSavedConnections'
import { useConnectionStatus } from '../hooks/useConnectionStatus'
import { useFullscreen } from '../hooks/useFullscreen'
import { useRefitOnVisible } from '../hooks/useRefitOnVisible'
import RemoteWindowFrame from './remote/RemoteWindowFrame'
import SavedConnectionsList from './remote/SavedConnectionsList'
import ConnectionHeader from './remote/ConnectionHeader'

export default function SSHAccess() {
  const { status, setStatus, errorMsg, setErrorMsg, isConnected, isConnecting, fail, reset } = useConnectionStatus()
  const [form, setForm] = useState({ host: '', port: '22', username: '', password: '' })
  const [activeConn, setActiveConn] = useState({ host: '', port: '22', username: '' })

  const saved = useSavedConnections(
    'ssh_saved_connections',
    (a, b) => a.host === b.host && a.username === b.username,
  )

  const termRef = useRef(null)
  const xtermRef = useRef(null)
  const fitAddonRef = useRef(null)
  const wsRef = useRef(null)
  // Her connect()'te yeniden kaydedilen xterm dinleyicileri (onData/onResize).
  // Ref'te saklanmazlarsa ikinci bağlantıda eski dinleyiciler yaşamaya devam
  // eder ve her tuş vuruşu sokete iki kez gider.
  const listenersRef = useRef([])

  const { isFullscreen, setIsFullscreen, toggle: toggleFullscreen } = useFullscreen(
    () => fitAddonRef.current?.fit()
  )

  // Paylaşılan hedefi TEK YÖNLÜ tüket: mount'ta host alanına ön-doldur,
  // asla geri yazma (keepAlive olduğundan yalnızca ilk ziyarette çalışır)
  const { target } = useTarget()
  useEffect(() => {
    const t = target.trim()
    if (t) setForm(f => f.host ? f : { ...f, host: t })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── xterm örneği (bir kez) ─────────────────────────────────────────────────
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
    return () => {
      // Sekmeden ayrılırken soket açık bırakılırsa her geçiş bir bağlantı sızdırır
      wsRef.current?.close()
      wsRef.current = null
      xterm.dispose()
    }
  }, [])

  // ── xterm'i DOM'a bağla ────────────────────────────────────────────────────
  useEffect(() => {
    if (!termRef.current || !xtermRef.current) return
    xtermRef.current.open(termRef.current)
    try { fitAddonRef.current.fit() } catch { /* boş */ }
  }, [])

  // Görünür/yeniden boyutlanınca terminali yeniden ölçekle
  useRefitOnVisible(termRef, () => fitAddonRef.current?.fit())

  // ── Bağlan ─────────────────────────────────────────────────────────────────
  const connect = async (overrideForm) => {
    const f = overrideForm || form
    if (!f.host || !f.username) return
    // Prod'da reverse proxy Basic Auth'unu tetikle (WS'ten önce kimlik cache'lensin)
    if (!(await ensureAdminAccess())) {
      fail('Yönetici erişimi gerekli — SSH aracı için kimlik doğrulaması iptal edildi.')
      return
    }
    if (wsRef.current) wsRef.current.close()

    // Önceki bağlantının xterm dinleyicilerini bırak — yoksa çift gönderim olur
    listenersRef.current.forEach(d => { try { d.dispose() } catch { /* boş */ } })
    listenersRef.current = []

    setStatus('connecting')
    setErrorMsg('')
    setActiveConn({ host: f.host.trim(), port: String(f.port || 22), username: f.username.trim() })

    const ws = new WebSocket(wsUrl('/api/ssh/ws'))
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
        saved.save({ host: f.host.trim(), port: String(f.port || 22), username: f.username.trim() })
      }

      if (data.includes('Hata:') || data.includes('başarısız') || data.includes('hatası')) {
        const msg = data.split('Hata:')[1] || data
        fail(msg.replace(/[\r\n]/g, ' ').trim())
      }
    }

    ws.onerror = () => {
      fail('WebSocket bağlantısı kurulamadı — backend çalışıyor mu?')
    }

    ws.onclose = () => {
      setStatus(prev => (prev === 'connecting' || prev === 'connected') ? 'idle' : prev)
    }

    const d1 = xtermRef.current?.onData((d) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(new TextEncoder().encode(d))
    })

    const d2 = xtermRef.current?.onResize(({ cols, rows }) => {
      if (ws.readyState === WebSocket.OPEN)
        ws.send(JSON.stringify({ type: 'resize', cols, rows }))
    })

    listenersRef.current = [d1, d2].filter(Boolean)
  }

  const disconnect = () => {
    wsRef.current?.close()
    wsRef.current = null
    reset()
    xtermRef.current?.writeln('\r\n\x1b[38;2;141;144;153mBağlantı kapatıldı.\x1b[0m\r\n')
  }

  const newConnection = () => {
    disconnect()
    setForm({ host: '', port: '22', username: '', password: '' })
    setIsFullscreen(false)
  }

  const showForm = !isConnected && !isConnecting

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Sayfa başlığı ────────────────────────────────────────────────────── */}
      <ConnectionHeader
        icon={<Terminal className="w-4 h-4" style={{ color: '#3b7eff' }} />}
        iconBg="linear-gradient(135deg, rgba(173,198,255,0.2) 0%, rgba(77,142,255,0.15) 100%)"
        title="SSH Terminal"
        subtitle={isConnected
          ? `${activeConn.username}@${activeConn.host}:${activeConn.port} — aktif oturum`
          : 'Sunucularınıza tarayıcı üzerinden SSH ile bağlanın.'}
        showNewConnection={isConnected}
        onNewConnection={newConnection}
      />

      {/* ── Bağlantı formu ───────────────────────────────────────────────────── */}
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

            {/* Hata */}
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

          {/* Kayıtlı bağlantılar */}
          <SavedConnectionsList
            items={saved.items}
            icon={<Terminal className="w-3.5 h-3.5" style={{ color: '#3b7eff' }} />}
            iconBg="rgba(173,198,255,0.08)"
            subtitle={(c) => `port ${c.port}`}
            onSelect={(c) => setForm({ ...c, password: '' })}
            onRemove={saved.remove}
          />
        </div>
      )}

      {/* ── Bağlanıyor bandı ─────────────────────────────────────────────────── */}
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

      {/* ── Terminal penceresi ───────────────────────────────────────────────── */}
      <RemoteWindowFrame
        tabIcon={<span className="font-bold" style={{ color: '#3b7eff', letterSpacing: '-0.5px' }}>{'>'}_</span>}
        tabLabel={isConnected || isConnecting
          ? `${activeConn.username || form.username}@${activeConn.host || form.host}:${activeConn.port || form.port}`
          : 'terminal'}
        isFullscreen={isFullscreen}
        isConnected={isConnected}
        isConnecting={isConnecting}
        onToggleFullscreen={toggleFullscreen}
        onDisconnect={disconnect}
      >
        <div className="flex-1 min-h-0 px-2 pt-2 pb-2" style={{ background: '#0d0f13' }}>
          <div ref={termRef} style={{ height: '100%', width: '100%' }} />
        </div>
      </RemoteWindowFrame>
    </div>
  )
}
