import { useEffect, useState } from 'react'
import { Menu } from 'lucide-react'
import { clsx } from 'clsx'
import toast, { Toaster } from 'react-hot-toast'
import Sidebar from './components/Sidebar'
import TargetBar from './components/shell/TargetBar'
import GenelBakis from './components/GenelBakis'
import QuickCheck from './components/QuickCheck'
import SiteSpeed from './components/SiteSpeed'
import SSLTools from './components/SSLTools'
import DNSToolbox from './components/DNSToolbox'
import DNSHistory from './components/DNSHistory'
import DNSPropagation from './components/DNSPropagation'
import Blacklist from './components/Blacklist'
import MailHealth from './components/MailHealth'
import SSHAccess from './components/SSHAccess'
import HazirYanitlar from './components/HazirYanitlar'
import RDPAccess from './components/RDPAccess'
import FTPManager from './components/FTPManager'
import IPLookup from './components/IPLookup'
import Yonetim from './components/Yonetim'
import CommandPalette from './components/shell/CommandPalette'
import GirisModal from './components/auth/GirisModal'
import ProfilModal from './components/auth/ProfilModal'
import { TargetProvider, useTarget } from './context/TargetContext'
import { AuthProvider, useAuth } from './context/AuthContext'
import { HotkeyProvider, useHotkeys } from './hooks/useHotkeys'
import { getTool } from './lib/tools'

// E-postadaki bağlantılar SPA'ya sorgu parametresiyle konuşur; panelde router
// yok, o yüzden açılışta bir kez okunup URL temizlenir.
//   /?dogrulama=ok|gecersiz|suresi-doldu   → doğrulama sonucunu bildirir
//   /?sifre-sifirla=<token>                → parola belirleme modalını açar
const DOGRULAMA_MESAJI = {
  ok: ['success', 'E-posta adresiniz doğrulandı. Artık giriş yapabilirsiniz.'],
  gecersiz: ['error', 'Doğrulama bağlantısı geçersiz. Yeni bir bağlantı isteyin.'],
  'suresi-doldu': ['error', 'Doğrulama bağlantısının süresi dolmuş. Yeni bir bağlantı isteyin.'],
}

// keepAlive araçlar: ilk ziyarette lazy mount edilir, sonra display:none ile
// ağaçta kalır — canlı SSH/RDP oturumu sekme değişiminde kopmaz. Herkesi
// mount tutmak yanlış olurdu: örn. HazirYanitlar mount'ta fetch yapıyor.
const KEEP_ALIVE_COMPONENTS = {
  'ssh-access': SSHAccess,
  'rdp-access': RDPAccess,
  'ftp': FTPManager,
}

// Odak bir uzak oturumun (xterm / Guacamole canvas) içindeyse Ctrl+K uzak
// makineye gitmeli — palet ancak Ctrl+Alt+K ile açılır.
function isRemoteSessionFocused(e) {
  const el = e.target instanceof Element ? e.target : null
  return !!el?.closest('.xterm, [data-remote-session]')
}

