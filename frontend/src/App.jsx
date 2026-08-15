import { useState } from 'react'
import { Toaster } from 'react-hot-toast'
import Sidebar from './components/Sidebar'
import TargetBar from './components/shell/TargetBar'
import QuickCheck from './components/QuickCheck'
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
import CommandPalette from './components/shell/CommandPalette'
import { TargetProvider, useTarget } from './context/TargetContext'
import { HotkeyProvider, useHotkeys } from './hooks/useHotkeys'
import { getTool } from './lib/tools'

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
  const [view, setView] = useState('quick-check')
  const [visitedKeepAlive, setVisitedKeepAlive] = useState(() => new Set())
  const [paletteOpen, setPaletteOpen] = useState(false)
  const { setPendingIntent } = useTarget()

  const navigate = (destination) => {
    if (getTool(destination)?.keepAlive) {
      setVisitedKeepAlive(prev => prev.has(destination) ? prev : new Set(prev).add(destination))
    }
    setView(destination)
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
      case 'quick-check':    return <QuickCheck />
      case 'ssl-tools':      return <SSLTools />
      case 'dns-toolbox':    return <DNSToolbox />
      case 'dns-history':    return <DNSHistory />
      case 'dns-propagation': return <DNSPropagation />
      case 'blacklist':      return <Blacklist />
      case 'mail-health':    return <MailHealth />
      case 'ip-lookup':      return <IPLookup />
      case 'hazir-yanitlar': return <HazirYanitlar />
      default:               return <QuickCheck />
    }
  }

  const isKeepAliveView = view in KEEP_ALIVE_COMPONENTS

  return (
    <>
      <div className="flex h-screen overflow-hidden" style={{ background: '#f0f2f7' }}>
        <div style={{ borderRight: '1px solid rgba(0,6,30,0.09)', flexShrink: 0 }}>
          <Sidebar activeView={view} onNavigate={navigate} />
        </div>

        <main className="flex-1 flex flex-col overflow-hidden" style={{ background: '#f0f2f7' }}>
          <TargetBar view={view} />

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
    </>
  )
}

export default function App() {
  return (
    <TargetProvider>
      <HotkeyProvider>
        <AppShell />
      </HotkeyProvider>
    </TargetProvider>
  )
}
