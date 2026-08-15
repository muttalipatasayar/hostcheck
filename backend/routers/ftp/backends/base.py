"""Protokol soyutlaması — v1'de yalnızca SFTP yazılır ama ABC baştan durur:
FTP/FTPS sonraki turda sıfır yeniden yazımla bu arayüzü uygular.

Tüm metotlar SENKRON'dur ve ayrılmış FTP executor'ında çalıştırılır
(session.py'deki run_ftp). Backend'ler thread-güvenli DEĞİLDİR; oturum
kilidi (FtpSession.lock) eşzamanlı çağrıyı zaten engeller.

`capabilities` kümesi frontend'e `features` olarak gider: FTP/FTPS taşınabilir
chmod yapamaz — arayüz, desteklenmeyen eylemleri bu kümeye göre gizler.
Olası değerler: {'chmod', 'symlink', 'mtime_set'}
"""
from abc import ABC, abstractmethod
from typing import BinaryIO, Optional


class FtpEntry(dict):
    """Dizin girdisi sözlüğü: name, type ('file'|'dir'|'link'), size,
    mtime (epoch sn veya None), perm_octal ('755' veya None), perms (rwx metni)."""


class FtpBackend(ABC):
    """Bağlı bir dosya aktarım oturumu. Kurucu gerçek bağlantıyı kurar;
    başarısızsa Türkçe mesajlı bir istisna fırlatır."""

    capabilities: frozenset[str] = frozenset()

    @abstractmethod
    def home(self) -> str:
        """Oturumun ev dizini (jail kökü) — sunucudaki gerçek mutlak yol."""

    @abstractmethod
    def realpath(self, path: str) -> str:
        """Sunucunun kendi çözümlemesiyle mutlak yol (symlink'ler dahil)."""

    @abstractmethod
    def listdir(self, path: str) -> list[FtpEntry]: ...

    @abstractmethod
    def stat(self, path: str) -> FtpEntry: ...

    @abstractmethod
    def mkdir(self, path: str) -> None: ...

    @abstractmethod
    def rename(self, src: str, dst: str) -> None: ...

    @abstractmethod
    def delete_file(self, path: str) -> None: ...

    @abstractmethod
    def rmdir(self, path: str) -> None:
        """Yalnızca BOŞ dizini siler; özyineleme session katmanında yapılır."""

    @abstractmethod
    def open_read(self, path: str) -> BinaryIO: ...

    @abstractmethod
    def open_write(self, path: str) -> BinaryIO: ...

    @abstractmethod
    def read_bytes(self, path: str, max_bytes: int) -> bytes: ...

    @abstractmethod
    def write_bytes(self, path: str, data: bytes) -> None: ...

    def chmod(self, path: str, mode: int) -> None:
        """capabilities'te 'chmod' yoksa çağrılmamalıdır."""
        raise NotImplementedError("Bu protokol chmod desteklemiyor")

    @abstractmethod
    def close(self) -> None: ...
