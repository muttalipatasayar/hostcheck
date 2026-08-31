import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import toast from 'react-hot-toast'

// SSLTools ve SSLChainCheck ortak kullanır. SSLTools'tan export etseydik
// döngüsel import olurdu: SSLTools -> SSLChainCheck -> SSLTools.
export default function CopyButton({ text, label = 'Kopyala' }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    toast.success('Kopyalandı')
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button onClick={copy} className="btn-ghost text-label-md py-1 px-2 flex items-center gap-1.5">
      {copied ? <><Check className="w-3.5 h-3.5" style={{ color: '#4a6cf7' }} />Kopyalandı</>
               : <><Copy className="w-3.5 h-3.5" />{label}</>}
    </button>
  )
}
