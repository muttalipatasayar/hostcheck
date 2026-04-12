import { useState, useEffect, useCallback } from 'react'
import { Toaster } from 'react-hot-toast'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import QuickCheck from './components/QuickCheck'
import SSLTools from './components/SSLTools'
import DNSToolbox from './components/DNSToolbox'
import DNSHistory from './components/DNSHistory'
import TicketList from './components/TicketList'
import TicketDetail from './components/TicketDetail'
import NewTicketForm from './components/NewTicketForm'
import { ticketsApi } from './api/client'

export default function App() {
  const [view, setView] = useState('dashboard')
  const [selectedTicketId, setSelectedTicketId] = useState(null)
  const [tickets, setTickets] = useState([])
  const [loadingTickets, setLoadingTickets] = useState(true)

  const loadTickets = useCallback(async () => {
    try {
      const res = await ticketsApi.list()
      setTickets(res.data)
    } catch (err) {
      console.error('Talepler yüklenemedi:', err)
    } finally {
      setLoadingTickets(false)
    }
  }, [])

  useEffect(() => {
    loadTickets()
    // Poll every 30s for updates
    const interval = setInterval(loadTickets, 30000)
    return () => clearInterval(interval)
  }, [loadTickets])

  const navigate = (destination, id) => {
    if (destination === 'ticket-detail' && id) {
      setSelectedTicketId(id)
      setView('ticket-detail')
    } else {
      setView(destination)
      setSelectedTicketId(null)
    }
  }

  const handleTicketCreated = (ticket) => {
    setTickets(prev => [ticket, ...prev])
    setSelectedTicketId(ticket.id)
    setView('ticket-detail')
  }

  const handleTicketUpdated = (updatedTicket) => {
    setTickets(prev =>
      prev.map(t => t.id === updatedTicket.id ? updatedTicket : t)
    )
  }

  const renderContent = () => {
    switch (view) {
      case 'dashboard':
        return (
          <Dashboard
            tickets={tickets}
            onNavigate={navigate}
          />
        )

      case 'quick-check':
        return <QuickCheck />

      case 'ssl-tools':
        return <SSLTools />

      case 'dns-toolbox':
        return <DNSToolbox />

      case 'dns-history':
        return <DNSHistory />

      case 'tickets':
        return (
          <TicketList
            tickets={tickets}
            loading={loadingTickets}
            onSelect={(id) => navigate('ticket-detail', id)}
            onNewTicket={() => setView('new-ticket')}
          />
        )

      case 'new-ticket':
        return (
          <NewTicketForm
            onBack={() => setView('tickets')}
            onCreated={handleTicketCreated}
          />
        )

      case 'ticket-detail':
        return (
          <TicketDetail
            ticketId={selectedTicketId}
            onBack={() => setView('tickets')}
            onTicketUpdated={handleTicketUpdated}
          />
        )

      default:
        return null
    }
  }

  // Sidebar'daki "Talepler" view'unu maplemek için
  const sidebarView = view === 'ticket-detail' ? 'tickets' : view

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#111317' }}>
      {/* Sidebar — surface-container-low, no border */}
      <Sidebar
        activeView={sidebarView === 'new-ticket' ? 'new-ticket' : sidebarView}
        onNavigate={navigate}
        ticketCount={tickets.filter(t => t.status === 'open').length}
      />

      {/* Main content area — surface background */}
      <main
        className="flex-1 overflow-y-auto"
        style={{ background: '#111317' }}
      >
        <div className="h-full animate-fade-in" key={view}>
          {renderContent()}
        </div>
      </main>

      {/* Toast notifications */}
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
          success: {
            iconTheme: {
              primary: '#b1c6f9',
              secondary: '#002e6a',
            },
          },
          error: {
            iconTheme: {
              primary: '#ffb4ab',
              secondary: '#410002',
            },
          },
          duration: 3000,
        }}
      />
    </div>
  )
}
