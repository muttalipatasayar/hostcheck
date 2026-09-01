import { useState } from 'react'
import { Printer, Copy, Check, X, FileText } from 'lucide-react'
import toast from 'react-hot-toast'

// Müşteriye gidecek çıktı.
//
// Panelin varlık sebebi müşteri sitesini teşhis edip MÜŞTERİYE ANLATMAK'tı,
// ama bulgular 13 sekmeye dağılmış hâlde kalıyordu; teknisyen elle kopyalıyordu.
// Bu bileşen aynı veriden iki çıktı üretir:
//   • yazdırılabilir/PDF sayfa (tarayıcının kendi yazdır işlevi — yeni bağımlılık yok)
//   • panoya kopyalanabilir düz Türkçe metin (destek talebine yapıştırmak için)

const DURUM_METIN = {
  healthy: 'Sorun yok',
  warning: 'İyileştirilmeli',
  error:   'Sorunlu',
  info:    'Bilgi',
}
const DURUM_ISARET = { healthy: '●', warning: '■', error: '▲', info: '·' }
const DURUM_RENK = { healthy: '#0CCE6B', warning: '#FFA400', error: '#FF4E42', info: '#6b7388' }

// Teknik bulguyu müşterinin anlayacağı cümleye çevirir. Teknisyenin ekranında
// gördüğü metin ile müşteriye giden metin BİLEREK farklı: "NS kayıtları
// uyumsuz" teknisyen için bilgi, müşteri için anlamsızdır.
const MUSTERI_CEVIRI = {
  'alan-adi': {
    error:   'Alan adınızın süresi dolmuş veya dolmak üzere. Yenilenmezse siteniz ve e-postalarınız erişilemez hâle gelir.',
    warning: 'Alan adınızın yenilenme tarihi yaklaşıyor. Kesinti yaşamamak için yenilemenizi öneririz.',
  },
  ssl: {
    error:   'Güvenlik sertifikanız geçersiz veya süresi dolmuş. Ziyaretçiler tarayıcıda güvenlik uyarısı görüyor.',
    warning: 'Güvenlik sertifikanızın süresi yaklaşıyor. Yenileme işlemi planlanmalı.',
  },
  dns: {
    error:   'Alan adı yönlendirme ayarlarınızda (DNS) bir sorun var; site adresine ulaşımı etkiliyor.',
    warning: 'Alan adı yönlendirme ayarlarınızda iyileştirilebilecek noktalar var.',
  },
  http: {
    error:   'Sitenize şu anda erişilemiyor. Teknik ekibimiz konuyu incelemektedir.',
    warning: 'Siteniz yanıt veriyor ancak beklenmeyen bir durum kodu döndürüyor.',
  },
  eposta: {
    error:   'E-posta doğrulama kayıtlarınızda bir hata var; gönderdiğiniz e-postalar spam klasörüne düşebilir.',
    warning: 'E-posta doğrulama kayıtlarınız eksik. Bu, e-postalarınızın spam olarak işaretlenme riskini artırır.',
  },
  blacklist: {
    error:   'Sunucu adresiniz bazı e-posta kara listelerinde görünüyor; bu, e-posta teslimatını engelliyor.',
    warning: 'Sunucu adresiniz için itibar uyarısı bulunuyor.',
  },
}

function musteriMetni(veri) {
  const t = new Date().toLocaleDateString('tr-TR', { day: '2-digit', month: 'long', year: 'numeric' })
  const sorunlu = veri.kartlar.filter(k => k.durum === 'error' || k.durum === 'warning')
  const saglikli = veri.kartlar.filter(k => k.durum === 'healthy')

  const satirlar = [
    `${veri.domain} — Teknik Kontrol Raporu (${t})`,
    '',
  ]

  if (sorunlu.length === 0) {
    satirlar.push(
      'Sitenizde yaptığımız kontrollerde bir sorun tespit edilmemiştir.',
      '',
      'Kontrol edilen başlıklar:',
      ...saglikli.map(k => `  • ${k.baslik}: sorun yok`),
    )
  } else {
    satirlar.push('Sitenizde yaptığımız kontrollerde aşağıdaki bulgular tespit edilmiştir:', '')
    sorunlu.forEach((k, i) => {
      const ceviri = MUSTERI_CEVIRI[k.id]?.[k.durum]
      satirlar.push(`${i + 1}. ${k.baslik}${k.deger ? ` (${k.deger})` : ''}`)
      if (ceviri) satirlar.push(`   ${ceviri}`)
      satirlar.push('')
    })
    if (saglikli.length) {
      satirlar.push('Sorun tespit edilmeyen başlıklar:',
        '  ' + saglikli.map(k => k.baslik).join(', '), '')
    }
  }

  satirlar.push(
    'Konuyla ilgili sorularınız için destek ekibimize yazabilirsiniz.',
    '',
    '—',
    `Bu rapor ${t} tarihinde otomatik kontrol araçlarıyla oluşturulmuştur.`,
  )
  return satirlar.join('\n')
}

