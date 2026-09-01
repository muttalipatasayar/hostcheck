import { Lock, LogIn, Mail, ShieldCheck, UserPlus } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

// Giriş yapılmamışken Hazır Yanıtlar'ın yerine görünen kapı.
//
// Sekmeyi tamamen gizlemek yerine kapı göstermek bilinçli: yeni gelen bir
// destek uzmanı özelliğin var olduğunu ve nasıl erişeceğini görüyor.

export default function UyeKapisi({ onGiris, onKayit }) {
  const { ayarlar } = useAuth()
  const izinli = ayarlar.izinli_alanlar || []

  return (
    <div className="flex h-full items-center justify-center px-6 py-10">
      <div className="w-full max-w-md text-center">
        <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-5"
          style={{ background: 'linear-gradient(135deg, rgba(59,127,255,0.14) 0%, rgba(37,99,235,0.10) 100%)' }}>
          <Lock className="w-7 h-7" style={{ color: '#2563eb' }} />
        </div>

        <h2 className="text-headline-md font-semibold mb-2" style={{ color: '#1a1d2e', letterSpacing: '-0.01em' }}>
          Bu bölüm üyelere özel
        </h2>
        <p className="text-body-md leading-relaxed mb-6" style={{ color: '#6b7388' }}>
          Hazır Yanıtlar kütüphanesi müşterilere gönderilen hazır metinleri barındırır.
          Görüntülemek için kurumsal hesabınızla giriş yapın.
        </p>

        <div className="flex items-center justify-center gap-3 mb-7">
          <button onClick={onGiris} className="btn-primary">
            <LogIn className="w-4 h-4" /> Giriş Yap
          </button>
          <button onClick={onKayit} className="btn-secondary">
            <UserPlus className="w-4 h-4" /> Üye Ol
          </button>
        </div>

        <div className="card px-5 py-4 text-left">
          <div className="flex items-start gap-3">
            <ShieldCheck className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: '#2563eb' }} />
            <div className="min-w-0">
              <p className="text-body-sm font-medium mb-1" style={{ color: '#1a1d2e' }}>
                Kimler üye olabilir?
              </p>
              <p className="text-body-sm leading-relaxed" style={{ color: '#6b7388' }}>
                Yalnızca{' '}
                {izinli.length
                  ? izinli.map((a, i) => (
                      <span key={a}>
                        {i > 0 && ' ve '}
                        <span className="font-mono font-medium" style={{ color: '#2563eb' }}>@{a}</span>
                      </span>
                    ))
                  : <span className="font-mono">kurumsal</span>}{' '}
                uzantılı kurumsal e-posta adresleri. Kayıttan sonra adresinize gelen
                bağlantıyla hesabınızı doğrulamanız gerekir.
              </p>
              <p className="text-label-md mt-2 flex items-center gap-1.5" style={{ color: '#9da5be' }}>
                <Mail className="w-3.5 h-3.5" />
                Doğrulama e-postası gelmezse spam klasörünü kontrol edin.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
