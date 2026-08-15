"""Uzak yol güvenliği — path traversal jail'i.

Dürüst uyarı: panelin güvenlik sınırı hâlâ 127.0.0.1 binding'idir (kimlik
doğrulama yok). Bu jail, paneli path karışıklığından korur: kullanıcı arayüzü
kök ("/") olarak oturumun ev dizinini görür ve saf string hileleriyle
(../, null byte, mutlak yol) onun dışına çıkamaz. Uzak SYMLINK'ler saf string
mantığını yenebildiği için eylemden önce sunucunun kendi realpath'i ile
yeniden doğrulama da şarttır (backend'lerdeki `resolve_within_root`).
"""
import posixpath

from fastapi import HTTPException


def safe_join(root: str, user_path: str) -> str:
    """Kullanıcının verdiği yolu jail köküne bağlar.

    Kullanıcı yolları her zaman jail köküne göre yorumlanır: "/" = kök.
    Null-byte reddi → normpath → normpath SONRASI '..' reddi → kök prefix
    kontrolü. Dönen değer sunucudaki gerçek mutlak yoldur.
    """
    if user_path is None or "\x00" in user_path:
        raise HTTPException(400, "Geçersiz yol")

    # Her zaman '/' köklü normalize et ("a/b", "/a/b", "" hepsi aynı davranır)
    normalized = posixpath.normpath("/" + user_path.strip())

    # normpath SONRASI kontrol: "a/../../b" gibi diziler normpath'te çözülür,
    # geriye '..' kaldıysa kök dışına çıkma girişimidir
    if ".." in normalized.split("/"):
        raise HTTPException(400, "Yol kök dizinin dışına çıkamaz")

    # Kök '/' ise rstrip sonucu '' olur — '//' gibi çift bölü prefix'i üretmemek
    # için birleştirme ve kontrol soyulmuş kök üzerinden yapılır
    root_stripped = root.rstrip("/")
    joined = posixpath.normpath(root_stripped + normalized)
    base = root_stripped or "/"

    if joined != base and not joined.startswith(root_stripped + "/"):
        raise HTTPException(400, "Yol kök dizinin dışına çıkamaz")
    return joined


def to_user_path(root: str, real_path: str) -> str:
    """Sunucu yolunu arayüzün gördüğü jail-göreli yola çevirir."""
    root = root.rstrip("/") or "/"
    if real_path == root:
        return "/"
    if real_path.startswith(root + "/"):
        return real_path[len(root):]
    return "/"