export default function MusteriRaporu({ veri, hiz, onKapat }) {
  const [kopyalandi, setKopyalandi] = useState(false)
  if (!veri) return null

  const tarih = new Date().toLocaleString('tr-TR')
  const metin = musteriMetni(veri)

  const kopyala = async () => {
    try {
      await navigator.clipboard.writeText(metin)
      setKopyalandi(true)
      toast.success('Müşteri metni kopyalandı')
      setTimeout(() => setKopyalandi(false), 2000)
    } catch {
      toast.error('Panoya erişilemedi — metni elle seçip kopyalayın')
    }
  }

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto rapor-katman"
         style={{ background: 'rgba(0,6,30,0.45)' }}>
      <div className="min-h-full flex items-start justify-center p-4 sm:p-8">
        <div className="w-full rapor-sayfa" style={{ maxWidth: 860, background: '#ffffff', borderRadius: 12 }}>

          {/* Araç çubuğu — yazdırmada gizlenir */}
          <div className="flex items-center justify-between px-6 py-3 yazdirma-gizle"
               style={{ borderBottom: '1px solid rgba(0,6,30,0.08)' }}>
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4" style={{ color: '#3b7eff' }} />
              <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>Müşteri Raporu</p>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={kopyala} className="btn-ghost text-label-md">
                {kopyalandi ? <><Check className="w-3.5 h-3.5" style={{ color: '#0CCE6B' }} /> Kopyalandı</>
                            : <><Copy className="w-3.5 h-3.5" /> Müşteri metnini kopyala</>}
              </button>
              <button onClick={() => window.print()} className="btn-primary text-label-md py-1.5 px-3">
                <Printer className="w-3.5 h-3.5" /> Yazdır / PDF
              </button>
              <button onClick={onKapat} aria-label="Raporu kapat" className="btn-ghost p-1.5">
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Rapor gövdesi */}
          <div className="px-8 py-7">
            <div className="flex items-start justify-between gap-4 mb-6"
                 style={{ borderBottom: '2px solid #1a1d2e', paddingBottom: 14 }}>
              <div>
                <h1 className="font-semibold" style={{ fontSize: 22, color: '#1a1d2e', letterSpacing: '-0.01em' }}>
                  Teknik Kontrol Raporu
                </h1>
                <p className="text-body-sm font-mono mt-1" style={{ color: '#3b7eff' }}>{veri.domain}</p>
              </div>
              <div className="text-right">
                <p className="text-label-md" style={{ color: '#6b7388' }}>{tarih}</p>
                <p className="text-label-sm mt-0.5" style={{ color: '#9da5be' }}>HostCheck Destek Paneli</p>
              </div>
            </div>

            <div className="mb-6 px-4 py-3 rounded-card"
                 style={{ background: `${DURUM_RENK[veri.genel_durum]}12`,
                          borderLeft: `3px solid ${DURUM_RENK[veri.genel_durum]}` }}>
              <p className="text-body-sm font-medium" style={{ color: '#1a1d2e' }}>
                <span style={{ color: DURUM_RENK[veri.genel_durum] }}>
                  {DURUM_ISARET[veri.genel_durum]}
                </span>{' '}
                {veri.ozet}
              </p>
            </div>

            <table className="w-full" style={{ borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(0,6,30,0.12)' }}>
                  <th className="text-left text-label-sm font-medium uppercase tracking-wider py-2"
                      style={{ color: '#9da5be' }}>Kontrol</th>
                  <th className="text-left text-label-sm font-medium uppercase tracking-wider py-2"
                      style={{ color: '#9da5be' }}>Durum</th>
                  <th className="text-left text-label-sm font-medium uppercase tracking-wider py-2"
                      style={{ color: '#9da5be' }}>Bulgu</th>
                </tr>
              </thead>
              <tbody>
                {veri.kartlar.map(k => (
                  <tr key={k.id} style={{ borderBottom: '1px solid rgba(0,6,30,0.06)' }}>
                    <td className="py-2.5 text-body-sm font-medium" style={{ color: '#1a1d2e', width: 150 }}>
                      {k.baslik}
                    </td>
                    <td className="py-2.5 text-body-sm" style={{ width: 140 }}>
                      <span style={{ color: DURUM_RENK[k.durum] }}>{DURUM_ISARET[k.durum]}</span>{' '}
                      <span style={{ color: DURUM_RENK[k.durum] }}>{DURUM_METIN[k.durum]}</span>
                    </td>
                    <td className="py-2.5 text-body-sm" style={{ color: '#4a5068' }}>
                      {k.deger}{k.detay ? <span style={{ color: '#6b7388' }}> — {k.detay}</span> : null}
                    </td>
                  </tr>
                ))}
                {hiz && (
                  <tr style={{ borderBottom: '1px solid rgba(0,6,30,0.06)' }}>
                    <td className="py-2.5 text-body-sm font-medium" style={{ color: '#1a1d2e' }}>Site Hızı</td>
                    <td className="py-2.5 text-body-sm">
                      <span style={{ color: DURUM_RENK[hiz.durum] }}>{DURUM_ISARET[hiz.durum]}</span>{' '}
                      <span style={{ color: DURUM_RENK[hiz.durum] }}>{DURUM_METIN[hiz.durum]}</span>
                    </td>
                    <td className="py-2.5 text-body-sm" style={{ color: '#4a5068' }}>
                      Mobil skor {hiz.skor}/100
                    </td>
                  </tr>
                )}
              </tbody>
            </table>

            {veri.alt_alan_mi && (
              <p className="text-label-sm mt-4" style={{ color: '#9da5be' }}>
                Not: Kayıt bilgileri ve e-posta politikası <strong>{veri.kayit_alan_adi}</strong> üzerinden;
                sertifika ve erişim kontrolleri <strong>{veri.domain}</strong> üzerinden yapılmıştır.
              </p>
            )}

            {/* Müşteriye gidecek metin — yazdırmada da görünür */}
            <div className="mt-7 pt-5" style={{ borderTop: '1px solid rgba(0,6,30,0.12)' }}>
              <p className="text-label-sm font-medium uppercase tracking-wider mb-2.5"
                 style={{ color: '#9da5be' }}>Müşteriye Gönderilecek Metin</p>
              <pre className="text-body-sm whitespace-pre-wrap"
                   style={{ color: '#4a5068', lineHeight: 1.7, fontFamily: 'inherit', margin: 0 }}>
{metin}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
