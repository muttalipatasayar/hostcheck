import { TOOLS } from './tools'
import { RECORD_TYPES } from './dnsRecordTypes'
import { SSL_TABS } from './sslTabs'

// Komut paleti kataloğu. Her komut { id, label, hint, icon, view, payload }:
// palet `view`e gider ve `payload`ı pendingIntent olarak bırakır; hedef araç
// mount'ta okuyup tüketir.
export const COMMANDS = [
  ...TOOLS.map(t => ({
    id: `git-${t.id}`,
    label: `${t.label} aracına git`,
    hint: 'Araç',
    icon: t.icon,
    view: t.id,
    payload: null,
  })),
  ...RECORD_TYPES.map(r => ({
    id: `dns-${r.id}`,
    label: `${r.id} kaydı sorgula`,
    hint: r.desc,
    icon: r.icon,
    view: 'dns-toolbox',
    payload: { recordType: r.id },
  })),
  ...SSL_TABS.map(tab => ({
    id: `ssl-${tab.id}`,
    label: tab.label,
    hint: 'SSL Araçları',
    icon: tab.icon,
    view: 'ssl-tools',
    payload: { tab: tab.id },
  })),
]
