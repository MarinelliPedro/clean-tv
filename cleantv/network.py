"""Checagens de rede local: IP privado, mesma sub-rede, porta 5555 aberta, varredura /24.

ADB pela internet nunca é aceito: só endereços IPv4 privados (RFC 1918).
"""

from __future__ import annotations

import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .errors import CleanTvError

PRIVATE_NETWORKS = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
DEFAULT_PORT = 5555


def check_target_ip(ip: str) -> ipaddress.IPv4Address:
    """Valida o IP da TV. Lança CleanTvError com a explicação se não for aceitável."""
    try:
        address = ipaddress.ip_address(ip.strip())
    except ValueError:
        raise CleanTvError(f"'{ip}' não é um endereço IP válido (exemplo: 192.168.0.40).") from None
    if address.version != 4:
        raise CleanTvError("Use o endereço IPv4 da TV (exemplo: 192.168.0.40).")
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise CleanTvError(
            f"{address} não é um endereço de rede local. Por segurança, a ferramenta só conecta em IPs privados "
            "(10.x, 172.16-31.x, 192.168.x): ADB nunca deve ser usado pela internet."
        )
    return address


def local_address_for(target: str) -> str | None:
    """IP deste computador usado para chegar ao alvo (UDP 'connect' não envia pacotes)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((target, 9))
            return s.getsockname()[0]
    except OSError:
        return None


def local_ipv4_addresses() -> list[str]:
    found: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    routed = local_address_for("192.168.0.1")
    if routed:
        found.add(routed)
    return sorted(ip for ip in found if any(ipaddress.ip_address(ip) in n for n in PRIVATE_NETWORKS))


def same_subnet(a: str, b: str, prefix: int = 24) -> bool:
    return ipaddress.ip_address(b) in ipaddress.ip_network(f"{a}/{prefix}", strict=False)


def probe(ip: str, port: int = DEFAULT_PORT, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def scan_subnet(
    local_ip: str,
    port: int = DEFAULT_PORT,
    timeout: float = 0.4,
    workers: int = 64,
    probe_fn: Callable[[str, int, float], bool] = probe,
) -> list[str]:
    """Procura a porta ADB nos 254 endereços da /24 deste computador (nunca fora dela)."""
    check_target_ip(local_ip)
    network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    hosts = [str(h) for h in network.hosts() if str(h) != local_ip]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda h: (h, probe_fn(h, port, timeout)), hosts))
    return [host for host, is_open in results if is_open]
