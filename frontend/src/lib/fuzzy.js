// Türkçe'ye duyarlı bulanık eşleştirme — komut paleti için.
// Bağımlılık yok; komut sayısı < 100 olduğundan basit skorlama yeterli.

// ı/i, ş/s, ğ/g, ü/u, ö/o, ç/c katlama: "sifre" yazan "şifre"yi bulmalı.
const TR_FOLD = { 'ı': 'i', 'ş': 's', 'ğ': 'g', 'ü': 'u', 'ö': 'o', 'ç': 'c' }

export function foldTr(s) {
  return s
    .toLocaleLowerCase('tr')
    .replace(/[ışğüöç]/g, c => TR_FOLD[c] || c)
}

// 0 = eşleşme yok; büyük skor = daha iyi eşleşme.
export function fuzzyScore(query, text) {
  const q = foldTr(query.trim())
  const t = foldTr(text)
  if (!q) return 1

  // Doğrudan geçiş: başta olması en değerli
  const idx = t.indexOf(q)
  if (idx === 0) return 100
  if (idx > 0) {
    // Kelime başında geçiyorsa ortadan geçmesinden daha iyi
    const wordStart = t[idx - 1] === ' '
    return (wordStart ? 85 : 70) - Math.min(idx, 30)
  }

  // Alt dizi eşleşmesi: ardışık ve kelime başı karakterlere bonus
  let qi = 0
  let score = 0
  let prevHit = -2
  for (let i = 0; i < t.length && qi < q.length; i++) {
    if (t[i] !== q[qi]) continue
    score += i === prevHit + 1 ? 3 : 1
    if (i === 0 || t[i - 1] === ' ') score += 2
    prevHit = i
    qi++
  }
  return qi === q.length ? Math.min(score, 60) : 0
}
