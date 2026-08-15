import { useEffect, useRef } from 'react'

// display:none altında clientWidth/clientHeight 0 olur; xterm FitAddon.fit()
// ve RDP fitDisplay() sıfır boyutla çağrılırsa yanlış ölçüm / sıfıra bölme
// üretir. Bu hook, eleman ölçülebilir bir boyuta ulaştığında (görünür
// olduğunda veya yeniden boyutlandığında) `refit`'i çağırır; sıfır boyutları
// yutar. SSH terminali, RDP ekranı, SSL alt sekmeleri ve tam ekran geçişleri
// aynı hata sınıfını paylaştığı için tek yerde çözülür.
export function useRefitOnVisible(elementRef, refit) {
  const refitRef = useRef(refit)
  refitRef.current = refit

  useEffect(() => {
    const el = elementRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        if (width > 0 && height > 0) {
          try { refitRef.current() } catch { /* boş */ }
        }
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [elementRef])
}
