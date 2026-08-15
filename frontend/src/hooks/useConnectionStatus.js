import { useState } from 'react'

// SSH/RDP (ileride FTP) oturumlarının ortak durum makinesi:
// idle → connecting → connected; her adımda error'a düşebilir.
export function useConnectionStatus() {
  const [status, setStatus] = useState('idle')
  const [errorMsg, setErrorMsg] = useState('')

  const fail = (msg) => {
    setStatus('error')
    setErrorMsg(msg)
  }

  const reset = () => {
    setStatus('idle')
    setErrorMsg('')
  }

  return {
    status, setStatus,
    errorMsg, setErrorMsg,
    isConnected: status === 'connected',
    isConnecting: status === 'connecting',
    fail,
    reset,
  }
}
