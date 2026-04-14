import { useState } from 'react'
import { Toaster } from 'react-hot-toast'
import Sidebar from './components/Sidebar'
import QuickCheck from './components/QuickCheck'
import SSLTools from './components/SSLTools'
import DNSToolbox from './components/DNSToolbox'
import DNSHistory from './components/DNSHistory'
import SSHAccess from './components/SSHAccess'
import HazirYanitlar from './components/HazirYanitlar'
import RDPAccess from './components/RDPAccess'
import IPLookup from './components/IPLookup'

export default function App() {
  const [view, setView] = useState('quick-check')

  const navigate = (destination) => setView(destination)

  const renderContent = () => {
    switch (view) {
      case 'quick-check':    return <QuickCheck />
      case 'ssl-tools':      return <SSLTools />
      case 'dns-toolbox':    return <DNSToolbox />
      case 'dns-history':    return <DNSHistory />
      case 'ssh-access':     return <SSHAccess />
      case 'rdp-access':     return <RDPAccess />
      case 'ip-lookup':      return <IPLookup />
      case 'hazir-yanitlar': return <HazirYanitlar />
      default:               return <QuickCheck />
    }
  }

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#f0f2f7' }}>
      <div style={{ borderRight: '1px solid rgba(0,6,30,0.09)', flexShrink: 0 }}>
        <Sidebar activeView={view} onNavigate={navigate} />
      </div>

      <main className="flex-1 overflow-y-auto" style={{ background: '#f0f2f7' }}>
        <div className="h-full animate-fade-in" key={view}>
          {renderContent()}
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
  )
}
