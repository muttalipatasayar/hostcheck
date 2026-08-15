"""SFTP backend — paramiko üzerinden.

paramiko.SFTPClient eşzamanlı erişime dayanıklı değildir; tüm çağrılar
oturum kilidi altında, ayrılmış FTP executor'ında yapılır (session.py).
"""
import stat as stat_mod
import time
from typing import BinaryIO

import paramiko

from .base import FtpBackend, FtpEntry


def _entry_type(mode: int) -> str:
    if stat_mod.S_ISDIR(mode):
        return "dir"
    if stat_mod.S_ISLNK(mode):
        return "link"
    return "file"


def _perm_octal(mode: int) -> str:
    return format(mode & 0o7777, "o")


def _perm_text(mode: int) -> str:
    return stat_mod.filemode(mode)


class SftpBackend(FtpBackend):
    capabilities = frozenset({"chmod", "symlink", "mtime_set"})

    def __init__(self, host: str, port: int, username: str, password: str):
        self._ssh = paramiko.SSHClient()
        # Host-key politikası ssh.py ile aynı: AutoAddPolicy MITM'e açıktır;
        # WarningPolicy bilinmeyen anahtarı loglar ama bağlantıyı kurar
        # (dahili araç için yeterli). Üretimde RejectPolicy + known_hosts.
        self._ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
        self._ssh.connect(
            host, port=port, username=username, password=password,
            timeout=15, allow_agent=False, look_for_keys=False,
        )
        self._sftp = self._ssh.open_sftp()

    # ── Yol çözümleme ────────────────────────────────────────────────────────
    def home(self) -> str:
        return self._sftp.normalize(".")

    def realpath(self, path: str) -> str:
        return self._sftp.normalize(path)

    # ── Listeleme / meta ─────────────────────────────────────────────────────
    def listdir(self, path: str) -> list[FtpEntry]:
        entries: list[FtpEntry] = []
        for attr in self._sftp.listdir_attr(path):
            mode = attr.st_mode or 0
            entries.append(FtpEntry(
                name=attr.filename,
                type=_entry_type(mode),
                size=attr.st_size or 0,
                mtime=attr.st_mtime,
                perm_octal=_perm_octal(mode),
                perms=_perm_text(mode),
            ))
        return entries

    def stat(self, path: str) -> FtpEntry:
        attr = self._sftp.stat(path)
        mode = attr.st_mode or 0
        return FtpEntry(
            name=path.rsplit("/", 1)[-1],
            type=_entry_type(mode),
            size=attr.st_size or 0,
            mtime=attr.st_mtime,
            perm_octal=_perm_octal(mode),
            perms=_perm_text(mode),
        )

    # ── Değişiklikler ────────────────────────────────────────────────────────
    def mkdir(self, path: str) -> None:
        self._sftp.mkdir(path)

    def rename(self, src: str, dst: str) -> None:
        self._sftp.rename(src, dst)

    def delete_file(self, path: str) -> None:
        self._sftp.remove(path)

    def rmdir(self, path: str) -> None:
        self._sftp.rmdir(path)

    def chmod(self, path: str, mode: int) -> None:
        self._sftp.chmod(path, mode)

    # ── İçerik ───────────────────────────────────────────────────────────────
    def open_read(self, path: str) -> BinaryIO:
        f = self._sftp.open(path, "rb")
        f.prefetch()  # akış hızını belirgin artırır
        return f

    def open_write(self, path: str) -> BinaryIO:
        return self._sftp.open(path, "wb")

    def read_bytes(self, path: str, max_bytes: int) -> bytes:
        with self._sftp.open(path, "rb") as f:
            return f.read(max_bytes)

    def write_bytes(self, path: str, data: bytes) -> None:
        with self._sftp.open(path, "wb") as f:
            f.write(data)

    def close(self) -> None:
        try:
            self._sftp.close()
        finally:
            self._ssh.close()
