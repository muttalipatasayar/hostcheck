"""Yönetici erişim ucu — kimlik doğrulamanın kendisi burada DEĞİL, reverse
proxy'de (Nginx Basic Auth) yapılır. Bu uç yalnızca bir "probe"tur:

SSH/RDP/FTP araçları WebSocket kullanır ve tarayıcı, bir WebSocket el
sıkışması 401 aldığında kimlik penceresi AÇMAZ. Bu yüzden bu araçlar bağlanış
öncesi bu HTTP ucunu çağırır: Nginx 401 döner → tarayıcı Basic Auth penceresi
açar → kullanıcı girer → kimlik aynı origin için önbelleğe alınır → sonraki
WebSocket el sıkışmaları Authorization başlığını otomatik taşır.

Prod'da bu prefix (/api/admin, /api/ssh, /api/rdp, /api/ftp) Nginx'te
auth_basic ile korunur; bu binding hâlâ 127.0.0.1'dir.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/ping")
async def ping():
    """Reverse proxy auth'unu tetiklemek için hafif uç. Proxy isteği buraya
    ilettiyse kimlik zaten doğrulanmıştır."""
    return {"ok": True, "scope": "admin"}
