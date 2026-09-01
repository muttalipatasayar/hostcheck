import { useEffect, useRef, useState, useCallback } from 'react'
import Guacamole from 'guacamole-common-js'
import axios from 'axios'
import toast from 'react-hot-toast'
import {
  Monitor, Plug, PlugZap, X, Info,
  ClipboardCopy, ClipboardPaste, CheckCircle2, XCircle, RefreshCw,
} from 'lucide-react'
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
import { apiHataMesaji } from '../lib/apiHata'

// Windows sunucular çoğunlukla NLA ister; "Otomatik" pazarlığı bazı
// sunucu/guacd ikililerinde başarısız olur — açık seçim şart
const SECURITY_MODES = [
  { id: 'any', label: 'Otomatik (önerilen)' },
  { id: 'nla', label: 'NLA — modern Windows varsayılanı' },
  { id: 'tls', label: 'TLS' },
  { id: 'rdp', label: 'RDP (eski sunucular)' },
]

// Guacamole durum kodları → teknisyene Türkçe teşhis ipucu
const STATUS_HINTS = {
  514: 'Sunucu yanıt vermedi (zaman aşımı) — IP/port doğru mu, 3389 güvenlik duvarında açık mı?',
  515: "RDP el sıkışması başarısız — Güvenlik modunu 'NLA' (veya eski sunucuda 'RDP') olarak değiştirip yeniden deneyin",
  516: 'Kaynak bulunamadı',
  519: 'Sunucuya ulaşılamadı — adres yanlış veya 3389 portu kapalı olabilir',
  520: 'Sunucu şu an erişilemez durumda',
  768: 'Geçersiz bağlantı parametresi',
  769: 'Kimlik doğrulama başarısız — kullanıcı adı / şifre / domain (NLA) kontrol edin',
  771: 'Erişim reddedildi — hesabın uzak masaüstü izni olmayabilir',
}

