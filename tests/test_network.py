import pytest

from cleantv import network
from cleantv.errors import CleanTvError


@pytest.mark.parametrize("ip", ["192.168.0.40", "10.1.2.3", "172.16.5.4", "172.31.255.1"])
def test_private_addresses_are_accepted(ip):
    network.check_target_ip(ip)


@pytest.mark.parametrize(
    "ip", ["8.8.8.8", "127.0.0.1", "100.64.1.1", "172.32.0.1", "0.0.0.0", "255.255.255.255", "abc", "::1", "fe80::1", "192.168.0"]
)
def test_non_local_addresses_are_rejected(ip):
    with pytest.raises(CleanTvError):
        network.check_target_ip(ip)


def test_public_address_explains_why():
    with pytest.raises(CleanTvError, match="internet"):
        network.check_target_ip("8.8.8.8")


def test_same_subnet():
    assert network.same_subnet("192.168.0.10", "192.168.0.40")
    assert not network.same_subnet("192.168.0.10", "192.168.1.40")


def test_scan_stays_inside_local_24():
    probed = []

    def probe(ip, port, timeout):
        probed.append(ip)
        return ip in ("192.168.0.40", "192.168.0.41")

    assert network.scan_subnet("192.168.0.10", probe_fn=probe) == ["192.168.0.40", "192.168.0.41"]
    assert len(probed) == 253
    assert all(ip.startswith("192.168.0.") for ip in probed)
    assert "192.168.0.10" not in probed


def test_scan_refuses_public_base():
    with pytest.raises(CleanTvError):
        network.scan_subnet("8.8.8.8", probe_fn=lambda *a: False)
