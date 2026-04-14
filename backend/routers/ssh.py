import asyncio
import json

import paramiko
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/api/ssh", tags=["ssh"])


@router.websocket("/ws")
async def ssh_terminal(websocket: WebSocket):
    await websocket.accept()
    ssh = None
    channel = None

    try:
        # İlk mesaj bağlantı parametrelerini içerir
        try:
            init_data = await asyncio.wait_for(websocket.receive_json(), timeout=15.0)
        except asyncio.TimeoutError:
            await websocket.send_text("\r\nHata: Bağlantı parametreleri alınamadı (timeout)\r\n")
            return

        host = str(init_data.get("host", "")).strip()
        port = int(init_data.get("port", 22))
        username = str(init_data.get("username", "")).strip()
        password = str(init_data.get("password", ""))

        if not host or not username:
            await websocket.send_text("\r\nHata: Host ve kullanıcı adı zorunludur.\r\n")
            return

        # Port aralığı doğrulama
        if not (1 <= port <= 65535):
            await websocket.send_text("\r\nHata: Geçersiz port numarası.\r\n")
            return

        await websocket.send_text(f"\r\nBağlanıyor: {username}@{host}:{port} ...\r\n")

        # SSH bağlantısını executor'da kur (event loop'u bloke etmemek için)
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: ssh.connect(
                host,
                port=port,
                username=username,
                password=password,
                timeout=15,
                allow_agent=False,
                look_for_keys=False,
            ),
        )

        channel = ssh.invoke_shell(term="xterm-256color", width=220, height=50)
        channel.setblocking(False)

        # ANSI renkli bağlantı mesajı — yeşil onay işareti
        success_msg = (
            f"\r\n\x1b[38;2;168;213;162m✓ Bağlantı kuruldu\x1b[0m"
            f" \x1b[38;2;66;71;84m—\x1b[0m"
            f" \x1b[38;2;173;198;255m{username}@{host}\x1b[0m\r\n\r\n"
        )
        await websocket.send_text(success_msg)

        # SSH çıktısını WebSocket'e yönlendiren arka plan görevi
        async def forward_output():
            while True:
                try:
                    await asyncio.sleep(0.02)
                    if channel.recv_ready():
                        data = channel.recv(4096)
                        if data:
                            await websocket.send_bytes(data)
                    if channel.exit_status_ready() or channel.closed:
                        try:
                            await websocket.send_text("\r\n\r\nBağlantı kapatıldı.\r\n")
                        except Exception:
                            pass
                        break
                except Exception:
                    break

        output_task = asyncio.create_task(forward_output())

        try:
            while True:
                msg = await websocket.receive()

                if msg.get("type") == "websocket.disconnect":
                    break

                if "bytes" in msg:
                    channel.send(msg["bytes"])
                elif "text" in msg:
                    text = msg["text"]
                    try:
                        parsed = json.loads(text)
                        if parsed.get("type") == "resize":
                            cols = int(parsed.get("cols", 220))
                            rows = int(parsed.get("rows", 50))
                            channel.resize_pty(width=cols, height=rows)
                    except (json.JSONDecodeError, ValueError, KeyError):
                        channel.send(text.encode())
        finally:
            output_task.cancel()
            try:
                await output_task
            except asyncio.CancelledError:
                pass

    except asyncio.TimeoutError:
        _safe_send(websocket, "\r\nHata: SSH bağlantısı zaman aşımına uğradı.\r\n")
    except paramiko.AuthenticationException:
        await _safe_send(websocket, "\r\nHata: Kimlik doğrulama başarısız. Kullanıcı adı veya şifre hatalı.\r\n")
    except paramiko.SSHException as exc:
        await _safe_send(websocket, f"\r\nSSH Hatası: {exc}\r\n")
    except OSError as exc:
        await _safe_send(websocket, f"\r\nBağlantı hatası: {exc}\r\n")
    except WebSocketDisconnect:
        pass
    finally:
        if channel:
            try:
                channel.close()
            except Exception:
                pass
        if ssh:
            try:
                ssh.close()
            except Exception:
                pass


async def _safe_send(websocket: WebSocket, text: str):
    try:
        await websocket.send_text(text)
    except Exception:
        pass
