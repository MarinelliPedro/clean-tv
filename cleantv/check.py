"""Verificação depois de atualizações: o que a ferramenta aplicou continua aplicado?

Atualizações de sistema (OTA) costumam reativar pacotes desativados e às vezes trazem o launcher
original de volta. O `check` compara, sem alterar nada:
  - o que as execuções aplicaram (diários em runs/, menos os desfeitos com restore);
  - o ponto de restauração original (o que existia antes da ferramenta);
  - o estado atual da TV.
Com --apply, monta um plano só com o que voltou e o aplica pelo executor de sempre
(lotes, verificação e rollback).
"""

from __future__ import annotations

from dataclasses import dataclass

from .constants import OUR_LAUNCHER_HOME, OUR_LAUNCHER_PACKAGE
from .device import is_usable_launcher
from .inventory import Inventory
from .journal import (
    DISABLE_PACKAGE,
    DISABLE_STOCK_LAUNCHER,
    INSTALL_LAUNCHER,
    SET_HOME,
    VALIDATE_LAUNCHER,
    Action,
    Journal,
)
from .planner import CHOICE, Change, Choices, LauncherStep, Plan, safety_block
from .rules.engine import Classification

SUGGESTED_CATEGORIES = ("ads", "telemetry", "bloatware")


@dataclass
class Applied:
    """O que as execuções deixaram aplicado na TV (a execução mais recente vale)."""

    disabled: dict[str, Action]  # pacote -> ação que o desativou (guarda categoria e motivo)
    stock_launcher: str | None
    home_ours: bool
    launcher_installed: bool

    @property
    def is_empty(self) -> bool:
        return not self.disabled and not self.stock_launcher and not self.home_ours and not self.launcher_installed


def applied_state(journals: list[Journal]) -> Applied:
    disabled: dict[str, Action] = {}
    stock: str | None = None
    home_ours = False
    installed = False
    for journal in journals:
        if journal.status == "restored":
            continue
        for action in journal.actions:
            if action.kind == VALIDATE_LAUNCHER and action.status == "failed" and journal.fallback_launcher:
                # Atualização do launcher que não abriu: o launcher original foi reativado de propósito.
                stock, home_ours = None, False
            if action.status != "done":
                continue
            if action.kind == DISABLE_PACKAGE:
                disabled[action.target] = action
            elif action.kind == DISABLE_STOCK_LAUNCHER:
                stock = action.target
            elif action.kind == SET_HOME:
                home_ours = action.target == OUR_LAUNCHER_HOME
            elif action.kind == INSTALL_LAUNCHER:
                installed = True
    return Applied(disabled, stock, home_ours, installed)


@dataclass
class Drift:
    system_update: tuple[str, str] | None  # (build do ponto de restauração, build atual)
    reenabled: list[str]  # desativados pela ferramenta que voltaram a ficar ativos
    blocked: list[tuple[str, str]]  # reativados que as regras de hoje protegem: não são reaplicados
    gone: list[str]  # desativados pela ferramenta que não estão mais instalados
    stock_reenabled: str | None
    home: str | None  # HOME atual, quando deveria ser o Clean TV
    launcher_missing: bool
    new_suggested: list[Classification]  # pacotes novos desde o backup que as regras sugerem revisar

    @property
    def fixable(self) -> bool:
        return bool(self.reenabled or self.stock_reenabled or self.home)

    @property
    def ok(self) -> bool:
        return not (self.fixable or self.launcher_missing)


def find_drift(applied: Applied, backup: Inventory, current: Inventory, classes: dict[str, Classification]) -> Drift:
    reenabled: list[str] = []
    blocked: list[tuple[str, str]] = []
    gone: list[str] = []
    for name in sorted(applied.disabled):
        info = current.packages.get(name)
        if info is None:
            gone.append(name)
        elif info.enabled:
            reason = safety_block(name, current, classes.get(name), Choices())
            if reason:
                blocked.append((name, reason))
            else:
                reenabled.append(name)

    stock = applied.stock_launcher
    stock_reenabled = stock if stock and stock in current.packages and current.packages[stock].enabled else None
    ours = current.packages.get(OUR_LAUNCHER_PACKAGE)
    launcher_missing = applied.launcher_installed and (ours is None or not ours.enabled)
    home = current.home_component if applied.home_ours and current.home_component != OUR_LAUNCHER_HOME else None

    new_suggested = []
    for name in sorted(set(current.packages) - set(backup.packages) - {OUR_LAUNCHER_PACKAGE}):
        cls = classes.get(name)
        if cls and cls.category in SUGGESTED_CATEGORIES and cls.action in ("disable", "ask"):
            if not safety_block(name, current, cls, Choices()):
                new_suggested.append(cls)

    before, now = backup.identity.fingerprint, current.identity.fingerprint
    return Drift(
        system_update=(before, now) if before and now and before != now else None,
        reenabled=reenabled,
        blocked=blocked,
        gone=gone,
        stock_reenabled=stock_reenabled,
        home=home,
        launcher_missing=launcher_missing,
        new_suggested=new_suggested,
    )


def reapply_plan(drift: Drift, applied: Applied, current: Inventory, *, address: str, batch_size: int = 5) -> Plan:
    """Plano só com o que voltou: os mesmos pacotes, com a categoria e o motivo da primeira vez."""
    changes = []
    for i, name in enumerate(drift.reenabled):
        action = applied.disabled[name]
        reason = action.reason or "Desativado antes por você com esta ferramenta."
        changes.append(Change(name, action.category or CHOICE, reason, "", "check", batch=i // batch_size + 1))

    launcher = None
    if (drift.stock_reenabled or drift.home) and not drift.launcher_missing:
        # O Clean TV continua instalado: só abrir e validar, fixar o HOME e desativar o original de novo.
        original = current.home_component
        launcher = LauncherStep(
            apk="",
            component=OUR_LAUNCHER_HOME,
            original_home=original if is_usable_launcher(original) and original != OUR_LAUNCHER_HOME else None,
            stock_launcher=drift.stock_reenabled,
        )
    return Plan(
        device_id=current.identity.device_id,
        address=address,
        changes=changes,
        launcher=launcher,
        dock=[],
        skipped=[(name, reason) for name, reason in drift.blocked],
        batch_size=batch_size,
    )
