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
      case 'hazir-yanitlar': return <HazirYanitlar />
      default:               return <QuickCheck />
    }
  }

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#111317' }}>
      <Sidebar activeView={view} onNavigate={navigate} />

      <main className="flex-1 overflow-y-auto" style={{ background: '#111317' }}>
        <div className="h-full animate-fade-in" key={view}>
          {renderContent()}
        </div>
      </main>

      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: '#282a2e',
            color: '#e3e5ef',
            border: '1px solid rgba(66,71,84,0.3)',
            borderRadius: '0.375rem',
            fontSize: '0.875rem',
          },
          success: { iconTheme: { primary: '#b1c6f9', secondary: '#002e6a' } },
          error:   { iconTheme: { primary: '#ffb4ab', secondary: '#410002' } },
          duration: 3000,
        }}
      />
    </div>
  )
}