export default function RDPAccess() {
  const { status, setStatus, errorMsg, setErrorMsg, isConnected, isConnecting, fail, reset } = useConnectionStatus()
  const [activeConn, setActiveConn] = useState(null)
  const [form, setForm] = useState({
    host: '', port: '3389', username: '', password: '', domain: '', security: 'any',
  })
  const [guacd, setGuacd] = useState(null)          // null: kontrol ediliyor
  const [remoteClip, setRemoteClip] = useState('')  // uzaktan gelen pano metni
  const [clipInput, setClipInput] = useState('')    // uzağa gönderilecek metin

  // guacd erişilebilirlik kontrolü — "bağlanmıyor" şikayetlerinin 1 numaralı
  // nedeni guacd'ın hiç çalışmıyor olması; formda peşinen gösterilir
  const checkGuacd = useCallback(() => {
    setGuacd(null)
    axios.get('/api/rdp/guacd-status')
      .then(({ data }) => setGuacd(data))
      .catch(() => setGuacd({ running: false, address: '127.0.0.1:4822' }))
  }, [])

  const saved = useSavedConnections(
    'rdp_saved_connections',
    (a, b) => a.host === b.host && a.port === b.port && a.username === b.username,
  )

  // Paylaşılan hedefi TEK YÖNLÜ tüket: mount'ta host alanına ön-doldur,
  // asla geri yazma (keepAlive olduğundan yalnızca ilk ziyarette çalışır)
  const { target } = useTarget()
  useEffect(() => {
    const t = target.trim()
    if (t) setForm(f => f.host ? f : { ...f, host: t })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const displayContainerRef = useRef(null) // Guacamole canvas'ının bağlandığı <div>
  const clientRef            = useRef(null)
  const keyboardRef          = useRef(null)

  // ── Unmount temizliği ────────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      if (clientRef.current) {
        try { clientRef.current.disconnect() } catch { /* boş */ }
      }
      if (keyboardRef.current) {
        try { keyboardRef.current.reset() } catch { /* boş */ }
      }
    }
  }, [])

  // ── Ekranı konteynere sığdır ─────────────────────────────────────────────────
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

  const { isFullscreen, setIsFullscreen, toggle: toggleFullscreen } = useFullscreen(fitDisplay)

  // Konteyner görünür/yeniden boyutlanınca ekranı yeniden ölçekle
  useRefitOnVisible(displayContainerRef, fitDisplay)

  // ── Bağlan ───────────────────────────────────────────────────────────────────
  const connect = useCallback(async (overrideForm) => {
    const f = overrideForm || form
    if (!f.host?.trim() || !f.username?.trim()) return
    // Prod'da reverse proxy Basic Auth'unu tetikle (WS'ten önce kimlik cache'lensin)
    if (!(await ensureAdminAccess())) {
      fail('Yönetici erişimi gerekli — RDP aracı için kimlik doğrulaması iptal edildi.')
      return
    }

    // Varsa mevcut oturumu kapat
    if (clientRef.current) {
      try { clientRef.current.disconnect() } catch { /* boş */ }
      clientRef.current = null
    }
    if (keyboardRef.current) {
      try { keyboardRef.current.reset() } catch { /* boş */ }
      keyboardRef.current = null
    }
    if (displayContainerRef.current) {
      displayContainerRef.current.innerHTML = ''
    }

    setStatus('connecting')
    setErrorMsg('')
    setActiveConn({ host: f.host.trim(), port: f.port || '3389', username: f.username.trim(), domain: f.domain || '' })

    // Form açıkken görüntü alanı daralmış olabilir (ör. 57px yükseklik) —
    // backend 320x240 altını reddeder ve bağlantı hiç kurulamazdı. Ölçüyü
    // makul sınırlara sıkıştır; bağlandıktan sonra fitDisplay zaten ölçekler.
    const container = displayContainerRef.current
    const w = Math.min(Math.max(container?.clientWidth || 1280, 800), 7680)
    const h = Math.min(Math.max(container?.clientHeight || 720, 600), 4320)

    const tunnel = new Guacamole.WebSocketTunnel(wsUrl('/api/rdp/ws'))
    const client = new Guacamole.Client(tunnel)

    // Canvas'ı bağla
    const displayEl = client.getDisplay().getElement()
    displayEl.style.display = 'block'
    container.appendChild(displayEl)

    // Klavye — yalnızca display elemanına bağlanır (UI girdilerinden odak çalmaz)
    const keyboard = new Guacamole.Keyboard(displayEl)
    keyboard.onkeydown = (keysym) => client.sendKeyEvent(1, keysym)
    keyboard.onkeyup   = (keysym) => client.sendKeyEvent(0, keysym)
    keyboardRef.current = keyboard

    // Fare
    const mouse = new Guacamole.Mouse(displayEl)
    mouse.onmousedown = (state) => client.sendMouseState(state)
    mouse.onmouseup   = (state) => client.sendMouseState(state)
    mouse.onmousemove = (state) => client.sendMouseState(state)

    // Canvas'a tıklayınca klavye odağını al
    displayEl.setAttribute('tabindex', '0')
    displayEl.addEventListener('click', () => displayEl.focus())

    // ── Pano senkronu: uzak → yerel ─────────────────────────────────────────
    client.onclipboard = (stream, mimetype) => {
      if (!mimetype.startsWith('text/')) { stream.sendAck('Yalnızca metin', 0x0100); return }
      const reader = new Guacamole.StringReader(stream)
      let data = ''
      reader.ontext = (t) => { data += t }
      reader.onend = () => {
        setRemoteClip(data)
        // navigator.clipboard yalnızca secure context'te var (localhost sayılır,
        // LAN IP'si SAYILMAZ) — yoksa metin aşağıdaki kutuda gösterilir
        if (window.isSecureContext && navigator.clipboard?.writeText) {
          navigator.clipboard.writeText(data).catch(() => {})
        }
      }
    }

    // ── Pano senkronu: yerel → uzak (paste olayı insecure context'te de
    // veri taşır — Ctrl+V canvas'a odaklıyken içerik uzağa gider) ────────────
    displayEl.addEventListener('paste', (ev) => {
      const text = ev.clipboardData?.getData('text/plain')
      if (text && clientRef.current === client) {
        const stream = client.createClipboardStream('text/plain')
        const writer = new Guacamole.StringWriter(stream)
        writer.sendText(text)
        writer.sendEnd()
      }
    })

    // Uzak ekran yeniden boyutlanınca yeniden ölçekle
    client.getDisplay().onresize = fitDisplay

    // Durum değişimleri
    client.onstatechange = (state) => {
      // 3 = CONNECTED
      if (state === 3) {
        setStatus('connected')
        fitDisplay()

        // Kaydet (şifresiz)
        saved.save({
          host: f.host.trim(),
          port: f.port || '3389',
          username: f.username.trim(),
          domain: f.domain || '',
          lastUsed: Date.now(),
        })
      }
      // 5 = DISCONNECTED
      if (state === 5) {
        setStatus(s => (s === 'connected' || s === 'connecting') ? 'idle' : s)
        setActiveConn(null)
      }
    }

    // Hatalar — Guacamole kodunu Türkçe teşhis ipucuyla zenginleştir.
    // Backend'in ürettiği mesajlar zaten Türkçe; onlara ipucu ekleme.
    client.onerror = (status) => {
      const msg = status?.message || 'Bilinmeyen hata'
      const hint = STATUS_HINTS[status?.code]
      const alreadyTurkish = /[çğıöşü]/i.test(msg)
      fail(alreadyTurkish || !hint ? msg : `${hint} (kod ${status?.code} — ${msg})`)
    }

    clientRef.current = client

    // Kimlik bilgileri POST gövdesinde gider; WebSocket URL'i yalnızca kısa
    // ömürlü, tek kullanımlık bir bilet taşır. Şifre hiçbir zaman URL'de,
    // tarayıcı geçmişinde veya sunucu access logunda görünmez.
    axios.post('/api/rdp/session', {
      hostname: f.host.trim(),
      port:     Number(f.port) || 3389,
      username: f.username.trim(),
      password: f.password || '',
      domain:   f.domain   || '',
      width:    w,
      height:   h,
      security: f.security || 'any',
    })
      .then(({ data }) => {
        // Kullanıcı bilet gelene kadar bağlantıyı iptal etmiş olabilir
        if (clientRef.current !== client) return
        client.connect(new URLSearchParams({ ticket: data.ticket }).toString())
      })
      .catch((err) => {
        if (clientRef.current !== client) return
        fail(apiHataMesaji(err, 'Bağlantı oturumu oluşturulamadı'))
      })
  }, [form, fitDisplay, fail, saved, setStatus, setErrorMsg])

  // ── Bağlantıyı kes ───────────────────────────────────────────────────────────
  const disconnect = useCallback(() => {
    if (clientRef.current) {
      try { clientRef.current.disconnect() } catch { /* boş */ }
      clientRef.current = null
    }
    if (keyboardRef.current) {
      try { keyboardRef.current.reset() } catch { /* boş */ }
      keyboardRef.current = null
    }
    if (displayContainerRef.current) {
      displayContainerRef.current.innerHTML = ''
    }
    reset()
    setActiveConn(null)
    setRemoteClip('')
  }, [])

  const newConnection = () => {
    disconnect()
    setForm({ host: '', port: '3389', username: '', password: '', domain: '', security: 'any' })
    setClipInput('')
    setIsFullscreen(false)
  }

  // ── Pano: açık "Panoyu gönder" yolu (insecure context'te de çalışır) ───────
  const sendClipboardText = (text) => {
    const client = clientRef.current
    if (!client || !text) return
    const stream = client.createClipboardStream('text/plain')
    const writer = new Guacamole.StringWriter(stream)
    writer.sendText(text)
    writer.sendEnd()
    toast.success('Metin uzak panoya gönderildi')
  }

  const readLocalAndSend = async () => {
    try {
      const t = await navigator.clipboard.readText()
      if (t) { setClipInput(t); sendClipboardText(t) }
    } catch {
      toast.error('Tarayıcı yerel panoya erişemedi — metni alana yapıştırıp gönderin')
    }
  }

  const copyRemoteToLocal = async () => {
    try {
      await navigator.clipboard.writeText(remoteClip)
      toast.success('Yerel panoya kopyalandı')
    } catch {
      // insecure context fallback: seçilebilir alan üzerinden kopyala
      const ta = document.createElement('textarea')
      ta.value = remoteClip
      document.body.appendChild(ta)
      ta.select()
      try {
        document.execCommand('copy')
        toast.success('Yerel panoya kopyalandı')
      } catch {
        toast.error('Kopyalanamadı — metni kutudan elle seçin')
      }
      ta.remove()
    }
  }

  const showForm = !isConnected && !isConnecting

  // Form her göründüğünde guacd'ı yeniden kontrol et (keepAlive: bileşen
  // mount kalır, yalnızca mount'ta kontrol etmek bayat rozet bırakır)
  useEffect(() => {
    if (showForm) checkGuacd()
  }, [showForm, checkGuacd])

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ── Sayfa başlığı ──────────────────────────────────────────────────────── */}
      <ConnectionHeader
        icon={<Monitor className="w-4 h-4" style={{ color: '#d4a8ff' }} />}
        iconBg="linear-gradient(135deg,rgba(212,168,255,.2) 0%,rgba(168,85,247,.15) 100%)"
        title="RDP Uzak Masaüstü"
        subtitle={isConnected
          ? `${activeConn?.username}@${activeConn?.host}:${activeConn?.port} — aktif oturum`
          : 'Windows sunucularına tarayıcı üzerinden uzak masaüstü bağlantısı açın.'}
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

            {/* Satır 1: Host + Port */}
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

            {/* Satır 2: Kullanıcı adı + Şifre */}
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

            {/* Satır 3: Domain + Güvenlik modu */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              <div>
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
              <div>
                <label className="text-label-sm mb-1.5 block" style={{ color: '#6b7388' }}>
                  Güvenlik Modu
                </label>
                <select
                  className="input-field w-full"
                  value={form.security}
                  onChange={e => setForm(f => ({ ...f, security: e.target.value }))}
                  title="Bağlantı kurulamıyorsa önce NLA'yı, eski sunucularda RDP'yi deneyin"
                >
                  {SECURITY_MODES.map(m => (
                    <option key={m.id} value={m.id}>{m.label}</option>
                  ))}
                </select>
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

            <div className="flex items-center gap-3">
              <button
                onClick={() => connect()}
                disabled={!form.host?.trim() || !form.username?.trim()}
                className="btn-primary flex items-center gap-2"
              >
                <Plug className="w-4 h-4" />
                Bağlan
              </button>

              {/* guacd canlı durum rozeti */}
              <div className="flex items-center gap-1.5 text-label-sm">
                {guacd === null && (
                  <span className="flex items-center gap-1.5" style={{ color: '#9da5be' }}>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" /> guacd kontrol ediliyor…
                  </span>
                )}
                {guacd?.running === true && (
                  <span className="flex items-center gap-1.5" style={{ color: '#4a6cf7' }}>
                    <CheckCircle2 className="w-3.5 h-3.5" /> guacd çalışıyor ({guacd.address})
                  </span>
                )}
                {guacd?.running === false && (
                  <span className="flex items-center gap-1.5" style={{ color: '#ffb4ab' }}>
                    <XCircle className="w-3.5 h-3.5" /> guacd ÇALIŞMIYOR — bağlantı kurulamaz
                    <button onClick={checkGuacd} className="underline hover:opacity-70" style={{ color: '#3b7eff' }}>
                      yeniden dene
                    </button>
                  </span>
                )}
              </div>
            </div>

            {/* guacd kurulum ipucu — çalışmıyorsa vurgulu */}
            <div
              className="mt-4 px-3 py-2.5 rounded-btn text-label-sm"
              style={guacd?.running === false
                ? { background: 'rgba(255,180,171,0.08)', color: '#c14953', border: '1px solid rgba(255,180,171,0.2)' }
                : { background: 'rgba(59,127,255,0.05)', color: '#6b7388', border: '1px solid rgba(59,127,255,0.09)' }}
            >
              <span style={{ color: guacd?.running === false ? '#c14953' : '#3b7eff' }}>
                {guacd?.running === false ? 'guacd başlatın:' : 'guacd kurulum:'}
              </span>
              {'  '}
              <code style={{ color: '#6b7388', background: 'rgba(0,6,30,0.04)', padding: '1px 6px', borderRadius: 4 }}>
                docker run -d --restart unless-stopped -p 4822:4822 guacamole/guacd
              </code>
            </div>
          </div>

          {/* Kayıtlı bağlantılar */}
          <SavedConnectionsList
            items={saved.items}
            icon={<Monitor className="w-3.5 h-3.5" style={{ color: '#d4a8ff' }} />}
            iconBg="rgba(212,168,255,0.08)"
            subtitle={(c) => `port ${c.port}${c.domain ? ` · ${c.domain}` : ''}`}
            onSelect={(c) => setForm({ host: c.host, port: c.port, username: c.username, password: '', domain: c.domain || '' })}
            onRemove={saved.remove}
          />
        </div>
      )}

      {/* ── Bağlanıyor bandı ─────────────────────────────────────────────────── */}
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

      {/* ── RDP penceresi ────────────────────────────────────────────────────── */}
      <RemoteWindowFrame
        tabIcon={<Monitor className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#d4a8ff' }} />}
        tabLabel={isConnected || isConnecting
          ? `${activeConn?.username || form.username}@${activeConn?.host || form.host}:${activeConn?.port || form.port}`
          : 'rdp'}
        isFullscreen={isFullscreen}
        isConnected={isConnected}
        isConnecting={isConnecting}
        onToggleFullscreen={toggleFullscreen}
        onDisconnect={disconnect}
      >
        {/* ── Pano çubuğu (Aşama 8) ── */}
        {isConnected && (
          <div
            className="flex items-center gap-2 px-3 py-2 flex-shrink-0 flex-wrap"
            style={{ background: '#16181d', borderBottom: '1px solid rgba(66,71,84,0.4)' }}
          >
            <ClipboardPaste className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#d4a8ff' }} />
            <input
              type="text"
              value={clipInput}
              onChange={e => setClipInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendClipboardText(clipInput)}
              placeholder="Uzak panoya gönderilecek metin…"
              className="flex-1 min-w-40 bg-transparent outline-none text-body-sm font-mono rounded px-2 py-1"
              style={{ color: '#e8eaf4', background: 'rgba(255,255,255,0.05)', caretColor: '#d4a8ff' }}
            />
            <button
              onClick={() => sendClipboardText(clipInput)}
              disabled={!clipInput}
              className="text-label-sm px-2.5 py-1.5 rounded-btn font-medium disabled:opacity-40"
              style={{ background: 'rgba(212,168,255,0.15)', color: '#d4a8ff' }}
            >
              Panoyu gönder
            </button>
            {window.isSecureContext ? (
              <button
                onClick={readLocalAndSend}
                className="text-label-sm px-2.5 py-1.5 rounded-btn"
                style={{ background: 'rgba(255,255,255,0.06)', color: '#c9cdd6' }}
                title="Yerel panodaki metni okuyup uzak oturuma gönderir"
              >
                Yerel panodan oku & gönder
              </button>
            ) : (
              <span
                className="text-label-sm flex items-center gap-1"
                style={{ color: '#9da5be' }}
                title="navigator.clipboard yalnızca HTTPS veya localhost'ta çalışır — LAN IP'sinden açıldığında tarayıcı yerel panoyu doğrudan okuyamaz; metni bu alanla taşıyın (canvas'a Ctrl+V de çalışır)"
              >
                <Info className="w-3 h-3" />
                LAN erişimi: pano bu alanla taşınır
              </span>
            )}
            {remoteClip && (
              <span className="flex items-center gap-1.5 min-w-0" style={{ maxWidth: 340 }}>
                <span className="text-label-sm flex-shrink-0" style={{ color: '#9da5be' }}>Uzaktan:</span>
                <span className="text-label-sm font-mono truncate" style={{ color: '#c9cdd6' }} title={remoteClip}>
                  {remoteClip}
                </span>
                <button
                  onClick={copyRemoteToLocal}
                  className="p-1 rounded hover:opacity-70 flex-shrink-0"
                  style={{ color: '#d4a8ff' }}
                  title="Uzaktan kopyalanan metni yerel panoya al"
                >
                  <ClipboardCopy className="w-3.5 h-3.5" />
                </button>
              </span>
            )}
          </div>
        )}

        {/* ── Görüntü alanı ── */}
        <div
          className="flex-1 min-h-0 overflow-hidden flex items-center justify-center"
          style={{ background: '#0d0f13' }}
        >
          {/* Guacamole canvas'ı buraya imperatif olarak bağlanır.
              data-remote-session: odak buradayken Ctrl+K uzağa gitsin (App.jsx) */}
          <div
            ref={displayContainerRef}
            data-remote-session="rdp"
            style={{ width: '100%', height: '100%', overflow: 'hidden', position: 'relative' }}
          />

          {/* Boşta yer tutucu */}
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
      </RemoteWindowFrame>
    </div>
  )
}
