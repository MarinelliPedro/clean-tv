"""Operações de alto nível sobre a TV, construídas em cima de um Transport.

Cada função envia um comando curto e interpreta a saída no formato real do Android.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass

from .adb.transport import Transport
from .constants import (
    HOME_CATEGORY,
    NOT_A_LAUNCHER_HINTS,
    NOT_A_LAUNCHER_PACKAGES,
    OUR_LAUNCHER_CONFIGURE,
    OUR_LAUNCHER_RECEIVER,
    RESOLVER_ACTIVITY,
    SETUP_WIZARDS,
    STATE_DEFAULT,
)
from .errors import UnsafeCommand

PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)*$")
COMPONENT_RE = re.compile(r"^[A-Za-z0-9_.]+/[A-Za-z0-9_.$]+$")
_STATE_RE = re.compile(r"User 0:.*?\benabled=(\d+)")
_RESUMED_RE = re.compile(
    r"(?:mResumedActivity|topResumedActivity|ResumedActivity)\S*?\s*[:=]\s*ActivityRecord\{\S+ u\d+ ([^\s}]+)"
)


def check_package(name: str) -> str:
    if not PACKAGE_RE.match(name):
        raise UnsafeCommand(f"Nome de pacote inválido: {name!r}")
    return name


def normalize_component(component: str) -> str:
    pkg, _, cls = component.partition("/")
    if cls.startswith("."):
        cls = pkg + cls
    return f"{pkg}/{cls}"


def component_package(component: str | None) -> str | None:
    return component.split("/", 1)[0] if component else None


def is_usable_launcher(component: str | None) -> bool:
    """Um HOME que serve como tela inicial (não é seletor, setup, fallback ou app de fábrica)."""
    if not component or component == RESOLVER_ACTIVITY:
        return False
    pkg = component_package(component)
    if pkg in SETUP_WIZARDS or pkg in NOT_A_LAUNCHER_PACKAGES:
        return False
    low = component.lower()
    return not any(hint in low for hint in NOT_A_LAUNCHER_HINTS)


@dataclass(frozen=True)
class DeviceIdentity:
    manufacturer: str
    brand: str
    model: str
    device: str
    android_release: str
    sdk: int
    fingerprint: str
    serial: str
    adb_secure: str

    @property
    def device_id(self) -> str:
        if self.serial and self.serial.lower() not in ("unknown", "0", "none"):
            return f"{self.manufacturer or 'tv'}-{self.serial}"
        digest = hashlib.sha1(f"{self.fingerprint}|{self.model}".encode()).hexdigest()[:12]
        return f"{self.manufacturer or 'tv'}-{digest}"

    def label(self) -> str:
        return f"{self.manufacturer} {self.model} — Android {self.android_release} (SDK {self.sdk})"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceIdentity":
        return cls(**data)


_IDENTITY_PROPS = {
    "manufacturer": "ro.product.manufacturer",
    "brand": "ro.product.brand",
    "model": "ro.product.model",
    "device": "ro.product.device",
    "android_release": "ro.build.version.release",
    "sdk": "ro.build.version.sdk",
    "fingerprint": "ro.build.fingerprint",
    "serial": "ro.serialno",
    "adb_secure": "ro.adb.secure",
}


def getprop(t: Transport, key: str) -> str:
    return t.shell(["getprop", key]).stdout.strip()


def read_identity(t: Transport) -> DeviceIdentity:
    values = {field: getprop(t, prop) for field, prop in _IDENTITY_PROPS.items()}
    try:
        values["sdk"] = int(values["sdk"])
    except ValueError:
        values["sdk"] = 0
    return DeviceIdentity(**values)


def list_features(t: Transport) -> set[str]:
    out = t.shell(["pm", "list", "features"]).stdout
    return {line.split(":", 1)[1].strip() for line in out.splitlines() if line.startswith("feature:")}


def list_packages(t: Transport, *flags: str) -> set[str]:
    out = t.shell(["pm", "list", "packages", *flags]).stdout
    names = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            # Com -f o formato é package:/caminho/app.apk=nome
            names.add(line[len("package:"):].rsplit("=", 1)[-1])
    return names


def package_state(t: Transport, pkg: str) -> int | None:
    """Estado exato para o usuário 0 (0=padrão, 1=ativo, 2/3/4=desativado) ou None se não instalado."""
    out = t.shell(["dumpsys", "package", check_package(pkg)]).stdout
    if f"Package [{pkg}]" not in out:
        return None
    match = _STATE_RE.search(out)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class OpResult:
    ok: bool
    message: str


def _set_state(t: Transport, verb: str, pkg: str) -> OpResult:
    result = t.shell(["pm", verb, "--user", "0", check_package(pkg)])
    return OpResult("new state:" in result.stdout, result.output)


def disable_user(t: Transport, pkg: str) -> OpResult:
    return _set_state(t, "disable-user", pkg)


def enable(t: Transport, pkg: str) -> OpResult:
    return _set_state(t, "enable", pkg)


def restore_state(t: Transport, pkg: str, original: int | None) -> OpResult:
    """Volta ao estado original: `default-state` quando era o padrão, senão `enable`."""
    if original == STATE_DEFAULT:
        result = _set_state(t, "default-state", pkg)
        if result.ok:
            return result
    return enable(t, pkg)


def _components(text: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if COMPONENT_RE.match(line):
            component = normalize_component(line)
            if component not in found:
                found.append(component)
    return found


def resolve_home(t: Transport) -> str | None:
    out = t.shell(
        ["cmd", "package", "resolve-activity", "--brief", "-a", "android.intent.action.MAIN", "-c", HOME_CATEGORY]
    ).stdout
    found = _components(out)
    return found[-1] if found else None


def home_priority(t: Transport) -> int:
    """Prioridade do HOME resolvido. Launchers de sistema podem declarar prioridade > 0, e aí o
    Android ignora a preferência do usuário enquanto eles estiverem ativos."""
    out = t.shell(
        ["cmd", "package", "resolve-activity", "--brief", "-a", "android.intent.action.MAIN", "-c", HOME_CATEGORY]
    ).stdout
    match = re.search(r"priority=(-?\d+)", out)
    return int(match.group(1)) if match else 0


def query_activities(t: Transport, category: str) -> list[str]:
    out = t.shell(
        ["cmd", "package", "query-activities", "--brief", "-a", "android.intent.action.MAIN", "-c", category]
    ).stdout
    return _components(out)


def set_home_activity(t: Transport, component: str) -> OpResult:
    if not COMPONENT_RE.match(component):
        raise UnsafeCommand(f"Componente inválido: {component!r}")
    result = t.shell(["cmd", "package", "set-home-activity", "--user", "0", component])
    return OpResult("success" in result.stdout.lower(), result.output)


def press_home(t: Transport) -> None:
    t.shell(["input", "keyevent", "KEYCODE_HOME"])


def start_activity(t: Transport, component: str) -> None:
    if not COMPONENT_RE.match(component):
        raise UnsafeCommand(f"Componente inválido: {component!r}")
    t.shell(["am", "start", "-n", component])


def foreground_activity(t: Transport) -> str | None:
    out = t.shell(["dumpsys", "activity", "activities"]).stdout
    match = _RESUMED_RE.search(out)
    return normalize_component(match.group(1)) if match else None


def configure_launcher(t: Transport, dock: list[str]) -> OpResult:
    """Envia o dock ao launcher Clean TV (receptor protegido; só o shell do ADB consegue)."""
    if not dock:
        return OpResult(True, "dock vazio: nada a enviar")
    for pkg in dock:
        check_package(pkg)
    result = t.shell(
        ["am", "broadcast", "-n", OUR_LAUNCHER_RECEIVER, "-a", OUR_LAUNCHER_CONFIGURE, "--es", "dock", ",".join(dock)]
    )
    return OpResult("result=-1" in result.stdout, result.output)


def get_setting(t: Transport, namespace: str, key: str) -> str | None:
    value = t.shell(["settings", "get", namespace, key]).stdout.strip()
    return None if value in ("", "null") else value


def put_setting(t: Transport, namespace: str, key: str, value: str) -> None:
    t.shell(["settings", "put", namespace, key, value])


def boot_completed(t: Transport) -> bool:
    return getprop(t, "sys.boot_completed") == "1"
