import { Search, FileKey, Package, FilePlus2, ListTree } from 'lucide-react'

// SSL Araçları alt sekmeleri — SSLTools ve komut paleti buradan okur.
export const SSL_TABS = [
  { id: 'ssl-checker',  label: 'SSL Sorgula',  icon: Search    },
  { id: 'chain-check',  label: 'Zincir Doğrulama', icon: ListTree },
  { id: 'csr-decode',   label: 'CSR Çözümle',  icon: FileKey   },
  { id: 'pfx-convert',  label: 'PFX Dönüştür', icon: Package   },
  { id: 'csr-generate', label: 'CSR Oluştur',  icon: FilePlus2 },
]
