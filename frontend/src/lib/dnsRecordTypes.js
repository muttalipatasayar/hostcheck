import {
  Globe, Mail, Server, FileText, Shield, Info, ChevronRight, RefreshCw,
} from 'lucide-react'

// DNS kayıt tipleri — DNSToolbox ve komut paleti buradan okur.
// (lib katmanında: palet, ağır bileşenleri bundle'a çekmeden listeleyebilsin)
export const RECORD_TYPES = [
  { id: 'A',      label: 'A',      desc: 'IPv4 Adresi',              icon: Globe,        color: '#4a6cf7' },
  { id: 'AAAA',   label: 'AAAA',   desc: 'IPv6 Adresi',              icon: Globe,        color: '#4a6cf7' },
  { id: 'CNAME',  label: 'CNAME',  desc: 'Alias / Takma Ad',         icon: ChevronRight, color: '#3b7eff' },
  { id: 'MX',     label: 'MX',     desc: 'Mail Sunucusu',            icon: Mail,         color: '#c3b1e1' },
  { id: 'NS',     label: 'NS',     desc: 'Ad Sunucusu',              icon: Server,       color: '#3b7eff' },
  { id: 'TXT',    label: 'TXT',    desc: 'Metin Kaydı',              icon: FileText,     color: '#6b7388' },
  { id: 'SOA',    label: 'SOA',    desc: 'Otorite Başlangıcı',       icon: Info,         color: '#6b7388' },
  { id: 'PTR',    label: 'PTR',    desc: 'Ters DNS (IP girin)',      icon: RefreshCw,    color: '#6b7388' },
  { id: 'SPF',    label: 'SPF',    desc: 'Gönderici Politikası',     icon: Shield,       color: '#b1f9c2' },
  { id: 'DMARC',  label: 'DMARC',  desc: 'E-posta Kimlik Doğrulama', icon: Shield,       color: '#ffb786' },
  { id: 'DKIM',   label: 'DKIM',   desc: 'E-posta İmzası',           icon: Shield,       color: '#f9d4b1' },
  { id: 'DNSSEC', label: 'DNSSEC', desc: 'Zone İmza Doğrulama',      icon: Shield,       color: '#b1f9e0' },
]

export const TYPE_MAP = Object.fromEntries(RECORD_TYPES.map(t => [t.id, t]))
