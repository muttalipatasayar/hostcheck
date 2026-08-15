import axios from 'axios'

// SSH/RDP/FTP araçları WebSocket kullanır; tarayıcı bir WS el sıkışması 401
// aldığında kimlik penceresi AÇMAZ. Bu yüzden bağlanmadan önce bu HTTP probe'u
// çağırırız: prod'da Nginx bu isteğe 401 döner → tarayıcı Basic Auth penceresi
// açar → kimlik önbelleğe alınır → sonraki WebSocket'ler Authorization taşır.
//
// Geliştirmede (auth yokken) 200 döner ve akış kesintisiz devam eder.
// 401'de tarayıcı kendi penceresini gösterdiği için burada ekstra UI yok.
export async function ensureAdminAccess() {
  try {
    await axios.get('/api/admin/ping', { withCredentials: true })
    return true
  } catch (err) {
    // 401 → kullanıcı Basic Auth penceresini iptal etti; bağlanma
    if (err?.response?.status === 401) return false
    // Diğer hatalar (ağ, 5xx) bağlanmayı engellemesin — asıl uç kendi
    // hatasını zaten gösterecek
    return true
  }
}
