import { useState } from 'react'
import { ArrowLeft, Ticket } from 'lucide-react'
import toast from 'react-hot-toast'
import { ticketsApi } from '../api/client'

const CATEGORIES = [
  'Domain / DNS',
  'SSL Sertifika',
  'E-posta',
  'Hosting / Sunucu',
  'Panel Erişimi',
  'Yedekleme / Restore',
  'Performans',
  'Güvenlik',
  'Fatura / Hesap',
  'Diğer',
]

export default function NewTicketForm({ onBack, onCreated }) {
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    customer_name: '',
    customer_email: '',
    domain: '',
    server_ip: '',
    subject: '',
    description: '',
    priority: 'medium',
    category: '',
  })

  const set = (field) => (e) => setForm(prev => ({ ...prev, [field]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.customer_name || !form.customer_email || !form.subject || !form.description) {
      toast.error('Zorunlu alanları doldurun')
      return
    }

    setLoading(true)
    try {
      const payload = {
        ...form,
        domain: form.domain || undefined,
        server_ip: form.server_ip || undefined,
        category: form.category || undefined,
      }
      const res = await ticketsApi.create(payload)
      toast.success(`Talep oluşturuldu: ${res.data.ticket_no}`)
      onCreated(res.data)
    } catch (err) {
      toast.error('Talep oluşturulamadı')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      <div className="px-8 pt-8 pb-5">
        <button onClick={onBack} className="btn-ghost mb-5 -ml-1">
          <ArrowLeft className="w-4 h-4" />
          Geri
        </button>

        <div className="flex items-center gap-3 mb-1">
          <div
            className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: 'rgba(173, 198, 255, 0.1)' }}
          >
            <Ticket className="w-4 h-4" style={{ color: '#3b7eff' }} />
          </div>
          <h1
            className="text-headline-md font-semibold"
            style={{ color: '#1a1d2e', letterSpacing: '-0.01em' }}
          >
            Yeni Talep
          </h1>
        </div>
        <p className="text-body-md" style={{ color: '#6b7388' }}>
          Müşteri bilgilerini ve talep detaylarını girin
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-8 px-8 pb-10 max-w-3xl">
        {/* Customer info */}
        <section>
          <h2 className="text-title-md font-medium mb-4" style={{ color: '#1a1d2e' }}>
            Müşteri Bilgileri
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Ad Soyad *">
              <input
                className="input-field"
                placeholder="Müşteri adı"
                value={form.customer_name}
                onChange={set('customer_name')}
              />
            </Field>
            <Field label="E-posta *">
              <input
                type="email"
                className="input-field"
                placeholder="musteri@example.com"
                value={form.customer_email}
                onChange={set('customer_email')}
              />
            </Field>
          </div>
        </section>

        {/* Technical info */}
        <section>
          <h2 className="text-title-md font-medium mb-4" style={{ color: '#1a1d2e' }}>
            Teknik Bilgiler
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Domain" hint="Opsiyonel">
              <input
                className="input-field font-mono"
                placeholder="example.com"
                value={form.domain}
                onChange={set('domain')}
              />
            </Field>
            <Field label="Sunucu IP" hint="Opsiyonel">
              <input
                className="input-field font-mono"
                placeholder="192.168.1.1"
                value={form.server_ip}
                onChange={set('server_ip')}
              />
            </Field>
          </div>
        </section>

        {/* Ticket details */}
        <section>
          <h2 className="text-title-md font-medium mb-4" style={{ color: '#1a1d2e' }}>
            Talep Detayları
          </h2>
          <div className="flex flex-col gap-3">
            <Field label="Konu *">
              <input
                className="input-field"
                placeholder="Kısa ve açıklayıcı konu başlığı"
                value={form.subject}
                onChange={set('subject')}
              />
            </Field>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Kategori">
                <select
                  className="input-field"
                  style={{ background: '#eaedf5', cursor: 'pointer' }}
                  value={form.category}
                  onChange={set('category')}
                >
                  <option value="">Seçin...</option>
                  {CATEGORIES.map(c => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </Field>

              <Field label="Öncelik">
                <select
                  className="input-field"
                  style={{ background: '#eaedf5', cursor: 'pointer' }}
                  value={form.priority}
                  onChange={set('priority')}
                >
                  <option value="low">Düşük</option>
                  <option value="medium">Orta</option>
                  <option value="high">Yüksek</option>
                  <option value="critical">Kritik</option>
                </select>
              </Field>
            </div>

            <Field label="Açıklama *">
              <textarea
                className="textarea-field"
                placeholder="Müşterinin yaşadığı sorunu detaylıca açıklayın..."
                rows={6}
                value={form.description}
                onChange={set('description')}
              />
            </Field>
          </div>
        </section>

        {/* Actions */}
        <div className="flex gap-3">
          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? <><span className="spinner" /> Oluşturuluyor...</> : 'Talep Oluştur'}
          </button>
          <button type="button" onClick={onBack} className="btn-secondary">
            İptal
          </button>
        </div>
      </form>
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <label className="text-label-md font-medium" style={{ color: '#4a5068' }}>
          {label}
        </label>
        {hint && (
          <span className="text-label-sm" style={{ color: '#9da5be' }}>{hint}</span>
        )}
      </div>
      {children}
    </div>
  )
}
