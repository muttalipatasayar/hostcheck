import { useState } from 'react'

// localStorage'da tutulan "Son Bağlantılar" listesi (şifresiz).
// `isSame` iki kaydın aynı bağlantı sayılıp sayılmayacağını belirler —
// SSH host+kullanıcı, RDP host+port+kullanıcı ile dedupe eder.
export function useSavedConnections(storageKey, isSame, max = 8) {
  const [items, setItems] = useState(() => {
    try { return JSON.parse(localStorage.getItem(storageKey) || '[]') }
    catch { return [] }
  })

  const persist = (list) => {
    localStorage.setItem(storageKey, JSON.stringify(list.slice(0, max)))
  }

  const save = (entry) => {
    setItems(prev => {
      const deduped = prev.filter(c => !isSame(c, entry))
      const updated = [entry, ...deduped]
      persist(updated)
      return updated
    })
  }

  const remove = (index) => {
    setItems(prev => {
      const updated = prev.filter((_, i) => i !== index)
      persist(updated)
      return updated
    })
  }

  return { items, save, remove }
}
