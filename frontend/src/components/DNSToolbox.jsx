import { useState, useEffect } from 'react'
import {
  Search, Shield,
  CheckCircle2, XCircle, AlertTriangle, Info,
  Loader2, Clock, Copy, Check,
  Wrench,
} from 'lucide-react'
import toast from 'react-hot-toast'
import axios from 'axios'
import { RECORD_TYPES, TYPE_MAP } from '../lib/dnsRecordTypes'
import { useTarget, useCommittedTarget } from '../context/TargetContext'
import { apiHataMesaji } from '../lib/apiHata'

// ── Yardımcı bileşenler ───────────────────────────────────────────────────────

function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    toast.success('Kopyalandı')
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button onClick={copy}
      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded"
      style={{ color: '#9da5be' }}
      title="Kopyala">
      {copied ? <Check className="w-3 h-3" style={{ color: '#4a6cf7' }} /> : <Copy className="w-3 h-3" />}
    </button>
  )
}

function StatusBadge({ status }) {
  if (status === 'found')
    return <span className="flex items-center gap-1 text-label-sm" style={{ color: '#4a6cf7' }}><CheckCircle2 className="w-3.5 h-3.5" />Bulundu</span>
  if (status === 'not_found')
    return <span className="flex items-center gap-1 text-label-sm" style={{ color: '#ffb786' }}><AlertTriangle className="w-3.5 h-3.5" />Kayıt Yok</span>
  return <span className="flex items-center gap-1 text-label-sm" style={{ color: '#ffb4ab' }}><XCircle className="w-3.5 h-3.5" />Hata</span>
}

// ── Kayıt satırı ─────────────────────────────────────────────────────────────

function RecordRow({ record, rtype }) {
  const cfg = TYPE_MAP[rtype] || TYPE_MAP['TXT']

  return (
    <div
      className="group flex items-start gap-4 px-5 py-3.5 transition-colors"
      style={{ borderBottom: '1px solid rgba(0,6,30,0.04)' }}
      onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.015)'}
      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
    >
      {/* TTL */}
      <div className="flex-shrink-0 text-right" style={{ minWidth: '64px' }}>
        {record.ttl != null && (
          <span className="text-label-sm font-mono" style={{ color: '#9da5be' }}>
            {record.ttl}s
          </span>
        )}
      </div>

      {/* Tip */}
      <span
        className="text-label-sm font-mono font-semibold flex-shrink-0 px-1.5 py-0.5 rounded"
        style={{ background: 'rgba(173,198,255,0.08)', color: cfg.color, minWidth: '52px', textAlign: 'center' }}
      >
        {rtype === 'SPF' || rtype === 'DMARC' ? rtype : rtype}
      </span>

      {/* MX öncelik */}
      {record.priority != null && (
        <span
          className="text-label-sm font-mono flex-shrink-0 px-1.5 py-0.5 rounded"
          style={{ background: 'rgba(195,177,225,0.1)', color: '#c3b1e1' }}
        >
          {record.priority}
        </span>
      )}

      {/* Değer */}
      <div className="flex-1 min-w-0">
        <p className="text-body-sm font-mono break-all" style={{ color: '#1a1d2e' }}>
          {record.value}
        </p>
        {record.extra && (
          <p className="text-label-sm mt-1 break-all" style={{ color: '#6b7388' }}>
            {record.extra}
          </p>
        )}
      </div>

      {/* Kopyala */}
      <CopyBtn text={record.value} />
    </div>
  )
}

// ── DKIM pattern yardımcısı ───────────────────────────────────────────────────

/**
 * "ntr._domainkey.gastronomad.online" gibi tam DKIM adresi girildiğinde
 * selector ve base domain'i ayıklar. Eşleşmezse null döner.
 */
function parseDkimInput(input) {
  const m = input.match(/^([^.\s]+)\._domainkey\.(.+)$/i)
  if (m) return { selector: m[1].toLowerCase(), baseDomain: m[2].toLowerCase() }
  return null
}

/**
 * Girilen domain'in subdomain'siz kök domain olup olmadığını kontrol eder.
 * example.com → true | www.example.com → false | example.com.tr → true
 */
