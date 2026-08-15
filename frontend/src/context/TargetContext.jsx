import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

// Kalıcı hedef: tüm araçların paylaştığı tek girdi.
//
// İki ayrı state tutulur:
// - `target`    — çubuktaki canlı metin. Her tuş vuruşunda değişir ama
//                 HİÇBİR sorgu tetiklemez; yazmak bedavadır.
// - `commitSeq` — monoton sayaç. Yalnızca Enter/Çalıştır ile `commitTarget()`
//                 çağrıldığında artar; araçlar sorguyu buna abone olarak çalıştırır.
const TargetContext = createContext(null)

export function TargetProvider({ children }) {
  const [target, setTarget] = useState('')
  const [commitSeq, setCommitSeq] = useState(0)
  // Hazır Yanıtlar'ın yerel filtresi — hedef DEĞİL, çubuğun bağlama göre
  // değişen içeriği (sorgu tetiklemez, sadece listeyi süzer)
  const [filter, setFilter] = useState('')

  // Sekmeler arası niyet aktarımı: palet `navigate()` + `setPendingIntent()`
  // yapar, hedef araç ilk render'da peek'ler ve mount effect'inde temizler.
  // (Ref: render sırasında okunabilsin, StrictMode çift render'ı bozmasın)
  const pendingIntentRef = useRef(null)

  const commitTarget = useCallback(() => {
    setCommitSeq(s => s + 1)
  }, [])

  const setPendingIntent = useCallback((view, payload) => {
    pendingIntentRef.current = { view, payload }
  }, [])

  const peekPendingIntent = useCallback((view) => (
    pendingIntentRef.current?.view === view ? pendingIntentRef.current.payload : null
  ), [])

  const clearPendingIntent = useCallback((view) => {
    if (pendingIntentRef.current?.view === view) pendingIntentRef.current = null
  }, [])

  return (
    <TargetContext.Provider value={{
      target, setTarget, commitSeq, commitTarget,
      filter, setFilter,
      setPendingIntent, peekPendingIntent, clearPendingIntent,
    }}>
      {children}
    </TargetContext.Provider>
  )
}

export function useTarget() {
  const ctx = useContext(TargetContext)
  if (!ctx) throw new Error('useTarget yalnızca TargetProvider altında kullanılabilir')
  return ctx
}

// Commit edilen hedefe abone olur ve `run(hedef)` çağırır.
//
// autoRun:false (pahalı araçlar): mount ANINDA çalışmaz — sayaç mount'taki
// değerden başlar, yalnızca mount'tan sonra gelen commit'lerde tetiklenir.
// autoRun:true (ucuz/idempotent araçlar): hedef daha önce commit edilmişse
// mount'ta da çalışır (sayaç 0'dan başlar).
export function useCommittedTarget(run, { autoRun = false } = {}) {
  const { target, commitSeq } = useTarget()
  const lastSeqRef = useRef(autoRun ? 0 : commitSeq)
  const runRef = useRef(run)
  runRef.current = run

  useEffect(() => {
    if (commitSeq === lastSeqRef.current) return
    lastSeqRef.current = commitSeq
    const t = target.trim()
    if (t) runRef.current(t)
  }, [commitSeq, target])

  return target
}
