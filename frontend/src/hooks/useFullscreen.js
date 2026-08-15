import { useState } from 'react'

// Tam ekran aç/kapa. Geçişten sonra layout otursun diye `onAfterToggle`
// (xterm fit / RDP scale) kısa bir gecikmeyle çağrılır.
export function useFullscreen(onAfterToggle, delay = 80) {
  const [isFullscreen, setIsFullscreen] = useState(false)

  const toggle = () => {
    setIsFullscreen(f => !f)
    if (onAfterToggle) setTimeout(() => { try { onAfterToggle() } catch { /* boş */ } }, delay)
  }

  return { isFullscreen, setIsFullscreen, toggle }
}