function isBareRootDomain(domain) {
  const parts = domain.split('.')
  if (parts.length === 2) return true
  // Bileşik TLD'ler: .com.tr, .net.tr, .co.uk vb.
  const compoundTLDs = [
    'com.tr','net.tr','org.tr','gov.tr','edu.tr','av.tr','biz.tr','web.tr',
    'info.tr','tv.tr','tel.tr','name.tr','pol.tr','k12.tr','mil.tr',
    'co.uk','org.uk','me.uk','co.jp','or.jp','ne.jp',
  ]
  const lastTwo = parts.slice(-2).join('.')
  if (compoundTLDs.includes(lastTwo) && parts.length === 3) return true
  return false
}

// ── Türetilmiş sorgu ─────────────────────────────────────────────────────────

/**
 * Paylaşılan hedeften SAF türetme — hedefi asla mutasyona uğratmaz, `note`
 * ile ne yapıldığını açıklar. Gerçek otorite backend'in döndürdüğü
 * `queried_domain` alanıdır; bu fonksiyon yalnızca isteği hazırlar.
 */
export function deriveQuery(rawTarget, recordType, selector) {
  let queryDomain = rawTarget.trim()
  let type = recordType
  let sel = selector
  let note = null

  const parsed = parseDkimInput(queryDomain)
  if (parsed && recordType !== 'CNAME') {
    // Tam DKIM adresi → DKIM sorgusuna çevir (açıkça CNAME seçilmişse dokunma)
    type = 'DKIM'
    sel = parsed.selector
    queryDomain = parsed.baseDomain
    note = `DKIM adresi algılandı — selector: ${parsed.selector}, alan adı: ${parsed.baseDomain}`
  } else if (parsed) {
    // CNAME seçiliyken DKIM adresi girildi → kök alan adını kullan
    queryDomain = parsed.baseDomain
    note = `DKIM adresinden alan adı alındı: ${parsed.baseDomain}`
  }

  if (type === 'CNAME' && isBareRootDomain(queryDomain)) {
    queryDomain = `www.${queryDomain}`
    note = note
      ? `${note} · www. ile sorgulandı`
      : `Kök alan adı algılandı — ${queryDomain} ile sorgulandı`
  }

  return { queryDomain, recordType: type, selector: sel, note }
}

// ── Ana bileşen ───────────────────────────────────────────────────────────────

