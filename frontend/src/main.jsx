import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { axiosKur } from './lib/axiosKurulum'
import './index.css'

// Çerez taşıma + CSRF başlığı için global axios ayarı. Bileşenler çıplak
// axios kullanmaya devam ediyor (CLAUDE.md konvansiyonu); ayar burada bir kez
// yapılıyor. Yan etkili import yerine açık çağrı: Rollup ölü kod elemesin.
axiosKur()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
