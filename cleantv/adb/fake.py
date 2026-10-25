"""TV simulada para os testes e para o modo `--simulate`.

Imita as saídas reais dos comandos que a ferramenta usa e permite injetar falhas:
queda de conexão depois de N comandos, pacote protegido, launcher que trava,
instalação recusada e o setupwraith do Google TV tomando o HOME.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from ..constants import (
    HOME_CATEGORY,
    LEANBACK_CATEGORY,
    OUR_LAUNCHER_HOME,
    OUR_LAUNCHER_PACKAGE,
    RESOLVER_ACTIVITY,
    SETUP_WIZARDS,
    STATE_NAMES,
    STOCK_LAUNCHERS,
)
from ..device import component_package, is_usable_launcher, normalize_component
from ..errors import CleanTvError, ConnectionLost
from .transport import ShellResult, is_read_only, validate_argv

PROFILES_DIR = Path(__file__).parent / "profiles"

DEFAULT_LAUNCHER_APK = {"name": OUR_LAUNCHER_PACKAGE, "system": False, "home": OUR_LAUNCHER_HOME}


def available_profiles() -> list[str]:
    return sorted(path.stem for path in PROFILES_DIR.glob("*.json"))


def load_profile(name: str) -> dict:
    path = PROFILES_DIR / f"{name}.json"
    if not path.is_file():
        raise CleanTvError(f"Perfil simulado desconhecido: {name}. Disponíveis: {', '.join(available_profiles())}")
    return json.loads(path.read_text(encoding="utf-8"))


def _short(component: str) -> str:
    """Forma curta do Android (ComponentName.flattenToShortString)."""
    pkg, _, cls = component.partition("/")
    return f"{pkg}/{cls[len(pkg):]}" if cls.startswith(pkg + ".") else component


@dataclass
class FakePackage:
    name: str
    system: bool = True
    state: int = 0
    home: str | None = None
    leanback: str | None = None
    protected: bool = False
    crashes: bool = False

    @property
    def enabled(self) -> bool:
        return self.state in (0, 1)


class FakeTv:
    def __init__(self, profile: dict, *, persist_path: Path | None = None):
        p = copy.deepcopy(profile)
        self.name: str = p.get("name", "sim")
        self.comment: str = p.get("_comment", "")
        self.address = f"sim:{self.name}"
        self.props: dict[str, str] = p["props"]
        self.features: list[str] = p.get("features", [])
        self.packages = {d["name"]: FakePackage(**d) for d in p["packages"]}
        self.settings: dict[str, dict[str, str]] = p.get("settings", {})
        self.preferred_home: str | None = p.get("preferred_home")
        self.supports_default_state: bool = p.get("supports_default_state", True)
        self.hijack_home_without_stock: bool = p.get("hijack_home_without_stock", False)
        self.refuse_install: bool = p.get("refuse_install", False)
        # Launchers de sistema podem declarar prioridade > 0 no HOME (a TCL real declara 2):
        # enquanto ativos, vencem qualquer preferência do usuário.
        self.stock_home_priority: int = p.get("stock_home_priority", 0)
        self.launcher_apk: dict = p.get("launcher_apk", dict(DEFAULT_LAUNCHER_APK))
        self.launcher_config: dict[str, str] = p.get("launcher_config", {})
        self.persist_path = persist_path
        self.online = True
        self.authorized = True
        self.fail_after: int | None = None
        self.commands: list[list[str]] = []
        self.installs: list[str] = []
        self.foreground = p.get("foreground") or self._resolve_home()

    # ---- persistência (modo --simulate) ----

    @classmethod
    def load(cls, name: str, data_dir: Path) -> "FakeTv":
        path = data_dir / "sim" / f"{name}.json"
        profile = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else load_profile(name)
        return cls(profile, persist_path=path)

    @staticmethod
    def reset(name: str, data_dir: Path) -> bool:
        load_profile(name)
        path = data_dir / "sim" / f"{name}.json"
        if path.is_file():
            path.unlink()
            return True
        return False

    def to_profile(self) -> dict:
        return {
            "name": self.name,
            "_comment": self.comment,
            "props": self.props,
            "features": self.features,
            "packages": [asdict(p) for p in self.packages.values()],
            "settings": self.settings,
            "preferred_home": self.preferred_home,
            "foreground": self.foreground,
            "supports_default_state": self.supports_default_state,
            "hijack_home_without_stock": self.hijack_home_without_stock,
            "refuse_install": self.refuse_install,
            "stock_home_priority": self.stock_home_priority,
            "launcher_apk": self.launcher_apk,
            "launcher_config": self.launcher_config,
        }

    def save(self) -> None:
        if self.persist_path:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)
            self.persist_path.write_text(json.dumps(self.to_profile(), indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- interface Transport ----

    def _tick(self) -> None:
        if not self.online:
            raise ConnectionLost("A TV simulada está offline.")
        if self.fail_after is not None:
            if self.fail_after <= 0:
                self.online = False
                raise ConnectionLost("Conexão simulada caiu (Wi-Fi).")
            self.fail_after -= 1

    def connect(self) -> str:
        if not self.online:
            raise ConnectionLost(f"Não foi possível conectar em {self.address}")
        return f"connected to {self.address}"

    def get_state(self) -> str:
        if not self.online:
            return "absent"
        return "device" if self.authorized else "unauthorized"

    def disconnect(self) -> None:
        pass

    def switch_to_usb(self) -> ShellResult:
        self._tick()
        self.online = False
        return ShellResult("restarting in USB mode\n")

    def install(self, apk_path: str) -> ShellResult:
        self._tick()
        self.installs.append(str(apk_path))
        if self.refuse_install:
            return ShellResult(
                "Performing Streamed Install\n",
                f"adb: failed to install {apk_path}: Failure [INSTALL_FAILED_USER_RESTRICTED: Install canceled by user]",
                1,
            )
        spec = dict(self.launcher_apk)
        self.packages[spec["name"]] = FakePackage(**spec)
        # Atualizar um app encerra o processo dele; uma versão que trava não volta ao primeiro plano.
        if spec.get("crashes") and component_package(self.foreground) == spec["name"]:
            self.foreground = None
        self.save()
        return ShellResult("Performing Streamed Install\nSuccess\n")

    def shell(self, argv: Sequence[str]) -> ShellResult:
        validate_argv(argv)
        self._tick()
        args = list(argv)
        self.commands.append(args)
        result = self._dispatch(args)
        if not is_read_only(args):
            self.save()
        return result

    # ---- comandos ----

    def _dispatch(self, args: list[str]) -> ShellResult:
        match args:
            case ["getprop"]:
                return ShellResult("".join(f"[{k}]: [{v}]\n" for k, v in sorted(self.props.items())))
            case ["getprop", key]:
                return ShellResult(self.props.get(key, "") + "\n")
            case ["pm", "list", "packages", *flags]:
                return self._list_packages(flags)
            case ["pm", "list", "features"]:
                return ShellResult("".join(f"feature:{f}\n" for f in self.features))
            case ["pm", ("disable-user" | "enable" | "default-state") as verb, "--user", "0", pkg]:
                return self._set_state(verb, pkg)
            case ["pm", ("disable-user" | "enable" | "default-state") as verb, pkg]:
                return self._set_state(verb, pkg)
            case ["pm", "uninstall", pkg]:
                return self._uninstall(pkg)
            case ["dumpsys", "package", pkg]:
                return self._dumpsys_package(pkg)
            case ["dumpsys", "activity", "activities"]:
                return self._dumpsys_activities()
            case ["cmd", "package", "resolve-activity", *rest]:
                return self._resolve_activity(rest)
            case ["cmd", "package", "query-activities", *rest]:
                return self._query_activities(rest)
            case ["cmd", "package", "set-home-activity", *rest]:
                return self._set_home(rest[-1])
            case ["settings", "get", namespace, key]:
                return ShellResult(self.settings.get(namespace, {}).get(key, "null") + "\n")
            case ["settings", "put", namespace, key, value]:
                self.settings.setdefault(namespace, {})[key] = value
                if (namespace, key, value) == ("global", "adb_enabled", "0"):
                    self.online = False  # o adbd desliga logo depois do comando
                return ShellResult("")
            case ["input", "keyevent", ("KEYCODE_HOME" | "3")]:
                self.foreground = self._resolve_home()
                return ShellResult("")
            case ["am", "start", *rest] if "-n" in rest:
                return self._am_start(rest[rest.index("-n") + 1])
            case ["am", "broadcast", *rest] if "-n" in rest:
                return self._broadcast(rest)
        return ShellResult("", f"/system/bin/sh: {args[0]}: inaccessible or not found", 127)

    def _list_packages(self, flags: list[str]) -> ShellResult:
        pkgs = list(self.packages.values())
        if "-s" in flags:
            pkgs = [p for p in pkgs if p.system]
        if "-3" in flags:
            pkgs = [p for p in pkgs if not p.system]
        if "-d" in flags:
            pkgs = [p for p in pkgs if not p.enabled]
        if "-e" in flags:
            pkgs = [p for p in pkgs if p.enabled]
        return ShellResult("".join(f"package:{p.name}\n" for p in sorted(pkgs, key=lambda p: p.name)))

    def _set_state(self, verb: str, pkg: str) -> ShellResult:
        p = self.packages.get(pkg)
        if p is None:
            return ShellResult(
                "",
                f"Exception occurred while executing '{verb}':\n"
                f"java.lang.IllegalArgumentException: Unknown package: {pkg}",
                255,
            )
        if verb == "default-state" and not self.supports_default_state:
            return ShellResult("", f"Unknown command: {verb}", 255)
        if verb == "disable-user" and p.protected:
            return ShellResult(
                "",
                "Exception occurred while executing 'disable-user':\n"
                f"java.lang.IllegalArgumentException: Cannot disable a protected package: {pkg}",
                255,
            )
        p.state = {"disable-user": 3, "enable": 1, "default-state": 0}[verb]
        if not p.enabled and component_package(self.foreground) == pkg:
            self.foreground = self._resolve_home()
        return ShellResult(f"Package {pkg} new state: {STATE_NAMES[p.state]}\n")

    def _uninstall(self, pkg: str) -> ShellResult:
        p = self.packages.get(pkg)
        if p is None or p.system:
            return ShellResult("Failure [DELETE_FAILED_INTERNAL_ERROR]\n", "", 1)
        del self.packages[pkg]
        if component_package(self.preferred_home) == pkg:
            self.preferred_home = None
        if component_package(self.foreground) == pkg:
            self.foreground = self._resolve_home()
        return ShellResult("Success\n")

    def _dumpsys_package(self, pkg: str) -> ShellResult:
        p = self.packages.get(pkg)
        if p is None:
            return ShellResult("Dexopt state:\n  Unable to find package: " + pkg + "\n")
        flags = "SYSTEM HAS_CODE" if p.system else "HAS_CODE ALLOW_CLEAR_USER_DATA"
        return ShellResult(
            "Packages:\n"
            f"  Package [{pkg}] (5f3a1c2):\n"
            "    userId=10042\n"
            f"    flags=[ {flags} ]\n"
            "    User 0: ceDataInode=4242 installed=true hidden=false suspended=false distractionFlags=0 "
            f"stopped=false notLaunched=false enabled={p.state} instant=false virtual=false\n"
        )

    def _dumpsys_activities(self) -> ShellResult:
        header = "ACTIVITY MANAGER ACTIVITIES (dumpsys activity activities)\n"
        if not self.foreground:
            return ShellResult(header + "  (nothing)\n")
        record = f"ActivityRecord{{9a8b7c u0 {_short(self.foreground)} t12}}"
        if int(self.props.get("ro.build.version.sdk", "30")) >= 29:
            body = f"Display #0 (activities from top to bottom):\n    topResumedActivity={record}\n  ResumedActivity: {record}\n"
        else:
            body = f"  Stack #1:\n    mResumedActivity: {record}\n"
        return ShellResult(header + body)

    @staticmethod
    def _category(rest: list[str]) -> str | None:
        return rest[rest.index("-c") + 1] if "-c" in rest else None

    def _resolve_activity(self, rest: list[str]) -> ShellResult:
        component = self._resolve_home() if self._category(rest) == HOME_CATEGORY else None
        if component is None:
            return ShellResult("No activity found\n")
        is_default = "false" if component == RESOLVER_ACTIVITY else "true"
        priority = self.stock_home_priority if component_package(component) in STOCK_LAUNCHERS else 0
        return ShellResult(
            f"priority={priority} preferredOrder=0 match=0x108000 specificIndex=-1 isDefault={is_default}\n{_short(component)}\n"
        )

    def _query_activities(self, rest: list[str]) -> ShellResult:
        category = self._category(rest)
        enabled = [p for p in self.packages.values() if p.enabled]
        if category == HOME_CATEGORY:
            comps = [p.home for p in enabled if p.home]
        elif category == LEANBACK_CATEGORY:
            comps = [p.leanback for p in enabled if p.leanback]
        else:
            comps = []
        if not comps:
            return ShellResult("No activities found\n")
        lines = [f"{len(comps)} activities found:"]
        for i, comp in enumerate(comps):
            lines += [
                f"  Activity #{i}:",
                "    priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=false",
                f"    {_short(comp)}",
            ]
        return ShellResult("\n".join(lines) + "\n")

    def _set_home(self, component: str) -> ShellResult:
        component = normalize_component(component)
        p = self.packages.get(component_package(component) or "")
        if p and p.enabled and p.home == component:
            self.preferred_home = component
            return ShellResult("Success\n")
        return ShellResult("", f"Error: component {component} not found", 255)

    def _am_start(self, component: str) -> ShellResult:
        component = normalize_component(component)
        p = self.packages.get(component_package(component) or "")
        started = f"Starting: Intent {{ cmp={_short(component)} }}\n"
        if p is None or not p.enabled or component not in (p.home, p.leanback):
            return ShellResult(started, f"Error: Activity class {{{component}}} does not exist.", 1)
        if not p.crashes:
            self.foreground = component
        elif component_package(self.foreground) == p.name:
            self.foreground = None  # o processo travou e levou junto a tela que estava aberta
        return ShellResult(started)

    def _broadcast(self, rest: list[str]) -> ShellResult:
        component = rest[rest.index("-n") + 1]
        extras = {rest[i + 1]: rest[i + 2] for i in range(len(rest) - 2) if rest[i] == "--es"}
        head = f"Broadcasting: Intent {{ cmp={component} }}\n"
        p = self.packages.get(component_package(component) or "")
        if p is None or not p.enabled:
            return ShellResult(head + "Broadcast completed: result=0\n")
        self.launcher_config.update(extras)
        return ShellResult(head + f'Broadcast completed: result=-1, data="dock={extras.get("dock", "")}"\n')

    def _resolve_home(self) -> str | None:
        candidates = [p.home for p in self.packages.values() if p.enabled and p.home]
        if not candidates:
            return None
        wizards = [c for c in candidates if component_package(c) in SETUP_WIZARDS]
        stock_enabled = any(self.packages[n].enabled for n in STOCK_LAUNCHERS if n in self.packages)
        if self.hijack_home_without_stock and wizards and not stock_enabled:
            return wizards[0]
        if self.stock_home_priority > 0:
            stock = [c for c in candidates if component_package(c) in STOCK_LAUNCHERS]
            if stock:
                return stock[0]
        if self.preferred_home in candidates:
            return self.preferred_home
        usable = [c for c in candidates if is_usable_launcher(c)]
        if len(usable) == 1:
            return usable[0]
        if not usable:
            return candidates[0]
        return RESOLVER_ACTIVITY  # mais de um launcher e nenhum padrão: o Android mostra o seletor