export default function DNSToolbox() {
  const { target, peekPendingIntent, clearPendingIntent } = useTarget()

  // Palet niyeti ("A kaydı sorgula") ilk render'da okunur ki autoRun sorgusu
  // doğru tiple çıksın; mount'ta temizlenir
  const [selectedType, setSelectedType] = useState(
    () => peekPendingIntent('dns-toolbox')?.recordType ?? 'A'
  )
  const [selector, setSelector] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => { clearPendingIntent('dns-toolbox') }, [clearPendingIntent])

  const runQuery = async (rawTarget, typeOverride, selectorOverride) => {
    const derived = deriveQuery(
      rawTarget,
      typeOverride ?? selectedType,
      selectorOverride !== undefined ? selectorOverride : selector,
    )
    if (!derived.queryDomain) return

    setLoading(true)
    setResult(null)
    try {
      const res = await axios.post('/api/dns-toolbox/query', {
        domain: derived.queryDomain,
        record_type: derived.recordType,
        selector: derived.recordType === 'DKIM' ? (derived.selector || null) : null,
      })
      setResult(res.data)
    } catch (err) {
      toast.error(apiHataMesaji(err, 'Sorgu başarısız'))
    } finally {
      setLoading(false)
    }
  }

  // autoRun:true — ucuz/idempotent; commit edilmiş hedefle sekmeye gelindiğinde
  // kendiliğinden de çalışır
  useCommittedTarget(runQuery, { autoRun: true })

  // Kayıt tipine tıklayınca tipi değiştir ve hedef doluysa hemen sorgula
  const handleTypeSelect = (id) => {
    setSelectedType(id)
    if (target.trim()) runQuery(target, id)
  }

  // Canlı caption: hedef nasıl yorumlanacak? (hedefi DEĞİŞTİRMEZ, açıklar)
  const derivedNow = deriveQuery(target, selectedType, selector)

  const resultType = result?.record_type
  const typeCfg = resultType ? TYPE_MAP[resultType] : null

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="px-8 pt-8 pb-6">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-btn flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, rgba(173,198,255,0.2) 0%, rgba(77,142,255,0.15) 100%)' }}>
            <Wrench className="w-4 h-4" style={{ color: '#3b7eff' }} />
          </div>
          <h1 className="text-headline-md font-semibold" style={{ color: '#1a1d2e', letterSpacing: '-0.01em' }}>
            DNS Toolbox
          </h1>
        </div>
        <p className="text-body-md" style={{ color: '#6b7388' }}>
          A · AAAA · CNAME · MX · NS · TXT · SOA · PTR · SPF · DMARC sorguları
        </p>
      </div>

      {/* Arama */}
      <div className="px-8 pb-5 flex flex-col gap-3">
        {/* Çalıştır + türetme açıklaması */}
        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={() => runQuery(target)}
            disabled={loading || !target.trim()}
            className="btn-primary flex-shrink-0 flex items-center gap-2"
          >
            {loading
              ? <><Loader2 className="w-4 h-4 animate-spin" />Sorgulanıyor...</>
              : <><Search className="w-4 h-4" />{target.trim() ? `${selectedType} sorgula` : 'Sorgula'}</>}
          </button>
          {!target.trim() && (
            <p className="text-body-sm" style={{ color: '#9da5be' }}>
              Üstteki hedef çubuğuna {selectedType === 'PTR' ? 'bir IP adresi' : 'bir alan adı'} yazın.
            </p>
          )}
        </div>

        {/* Türetilmiş sorgu caption'ı — hedef çubuğu DEĞİŞMEZ, yorum burada açıklanır */}
        {derivedNow.note && (
          <p className="text-label-sm flex items-center gap-1.5" style={{ color: '#6b7388' }}>
            <Info className="w-3.5 h-3.5 flex-shrink-0" style={{ color: '#3b7eff' }} />
            {derivedNow.note}
          </p>
        )}

        {/* DKIM selector alanı */}
        {selectedType === 'DKIM' && (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-card px-3 py-2" style={{ background: '#ffffff' }}>
              <span className="text-label-sm font-mono flex-shrink-0" style={{ color: '#f9d4b1' }}>selector</span>
              <span className="text-label-sm" style={{ color: '#9da5be' }}>._domainkey.</span>
              <input
                type="text"
                value={selector}
                onChange={e => setSelector(e.target.value.toLowerCase().trim())}
                onKeyDown={e => { if (e.key === 'Enter') runQuery(target) }}
                placeholder="ör: google, default, mail — boş bırakırsan otomatik arar"
                className="bg-transparent outline-none text-body-sm font-mono"
                style={{ color: '#1a1d2e', caretColor: '#f9d4b1', width: '320px' }}
              />
            </div>
          </div>
        )}

        {/* Kayıt tipi seçici */}
        <div className="flex flex-wrap gap-2">
          {RECORD_TYPES.map(({ id, label, desc }) => (
            <button
              key={id}
              onClick={() => handleTypeSelect(id)}
              title={desc}
              className="px-3 py-1.5 rounded text-label-md font-mono font-semibold transition-all"
              style={{
                background: selectedType === id ? 'rgba(59,127,255,0.12)' : 'rgba(0,6,30,0.03)',
                color: selectedType === id ? '#3b7eff' : '#6b7388',
                border: selectedType === id ? '1px solid rgba(59,127,255,0.25)' : '1px solid transparent',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="px-8 pb-10">
        <div className="flex flex-col gap-4">

          {/* Loading skeleton */}
          {loading && (
            <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
              {[1,2,3].map(i => (
                <div key={i} className="flex items-center gap-4 px-5 py-3.5 animate-pulse"
                  style={{ borderBottom: '1px solid rgba(0,6,30,0.04)' }}>
                  <div className="h-3 w-12 rounded" style={{ background: '#f2f4fa' }} />
                  <div className="h-4 w-14 rounded" style={{ background: '#f2f4fa' }} />
                  <div className="h-3 flex-1 rounded" style={{ background: '#f0f2f8' }} />
                </div>
              ))}
            </div>
          )}

          {/* Sonuç başlığı */}
          {result && !loading && (
            <>
              <div className="flex items-center justify-between px-5 py-3.5 rounded-card"
                style={{ background: '#ffffff' }}>
                <div className="flex items-center gap-3">
                  {typeCfg && <typeCfg.icon className="w-4 h-4" style={{ color: typeCfg.color }} />}
                  <p className="text-body-sm font-semibold" style={{ color: '#1a1d2e' }}>
                    {result.record_type} &nbsp;·&nbsp;
                    <span className="font-mono" style={{ color: '#3b7eff' }}>{result.queried_domain}</span>
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  {result.query_ms && (
                    <span className="flex items-center gap-1 text-label-sm font-mono" style={{ color: '#9da5be' }}>
                      <Clock className="w-3 h-3" />{result.query_ms}ms
                    </span>
                  )}
                  <StatusBadge status={result.status} />
                </div>
              </div>

              {/* Kayıtlar */}
              {result.records.length > 0 ? (
                <div className="rounded-card overflow-hidden" style={{ background: '#ffffff' }}>
                  {/* Tablo başlığı */}
                  <div className="flex items-center gap-4 px-5 py-2"
                    style={{ borderBottom: '1px solid rgba(0,6,30,0.06)', background: '#f0f2f7' }}>
                    <span className="text-label-sm font-medium" style={{ color: '#9da5be', minWidth: '64px', textAlign: 'right' }}>TTL</span>
                    <span className="text-label-sm font-medium" style={{ color: '#9da5be', minWidth: '52px' }}>Tip</span>
                    {result.record_type === 'MX' && (
                      <span className="text-label-sm font-medium" style={{ color: '#9da5be' }}>Öncelik</span>
                    )}
                    <span className="text-label-sm font-medium" style={{ color: '#9da5be' }}>Değer</span>
                  </div>
                  {result.records.map((rec, i) => (
                    <RecordRow key={i} record={rec} rtype={result.record_type} />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 rounded-card"
                  style={{ background: '#ffffff' }}>
                  <AlertTriangle className="w-7 h-7 mb-3 opacity-40" style={{ color: '#ffb786' }} />
                  <p className="text-body-sm font-medium" style={{ color: '#4a5068' }}>{result.message}</p>
                  <p className="text-label-sm mt-1" style={{ color: '#9da5be' }}>
                    Sunucu: {result.nameservers.slice(0, 2).join(', ')}
                  </p>
                </div>
              )}

              {/* Analiz paneli */}
              {result.analysis && (
                <div className="rounded-card px-5 py-4 flex items-start gap-3"
                  style={{
                    background: result.record_type === 'DMARC'  ? 'rgba(255,183,134,0.06)'
                      : result.record_type === 'SPF'    ? 'rgba(177,249,194,0.05)'
                      : result.record_type === 'DKIM'   ? 'rgba(249,212,177,0.06)'
                      : result.record_type === 'DNSSEC' ? 'rgba(177,249,224,0.06)'
                      : 'rgba(59,127,255,0.05)',
                    border: `1px solid ${
                      result.record_type === 'DMARC'  ? 'rgba(255,183,134,0.15)'
                      : result.record_type === 'SPF'    ? 'rgba(177,249,194,0.15)'
                      : result.record_type === 'DKIM'   ? 'rgba(249,212,177,0.15)'
                      : result.record_type === 'DNSSEC' ? 'rgba(177,249,224,0.15)'
                      : 'rgba(59,127,255,0.09)'}`,
                  }}>
                  <Shield className="w-4 h-4 mt-0.5 flex-shrink-0" style={{
                    color: result.record_type === 'DMARC'  ? '#ffb786'
                      : result.record_type === 'SPF'    ? '#b1f9c2'
                      : result.record_type === 'DKIM'   ? '#f9d4b1'
                      : result.record_type === 'DNSSEC' ? '#b1f9e0'
                      : '#3b7eff'
                  }} />
                  <div>
                    <p className="text-label-sm font-semibold mb-1" style={{
                      color: result.record_type === 'DMARC'  ? '#ffb786'
                        : result.record_type === 'SPF'    ? '#b1f9c2'
                        : result.record_type === 'DKIM'   ? '#f9d4b1'
                        : result.record_type === 'DNSSEC' ? '#b1f9e0'
                        : '#3b7eff'
                    }}>
                      {result.record_type} Analizi
                    </p>
                    <p className="text-body-sm" style={{ color: '#4a5068', lineHeight: '1.7' }}>
                      {result.analysis}
                    </p>
                  </div>
                </div>
              )}
            </>
          )}

          {/* Boş ekran */}
          {!result && !loading && (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
                style={{ background: 'rgba(59,127,255,0.05)' }}>
                <Wrench className="w-7 h-7 opacity-30" style={{ color: '#3b7eff' }} />
              </div>
              <p className="text-title-md font-medium mb-1" style={{ color: '#4a5068' }}>DNS Toolbox</p>
              <p className="text-body-md text-center max-w-xs" style={{ color: '#6b7388' }}>
                Üstteki hedef çubuğuna alan adı yazın, kayıt tipini seçin ve Enter'a basın
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
