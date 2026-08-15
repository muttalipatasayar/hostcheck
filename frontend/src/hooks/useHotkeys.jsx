import { createContext, useContext, useEffect, useRef } from 'react'

// Tek global klavye sahibi. Bir "scope stack" tutar: her useHotkeys çağrısı
// mount'ta yığına bir scope iter, unmount'ta çeker. Tuş olayında YALNIZCA en
// üstteki scope ateşlenir — iki modal açıkken Escape'in ikisini birden
// kapatması bugu böyle kapanır.
//
// Kısayol anahtarı biçimi: 'ctrl+k', 'ctrl+alt+k', 'escape', '/', 'arrowdown'
// Handler `false` dönerse olay o scope'ta ele alınmamış sayılır ve tarayıcıya
// bırakılır (başka scope'a DÜŞMEZ).

const HotkeyContext = createContext(null)

function comboOf(e) {
  const parts = []
  if (e.ctrlKey) parts.push('ctrl')
  if (e.altKey) parts.push('alt')
  if (e.shiftKey && e.key.length > 1) parts.push('shift') // yazılabilir karakterlerde shift zaten key'e yansır
  parts.push(e.key.toLowerCase())
  return parts.join('+')
}

export function HotkeyProvider({ children }) {
  const stackRef = useRef([])

  useEffect(() => {
    const onKeyDown = (e) => {
      const top = stackRef.current[stackRef.current.length - 1]
      if (!top) return
      const handler = top.bindingsRef.current[comboOf(e)]
      if (!handler) return
      if (handler(e) === false) return
      e.preventDefault()
      e.stopPropagation()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  const push = (scope) => { stackRef.current = [...stackRef.current, scope] }
  const remove = (scope) => { stackRef.current = stackRef.current.filter(s => s !== scope) }

  return (
    <HotkeyContext.Provider value={{ push, remove }}>
      {children}
    </HotkeyContext.Provider>
  )
}

// bindings: { 'ctrl+k': (e) => ..., 'escape': (e) => ... }
// Bileşen mount olduğunda scope yığının tepesine gelir.
export function useHotkeys(bindings) {
  const ctx = useContext(HotkeyContext)
  if (!ctx) throw new Error('useHotkeys yalnızca HotkeyProvider altında kullanılabilir')

  const bindingsRef = useRef(bindings)
  bindingsRef.current = bindings

  useEffect(() => {
    const scope = { bindingsRef }
    ctx.push(scope)
    return () => ctx.remove(scope)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
