"""Backup (ponto de restauração), plano de restauração e scripts autônomos.

O primeiro backup de cada TV é gravado como `original.json` e nunca é sobrescrito:
ele representa a TV antes de qualquer mudança. A restauração compara esse retrato
com o estado atual, então funciona mesmo se os diários se perderem.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import __version__, device
from .adb.transport import Transport
from .constants import OUR_LAUNCHER_PACKAGE, STOCK_LAUNCHERS
from .device import is_usable_launcher
from .inventory import Inventory
from .journal import DISABLE_PACKAGE, DISABLE_STOCK_LAUNCHER, Journal
from .paths import subdir
from .ui import UI

ORIGINAL_BACKUP = "original.json"


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def save_backup(inventory: Inventory, device_dir: Path, **meta) -> tuple[Path, Path, bool]:
    """Grava um retrato com data e hora e, se ainda não existir, o ponto de restauração original.

    Retorna (caminho do original, caminho do retrato, se o original foi criado agora).
    """
    backups = subdir(device_dir, "backups")
    payload = {
        "tool_version": __version__,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        **meta,
        "inventory": inventory.to_dict(),
    }
    stamp = backups / f"backup-{datetime.now():%Y%m%d-%H%M%S}.json"
    counter = 1
    while stamp.exists():
        counter += 1
        stamp = backups / f"backup-{datetime.now():%Y%m%d-%H%M%S}-{counter}.json"
    _write_json(stamp, payload)
    original = backups / ORIGINAL_BACKUP
    created = not original.exists()
    if created:
        _write_json(original, payload)
    return original, stamp, created


def load_backup(path: Path) -> tuple[Inventory, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Inventory.from_dict(payload.pop("inventory")), payload


def original_backup_path(device_dir: Path) -> Path | None:
    path = device_dir / "backups" / ORIGINAL_BACKUP
    return path if path.is_file() else None


def original_states(journals: list[Journal]) -> dict[str, int]:
    """Estado exato de cada pacote antes da primeira vez que a ferramenta mexeu nele."""
    states: dict[str, int] = {}
    for journal in journals:
        for action in journal.by_kind(DISABLE_PACKAGE, DISABLE_STOCK_LAUNCHER):
            if action.original_state is not None and action.target not in states:
                states[action.target] = action.original_state
    return states


def touched_packages(journals: list[Journal]) -> list[str]:
    """Pacotes que a ferramenta desativou (ou estava desativando quando parou)."""
    names: list[str] = []
    for journal in journals:
        for action in journal.by_kind(DISABLE_STOCK_LAUNCHER, DISABLE_PACKAGE):
            if action.status in ("done", "running") and action.target not in names:
                names.append(action.target)
    return sorted(names, key=lambda n: (n not in STOCK_LAUNCHERS, n))


@dataclass
class RestorePlan:
    enable: list[tuple[str, int | None]]
    set_home: str | None
    our_launcher_installed: bool
    missing: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.enable and not self.set_home and not self.our_launcher_installed


def build_restore_plan(backup: Inventory, current: Inventory, journals: list[Journal]) -> RestorePlan:
    states = original_states(journals)
    enable: list[tuple[str, int | None]] = []
    missing: list[str] = []
    for name, info in backup.packages.items():
        if not info.enabled:
            continue  # já estava desativado antes da ferramenta: continua como está
        now = current.packages.get(name)
        if now is None:
            missing.append(name)
        elif not now.enabled:
            enable.append((name, states.get(name)))
    enable.sort(key=lambda item: (item[0] not in STOCK_LAUNCHERS, item[0]))  # launcher original primeiro
    set_home = None
    if is_usable_launcher(backup.home_component) and current.home_component != backup.home_component:
        set_home = backup.home_component
    ours = OUR_LAUNCHER_PACKAGE in current.packages and OUR_LAUNCHER_PACKAGE not in backup.packages
    return RestorePlan(enable, set_home, ours, sorted(missing))


def execute_restore(t: Transport, plan: RestorePlan, ui: UI, *, uninstall_ours: bool) -> None:
    for name, state in plan.enable:
        result = device.restore_state(t, name, state)
        if result.ok:
            ui.say(f"  ok        {name}")
        else:
            ui.warn(f"  falhou    {name}: {result.message.strip().splitlines()[-1] if result.message.strip() else ''}")
    if plan.set_home:
        result = device.set_home_activity(t, plan.set_home)
        ui.say(f"  {'ok' if result.ok else 'falhou':<9} HOME de volta para {plan.set_home}")
    if uninstall_ours and plan.our_launcher_installed:
        # Única desinstalação que a ferramenta faz: o próprio launcher, nunca outro pacote.
        result = t.shell(["pm", "uninstall", OUR_LAUNCHER_PACKAGE])
        ui.say(f"  {'ok' if 'Success' in result.output else 'falhou':<9} launcher Clean TV removido")
    device.press_home(t)


def verify_restore(backup: Inventory, after: Inventory) -> list[str]:
    problems = []
    for name, info in sorted(backup.packages.items()):
        now = after.packages.get(name)
        if info.enabled and now is not None and not now.enabled:
            problems.append(f"{name} continua desativado")
    if is_usable_launcher(backup.home_component) and after.home_component != backup.home_component:
        problems.append(f"o HOME está em {after.home_component}, esperado {backup.home_component}")
    return problems


def _ascii(text: str) -> str:
    """O cmd.exe não lida bem com acentos: 'ç' vira 'c', travessão vira hífen."""
    text = text.replace("—", "-").replace("–", "-")
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return text.encode("ascii", "replace").decode("ascii")


def write_restore_scripts(
    device_dir: Path, *, address: str, adb_path: str | None, backup: Inventory, journals: list[Journal]
) -> tuple[Path, Path]:
    """Scripts de emergência que só dependem do adb (sem Python)."""
    packages = touched_packages(journals)
    home = backup.home_component if is_usable_launcher(backup.home_component) else None
    stamp = datetime.now().isoformat(timespec="seconds")
    label = _ascii(backup.identity.label())
    simulated = address.startswith("sim:")

    cmd = [
        "@echo off",
        "rem Clean TV - restauracao de emergencia (so precisa do adb)",
        f"rem Gerado em {stamp} para: {label}",
        "rem Reativa os pacotes desativados pela ferramenta e devolve a tela inicial original.",
        f"rem Uso: restaurar.cmd [IP:PORTA]   (padrao: {address})",
    ]
    if simulated:
        cmd.append("rem ATENCAO: gerado para uma TV SIMULADA; nao funciona com uma TV real.")
    cmd += [
        "setlocal",
        f'set "ADB={adb_path or "adb"}"',
        'set "TV=%~1"',
        f'if "%TV%"=="" set "TV={address}"',
        '"%ADB%" connect %TV%',
    ]
    cmd += [f'"%ADB%" -s %TV% shell pm enable {name}' for name in packages]
    if home:
        cmd.append(f'"%ADB%" -s %TV% shell cmd package set-home-activity --user 0 {home}')
    cmd += [
        '"%ADB%" -s %TV% shell input keyevent KEYCODE_HOME',
        'rem Para remover tambem o launcher do Clean TV, apague o "rem" da linha abaixo:',
        f'rem "%ADB%" -s %TV% shell pm uninstall {OUR_LAUNCHER_PACKAGE}',
        "echo Restauracao concluida. Confira a TV.",
        "endlocal",
    ]

    sh = [
        "#!/bin/sh",
        "# Clean TV - restauracao de emergencia (so precisa do adb)",
        f"# Gerado em {stamp} para: {label}",
        f"# Uso: sh restaurar.sh [IP:PORTA]   (padrao: {address})",
    ]
    if simulated:
        sh.append("# ATENCAO: gerado para uma TV SIMULADA; nao funciona com uma TV real.")
    sh += ['ADB="${ADB:-adb}"', f'TV="${{1:-{address}}}"', '"$ADB" connect "$TV"']
    sh += [f'"$ADB" -s "$TV" shell pm enable {name}' for name in packages]
    if home:
        sh.append(f'"$ADB" -s "$TV" shell cmd package set-home-activity --user 0 {home}')
    sh += [
        '"$ADB" -s "$TV" shell input keyevent KEYCODE_HOME',
        "# Para remover tambem o launcher do Clean TV, descomente a linha abaixo:",
        f'# "$ADB" -s "$TV" shell pm uninstall {OUR_LAUNCHER_PACKAGE}',
        'echo "Restauracao concluida. Confira a TV."',
    ]

    cmd_path = device_dir / "restaurar.cmd"
    sh_path = device_dir / "restaurar.sh"
    cmd_path.write_text("\r\n".join(_ascii(line) for line in cmd) + "\r\n", encoding="ascii", newline="")
    sh_path.write_text("\n".join(_ascii(line) for line in sh) + "\n", encoding="ascii", newline="\n")
    return cmd_path, sh_path
