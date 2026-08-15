// Sayfanın servis edildiği host üzerinden WebSocket URL'i üretir (dev'de Vite
// proxy, prod'da aynı origin). Sabit localhost yazmak, paneli başka bir
// makineden açan kullanıcıda bağlantıyı koparıyordu.
export function wsUrl(path) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}${path}`
}
