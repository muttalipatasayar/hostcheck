import { Zap, Shield, Wrench, History, Terminal, Monitor, Globe, MessageSquare, Radar, ShieldAlert, Mail, FolderOpen } from 'lucide-react'

// Araç kataloğu — Sidebar, TargetBar ve (Aşama 2'de) komut paleti buradan okur.
//
// target : 'domain' → çubuktaki hedefi sorgu girdisi olarak kullanır
//          'host'   → hedefi bağlantı formuna TEK YÖNLÜ ön-doldurur, geri yazmaz
//          'none'   → paylaşılan hedefi kullanmaz (yerel filtre vb.)
// autoRun: true  → ucuz/idempotent; sekmeye gelindiğinde commit edilmiş hedefle
//                  kendiliğinden çalışabilir
//          false → pahalı (rate limit, dış API kotası, SMTP el sıkışması);
//                  yalnızca açık Enter/Çalıştır ile çalışır
// keepAlive: true → ilk ziyaretten sonra ağaçta kalır (display:none) —
//                   canlı oturum sekme değişiminde kopmaz
export const TOOLS = [
  { id: 'quick-check',    label: 'Hızlı Kontrol',  icon: Zap,           target: 'domain', autoRun: false, keepAlive: false },
  { id: 'ssl-tools',      label: 'SSL Araçları',   icon: Shield,        target: 'domain', autoRun: false, keepAlive: false },
  { id: 'dns-toolbox',    label: 'DNS Toolbox',    icon: Wrench,        target: 'domain', autoRun: true,  keepAlive: false },
  { id: 'dns-history',    label: 'DNS History',    icon: History,       target: 'domain', autoRun: false, keepAlive: false },
  { id: 'dns-propagation', label: 'DNS Yayılma',   icon: Radar,         target: 'domain', autoRun: true,  keepAlive: false },
  { id: 'blacklist',      label: 'Blacklist / RBL', icon: ShieldAlert,  target: 'domain', autoRun: true,  keepAlive: false },
  { id: 'mail-health',    label: 'Mail Sağlığı',   icon: Mail,          target: 'domain', autoRun: false, keepAlive: false },
  { id: 'ssh-access',     label: 'SSH Erişimi',    icon: Terminal,      target: 'host',   autoRun: false, keepAlive: true  },
  { id: 'rdp-access',     label: 'RDP Erişimi',    icon: Monitor,       target: 'host',   autoRun: false, keepAlive: true  },
  { id: 'ftp',            label: 'FTP Dosyaları',  icon: FolderOpen,    target: 'host',   autoRun: false, keepAlive: true  },
  { id: 'ip-lookup',      label: 'IP Sorgulama',   icon: Globe,         target: 'domain', autoRun: true,  keepAlive: false },
  { id: 'hazir-yanitlar', label: 'Hazır Yanıtlar', icon: MessageSquare, target: 'none',   autoRun: false, keepAlive: false },
]

export function getTool(id) {
  return TOOLS.find(t => t.id === id)
}
