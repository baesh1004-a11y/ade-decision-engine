from __future__ import annotations

import socket


def get_lan_ip() -> str:
    """Return the preferred LAN IPv4 address without sending application data."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        address = sock.getsockname()[0]
        return address
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def dashboard_urls(port: int = 8501) -> dict[str, str]:
    lan_ip = get_lan_ip()
    return {
        "desktop": f"http://localhost:{port}",
        "mobile": f"http://{lan_ip}:{port}",
        "lan_ip": lan_ip,
    }