function AppShell() {
  // Açılış ekranı Genel Bakış: panel araç merkezliydi ve boş bir araçla
  // açılıyordu; destek çağrısı ise alan adı merkezlidir.
  const [view, setView] = useState('genel-bakis')
  const [visitedKeepAlive, setVisitedKeepAlive] = useState(() => new Set())
  const [paletteOpen, setPaletteOpen] = useState(false)
  // Mobil çekmece. Masaüstünde (lg+) kenar çubuğu her zaman açıktır ve bu
  // state hiç kullanılmaz; dar ekranda 240px'lik çubuk içeriği 150px'e
  // sıkıştırdığı için panel kullanılamaz hâle geliyordu.
  const [menuAcik, setMenuAcik] = useState(false)
  // authModal: null | { kip: 'giris'|'kayit'|'sifirla', token?: string }
  const [authModal, setAuthModal] = useState(null)
  const [profilAcik, setProfilAcik] = useState(false)
  const { setPendingIntent } = useTarget()
  const { girisli, admin } = useAuth()

  // E-posta bağlantılarının sonucu — bir kez okunur, sonra URL temizlenir ki
  // sayfa yenilendiğinde toast tekrar çıkmasın.
  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    const dogrulama = p.get('dogrulama')
    const sifirlama = p.get('sifre-sifirla')
    if (!dogrulama && !sifirlama) return

    if (dogrulama) {
      const [tur, mesaj] = DOGRULAMA_MESAJI[dogrulama] || DOGRULAMA_MESAJI.gecersiz
      toast[tur](mesaj, { duration: 6000 })
      if (dogrulama === 'ok') setAuthModal({ kip: 'giris' })
    }
    if (sifirlama) setAuthModal({ kip: 'sifirla', token: sifirlama })

    window.history.replaceState({}, '', window.location.pathname)
  }, [])

  // Oturum düşünce (çıkış, süre dolması, yöneticinin askıya alması) üyelik
  // gerektiren bir sekmede kalınmasın.
  useEffect(() => {
    if (!girisli && view === 'hazir-yanitlar') return   // kapı ekranı gösterir
    if (!admin && view === 'yonetim') setView('genel-bakis')
  }, [girisli, admin, view])

  const navigate = (destination) => {
    if (getTool(destination)?.keepAlive) {
      setVisitedKeepAlive(prev => prev.has(destination) ? prev : new Set(prev).add(destination))
    }
    setView(destination)
    setMenuAcik(false)     // mobilde seçim yapınca çekmece kapansın
  }

  // Kabuk kısayolları — yığının tabanı; modal/palet scope'ları üstüne biner
  useHotkeys({
    'ctrl+k': (e) => {
      if (isRemoteSessionFocused(e)) return false // tuş uzak oturuma gitsin
      setPaletteOpen(true)
    },
    'ctrl+alt+k': () => setPaletteOpen(true),
    '/': (e) => {
      // Bir girdi alanında yazarken '/' normal karakterdir
      if (['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return false
      if (isRemoteSessionFocused(e)) return false
      document.getElementById('target-bar-input')?.focus()
    },
  })

  const runCommand = (cmd) => {
    if (cmd.payload) setPendingIntent(cmd.view, cmd.payload)
    navigate(cmd.view)
  }

  const renderContent = () => {
    switch (view) {
      case 'genel-bakis':    return <GenelBakis onNavigate={navigate} />
      case 'quick-check':    return <QuickCheck />
      case 'site-speed':     return <SiteSpeed />
      case 'ssl-tools':      return <SSLTools />
      case 'dns-toolbox':    return <DNSToolbox />
      case 'dns-history':    return <DNSHistory />
      case 'dns-propagation': return <DNSPropagation />
      case 'blacklist':      return <Blacklist />
      case 'mail-health':    return <MailHealth />
      case 'ip-lookup':      return <IPLookup />
      case 'hazir-yanitlar': return (
        <HazirYanitlar
          onGiris={() => setAuthModal({ kip: 'giris' })}
          onKayit={() => setAuthModal({ kip: 'kayit' })}
        />
      )
      case 'yonetim':        return <Yonetim />
      default:               return <GenelBakis onNavigate={navigate} />
    }
  }

  const isKeepAliveView = view in KEEP_ALIVE_COMPONENTS

  return (
    <>
      <div className="flex h-screen overflow-hidden" style={{ background: '#f0f2f7' }}>
        {/* Mobil çekmece açıkken arka planı karart — dokununca kapanır */}
        {menuAcik && (
          <div
            className="lg:hidden fixed inset-0 z-30"
            style={{ background: 'rgba(0,6,30,0.35)' }}
            onClick={() => setMenuAcik(false)}
            aria-hidden="true"
          />
        )}

        <div
          className={clsx(
            'flex-shrink-0 z-40 transition-transform duration-200',
            'max-lg:fixed max-lg:inset-y-0 max-lg:left-0',
            menuAcik ? 'max-lg:translate-x-0' : 'max-lg:-translate-x-full',
          )}
          style={{ borderRight: '1px solid rgba(0,6,30,0.09)' }}
        >
          <Sidebar
            activeView={view}
            onNavigate={navigate}
            onKapat={() => setMenuAcik(false)}
            onGiris={() => setAuthModal({ kip: 'giris' })}
            onKayit={() => setAuthModal({ kip: 'kayit' })}
            onProfil={() => setProfilAcik(true)}
          />
        </div>

        <main className="flex-1 flex flex-col overflow-hidden min-w-0" style={{ background: '#f0f2f7' }}>
          <div className="flex items-center gap-2 min-w-0">
            <button
              onClick={() => setMenuAcik(true)}
              aria-label="Menüyü aç"
              className="lg:hidden flex-shrink-0 ml-3 p-2 rounded-btn"
              style={{ color: '#4a5068' }}
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="flex-1 min-w-0">
              <TargetBar view={view} />
            </div>
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto">
            {/* Koşullu render edilen araçlar — key yalnızca fade animasyonu için,
                keepAlive araçlar bu bloğun DIŞINDA yaşadığından unmount etmez */}
            {!isKeepAliveView && (
              <div className="h-full animate-fade-in" key={view}>
                {renderContent()}
              </div>
            )}

            {/* keepAlive araçlar: ziyaret edildiyse gizli de olsa mount kalır */}
            {[...visitedKeepAlive].map(id => {
              const Component = KEEP_ALIVE_COMPONENTS[id]
              return (
                <div
                  key={id}
                  className="h-full"
                  style={{ display: view === id ? undefined : 'none' }}
                >
                  <Component />
                </div>
              )
            })}
          </div>
        </main>

        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: '#ffffff',
              color: '#1a1d2e',
              border: '1px solid rgba(0,6,30,0.1)',
              borderRadius: '0.5rem',
              fontSize: '0.875rem',
              boxShadow: '0 4px 16px rgba(0,6,30,0.1)',
            },
            success: { iconTheme: { primary: '#16a34a', secondary: '#ffffff' } },
            error:   { iconTheme: { primary: '#dc2626', secondary: '#ffffff' } },
            duration: 3000,
          }}
        />
      </div>

      {paletteOpen && (
        <CommandPalette onRun={runCommand} onClose={() => setPaletteOpen(false)} />
      )}

      {authModal && (
        <GirisModal
          acilisKipi={authModal.kip}
          sifirlamaTokeni={authModal.token || ''}
          onKapat={() => setAuthModal(null)}
        />
      )}

      {profilAcik && <ProfilModal onKapat={() => setProfilAcik(false)} />}
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <TargetProvider>
        <HotkeyProvider>
          <AppShell />
        </HotkeyProvider>
      </TargetProvider>
    </AuthProvider>
  )
}
