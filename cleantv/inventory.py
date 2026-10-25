"""Retrato completo da TV: identidade, pacotes, launcher e configurações relevantes.

O mesmo retrato serve de inventário (para classificar) e de backup (para restaurar).
Só usa comandos de leitura.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from . import device
from .adb.transport import Transport
from .constants import HOME_CATEGORY, LEANBACK_CATEGORY, STOCK_LAUNCHERS
from .device import DeviceIdentity, component_package

PLATFORM_LABELS = {
    "google_tv": "Google TV",
    "android_tv": "Android TV",
    "android_tv_vendor": "Android TV com launcher do fabricante",
    "unknown": "não identificada",
}

# Configurações gravadas no backup (só leitura; a ferramenta não altera nenhuma delas,
# exceto adb_enabled/adb_wifi_enabled no final, se você pedir).
RECORDED_SETTINGS = (
    ("global", "adb_enabled"),
    ("global", "adb_wifi_enabled"),
    ("global", "development_settings_enabled"),
    ("global", "window_animation_scale"),
    ("global", "transition_animation_scale"),
    ("global", "animator_duration_scale"),
    ("global", "private_dns_mode"),
    ("global", "private_dns_specifier"),
    ("secure", "screensaver_enabled"),
    ("secure", "screensaver_components"),
    ("secure", "screensaver_activate_on_sleep"),
)


@dataclass
class PackageInfo:
    name: str
    system: bool
    enabled: bool
    launchable: str | None = None  # atividade LEANBACK_LAUNCHER (aparece na tela inicial)
    home: str | None = None  # atividade HOME (é um launcher)


@dataclass
class Inventory:
    identity: DeviceIdentity
    is_tv: bool
    platform: str
    packages: dict[str, PackageInfo]
    uninstalled_for_user: list[str]
    home_component: str | None
    home_candidates: list[str]
    settings: dict[str, str | None]
    collected_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def disabled(self) -> set[str]:
        return {name for name, info in self.packages.items() if not info.enabled}

    @property
    def home_package(self) -> str | None:
        return component_package(self.home_component)

    def launchable_apps(self) -> list[PackageInfo]:
        return sorted((p for p in self.packages.values() if p.enabled and p.launchable), key=lambda p: p.name)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["identity"] = self.identity.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Inventory":
        data = dict(data)
        data["identity"] = DeviceIdentity.from_dict(data["identity"])
        data["packages"] = {name: PackageInfo(**info) for name, info in data["packages"].items()}
        return cls(**data)


def detect_platform(installed: set[str], home_component: str | None) -> str:
    if "com.google.android.apps.tv.launcherx" in installed:
        return "google_tv"
    if {"com.google.android.tvlauncher", "com.google.android.leanbacklauncher"} & installed:
        return "android_tv"
    home = component_package(home_component)
    if home and home not in STOCK_LAUNCHERS:
        return "android_tv_vendor"
    return "unknown"


def collect(t: Transport) -> Inventory:
    identity = device.read_identity(t)
    features = device.list_features(t)
    installed = device.list_packages(t)
    system = device.list_packages(t, "-s")
    disabled = device.list_packages(t, "-d")
    with_uninstalled = device.list_packages(t, "-u")
    home_candidates = device.query_activities(t, HOME_CATEGORY)
    launchables = device.query_activities(t, LEANBACK_CATEGORY)
    home_component = device.resolve_home(t)

    packages = {
        name: PackageInfo(name=name, system=name in system, enabled=name not in disabled) for name in sorted(installed)
    }
    for component in launchables:
        info = packages.get(component_package(component) or "")
        if info and not info.launchable:
            info.launchable = component
    for component in home_candidates:
        info = packages.get(component_package(component) or "")
        if info and not info.home:
            info.home = component

    settings = {f"{ns}/{key}": device.get_setting(t, ns, key) for ns, key in RECORDED_SETTINGS}
    return Inventory(
        identity=identity,
        is_tv="android.software.leanback" in features,
        platform=detect_platform(installed, home_component),
        packages=packages,
        uninstalled_for_user=sorted(with_uninstalled - installed),
        home_component=home_component,
        home_candidates=home_candidates,
        settings=settings,
    )
