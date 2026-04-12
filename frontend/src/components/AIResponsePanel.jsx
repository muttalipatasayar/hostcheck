import { useState, useRef, useEffect } from 'react'
import { Sparkles, Copy, Check, RefreshCw, ChevronDown } from 'lucide-react'
import toast from 'react-hot-toast'
import { aiApi } from '../api/client'

export default function AIResponsePanel({ ticket, onResponseSaved }) {
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [response, setResponse] = useState(ticket.ai_response || '')
  const [copied, setCopied] = useState(false)
  const [additionalContext, setAdditionalContext] = useState('')
  const [showContext, setShowContext] = useState(false)
  const responseRef = useRef(null)

  useEffect(() => {
    setResponse(ticket.ai_response || '')
  }, [ticket.ai_response])

  const generate = async () => {
    setLoading(true)
    setStreaming(true)
    setResponse('')

    try {
      // Try streaming first
      const eventSource = new EventSource(
        `/api/ai/generate-stream?ticket_id=${ticket.id}`
      )

      // Streaming doesn't work well with POST via EventSource natively,
      // so we fall back to regular generation
      eventSource.close()

      const res = await aiApi.generate({
        ticket_id: ticket.id,
        additional_context: additionalContext || undefined,
      })

      setResponse(res.data.response)
      onResponseSaved && onResponseSaved(res.data.response)
      toast.success('AI yanıtı üretildi')
    } catch (err) {
      const detail = err.response?.data?.detail || 'AI yanıtı üretilemedi'
      toast.error(detail)
      console.error(err)
    } finally {
      setLoading(false)
      setStreaming(false)
    }
  }

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(response)
      setCopied(true)
      toast.success('Kopyalandı')
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error('Kopyalanamadı')
    }
  }

  return (
    <div
      className="rounded-card overflow-hidden flex flex-col"
      style={{ background: '#1a1c20' }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 py-4"
        style={{ borderBottom: '1px solid rgba(66,71,84,0.2)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-7 h-7 rounded-btn flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, rgba(173,198,255,0.2) 0%, rgba(77,142,255,0.15) 100%)' }}
          >
            <Sparkles className="w-3.5 h-3.5" style={{ color: '#adc6ff' }} />
          </div>
          <div>
            <p className="text-body-sm font-medium" style={{ color: '#e3e5ef' }}>
              AI Yanıt Üretici
            </p>
            <p className="text-label-sm mt-0.5" style={{ color: '#8d9099' }}>
              claude-sonnet-4 · Türkçe kurumsal yanıt
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {response && (
            <button onClick={copyToClipboard} className="btn-ghost">
              {copied
                ? <><Check className="w-3.5 h-3.5" style={{ color: '#b1c6f9' }} /> Kopyalandı</>
                : <><Copy className="w-3.5 h-3.5" /> Kopyala</>
              }
            </button>
          )}

          <button
            onClick={generate}
            disabled={loading}
            className="btn-primary"
          >
            {loading ? (
              <><span className="spinner" /> Üretiliyor...</>
            ) : response ? (
              <><RefreshCw className="w-3.5 h-3.5" /> Yeniden Üret</>
            ) : (
              <><Sparkles className="w-3.5 h-3.5" /> Yanıt Üret</>
            )}
          </button>
        </div>
      </div>

      {/* Optional context */}
      <div style={{ borderBottom: '1px solid rgba(66,71,84,0.1)' }}>
        <button
          onClick={() => setShowContext(!showContext)}
          className="flex items-center gap-2 w-full px-5 py-2.5 text-left transition-colors"
          style={{ color: '#8d9099' }}
          onMouseEnter={e => e.currentTarget.style.color = '#c2c6d6'}
          onMouseLeave={e => e.currentTarget.style.color = '#8d9099'}
        >
          <ChevronDown
            className="w-3.5 h-3.5 transition-transform"
            style={{ transform: showContext ? 'rotate(180deg)' : 'rotate(0deg)' }}
          />
          <span className="text-label-md">Ek bağlam ekle (opsiyonel)</span>
        </button>

        {showContext && (
          <div className="px-5 pb-3">
            <textarea
              className="textarea-field"
              placeholder="AI'a ekstra bağlam veya talimat verin... Örn: 'Müşteri premium planda, ücretsiz migration teklif et'"
              rows={3}
              value={additionalContext}
              onChange={e => setAdditionalContext(e.target.value)}
            />
          </div>
        )}
      </div>

      {/* Response area */}
      <div className="flex-1 min-h-[280px]">
        {loading ? (
          <div className="flex flex-col gap-3 p-5">
            <div className="flex items-center gap-3 mb-2">
              <div className="spinner" />
              <p className="text-body-sm" style={{ color: '#8d9099' }}>
                Yanıt üretiliyor...
              </p>
            </div>
            {/* Shimmer lines */}
            {[1, 2, 3, 4, 5].map(i => (
              <div
                key={i}
                className="h-3.5 rounded animate-pulse"
                style={{
                  background: '#282a2e',
                  width: i % 3 === 0 ? '60%' : i % 2 === 0 ? '85%' : '100%'
                }}
              />
            ))}
          </div>
        ) : response ? (
          <div
            ref={responseRef}
            className="p-5 overflow-y-auto"
            style={{ maxHeight: '420px' }}
          >
            {/* The "Pulse" — live log bar style indicator */}
            <div className="relative">
              <div
                className="absolute left-0 top-0 bottom-0 w-0.5 rounded"
                style={{
                  background: 'linear-gradient(180deg, #adc6ff 0%, rgba(173,198,255,0.1) 100%)',
                  boxShadow: '0 0 8px rgba(173,198,255,0.4)',
                }}
              />
              <div className="pl-4">
                <pre
                  className="text-body-md whitespace-pre-wrap"
                  style={{
                    color: '#e3e5ef',
                    fontFamily: 'inherit',
                    lineHeight: '1.7',
                  }}
                >
                  {response}
                </pre>
              </div>
            </div>
          </div>
        ) : (
          <div className="py-12 px-5 text-center">
            <div
              className="w-12 h-12 rounded-xl mx-auto mb-3 flex items-center justify-center"
              style={{ background: 'rgba(173, 198, 255, 0.06)' }}
            >
              <Sparkles className="w-6 h-6 opacity-30" style={{ color: '#adc6ff' }} />
            </div>
            <p className="text-body-md font-medium mb-1" style={{ color: '#c2c6d6' }}>
              Yanıt henüz üretilmedi
            </p>
            <p className="text-label-md" style={{ color: '#8d9099' }}>
              Kontrol sonuçlarını çalıştırdıktan sonra AI yanıt üretmek daha doğru
              ve bağlama uygun sonuçlar verir.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
