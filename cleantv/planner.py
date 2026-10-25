"""Transforma classificações + escolhas do usuário em um plano de mudanças em lotes.

O planejador é a última barreira antes do executor: mesmo que uma escolha ou regra
peça, ele nunca inclui launcher, quem responde ao HOME, assistente de configuração,
pacote protegido ou pacote já desativado. Tudo que for barrado vai para `skipped`
com o motivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .constants import OUR_LAUNCHER_HOME, OUR_LAUNCHER_PACKAGE, SETUP_WIZARDS, STOCK_LAUNCHERS
from .device import component_package, is_usable_launcher
from .inventory import Inventory
from .rules.engine import CATEGORIES, CHOICE_GROUPS, Classification
from .rules.safety import hard_protection

# Categoria só do plano: itens que entram por resposta sua (grupo desligado ou app escondido).
CHOICE = "choice"
CATEGORY_LABELS = {**CATEGORIES, CHOICE: "Sua escolha"}
CATEGORY_ORDER = ("ads", "telemetry", "bloatware", CHOICE, "keep", "unknown", "critical")

# Apps de streaming sugeridos para o dock, nesta ordem, quando instalados.
DOCK_SUGGESTIONS = (
    "com.google.android.youtube.tv",
    "com.netflix.ninja",
    "com.amazon.amazonvideo.livingroom",
    "com.disney.disneyplus",
    "com.hbo.hbonow",
    "com.wbd.stream",
    "com.globo.globotv",
    "com.spotify.tv.android",
)
DOCK_SIZE = 4


@dataclass
class Choices:
    keep_groups: dict[str, bool] = field(default_factory=dict)  # grupo -> True para manter
    opt_in: set[str] = field(default_factory=set)  # itens opcionais que você marcou
    opt_out: set[str] = field(default_factory=set)  # itens recomendados que você desmarcou
    hide_apps: set[str] = field(default_factory=set)  # apps da tela inicial que você quer esconder
    confirmed_overrides: set[str] = field(default_factory=set)  # pacotes protegidos confirmados por digitação
    dock: list[str] = field(default_factory=list)
    launcher_apk: str | None = None
    launcher_set_home: bool = True  # False = instala e testa, mas o HOME continua no launcher original
    disable_stock_launcher: bool = False


@dataclass
class Change:
    package: str
    category: str
    reason: str
    risk: str
    source: str
    batch: int = 0

    def undo_command(self, address: str) -> str:
        return f"adb -s {address} shell pm enable {self.package}"


@dataclass
class LauncherStep:
    apk: str  # vazio: o Clean TV já está instalado e não é reinstalado
    component: str
    original_home: str | None
    stock_launcher: str | None  # pacote do launcher original a desativar; None = manter instalado e ativo
    set_home: bool = True  # False = o HOME fica fixado no launcher original
    # Atualização com o Clean TV já como HOME: launcher original (desativado) que volta a ser ativado
    # se a versão nova não abrir, para a TV nunca ficar sem tela inicial.
    fallback_launcher: str | None = None

    @property
    def home_target(self) -> str | None:
        return self.component if self.set_home else self.original_home


@dataclass
class Plan:
    device_id: str
    address: str
    changes: list[Change]
    launcher: LauncherStep | None
    dock: list[str]
    skipped: list[tuple[str, str]]
    batch_size: int

    @property
    def batches(self) -> list[list[Change]]:
        result: dict[int, list[Change]] = {}
        for change in self.changes:
            result.setdefault(change.batch, []).append(change)
        return [result[k] for k in sorted(result)]

    @property
    def is_empty(self) -> bool:
        return not self.changes and self.launcher is None


@dataclass
class Candidates:
    recommended: list[Classification]  # action=disable, sem grupo
    optional: list[Classification]  # action=ask, sem grupo
    groups: dict[str, list[Classification]]
    apps: list[str]  # apps na tela inicial que o usuário pode escolher esconder


def safety_block(name: str, inventory: Inventory, cls: Classification | None, choices: Choices) -> str | None:
    """Motivo para nunca incluir este pacote no plano de desativação (ou None)."""
    overridden = bool(cls and cls.override_protection and name in choices.confirmed_overrides)
    reason = hard_protection(name)
    if reason and not overridden:
        return reason
    if name in SETUP_WIZARDS:
        return "Assistente de configuração: nunca é desativado."
    if name in STOCK_LAUNCHERS or name == inventory.home_package:
        return "Launcher: só é desativado na etapa de troca de launcher, depois de validar o novo."
    info = inventory.packages.get(name)
    if info and info.home:
        return "Responde ao botão HOME: desativar pode deixar a TV sem tela inicial."
    if name == OUR_LAUNCHER_PACKAGE:
        return "Launcher do Clean TV."
    if cls and cls.action == "protect":
        return cls.reason
    if info is None:
        return "Pacote não está instalado."
    if not info.enabled:
        return "Já está desativado."
    return None


def find_candidates(inventory: Inventory, classifications: dict[str, Classification]) -> Candidates:
    recommended, optional = [], []
    groups: dict[str, list[Classification]] = {}
    empty = Choices()
    for name in sorted(classifications):
        cls = classifications[name]
        if safety_block(name, inventory, cls, empty) and not cls.override_protection:
            continue
        if cls.choice_group:
            groups.setdefault(cls.choice_group, []).append(cls)
        elif cls.action == "disable":
            recommended.append(cls)
        elif cls.action == "ask":
            optional.append(cls)
    proposed = {c.package for c in recommended + optional} | {c.package for g in groups.values() for c in g}
    apps = []
    for info in inventory.launchable_apps():
        cls = classifications.get(info.name)
        if cls is None or info.name in proposed or cls.action == "protect":
            continue
        if not safety_block(info.name, inventory, cls, empty):
            apps.append(info.name)
    return Candidates(recommended, optional, groups, apps)


def suggest_dock(inventory: Inventory, exclude: set[str]) -> list[str]:
    available = [p.name for p in inventory.launchable_apps() if p.name not in exclude]
    ordered = [name for name in DOCK_SUGGESTIONS if name in available]
    ordered += [name for name in available if name not in ordered]
    return ordered[:DOCK_SIZE]


def _wants_disable(cls: Classification, choices: Choices) -> bool:
    if cls.override_protection:
        return cls.package in choices.confirmed_overrides and cls.package in choices.opt_in
    if cls.action == "protect":
        return False
    if cls.choice_group:
        if choices.keep_groups.get(cls.choice_group, True):
            return False
        return cls.action == "disable" or cls.package in choices.opt_in
    if cls.action == "disable":
        return cls.package not in choices.opt_out
    if cls.action == "ask":
        return cls.package in choices.opt_in
    return cls.package in choices.hide_apps


def _describe(cls: Classification, choices: Choices) -> tuple[Classification, str, str, str]:
    """Categoria, motivo e risco como aparecem no plano."""
    if cls.choice_group and not choices.keep_groups.get(cls.choice_group, True):
        return cls, CHOICE, f"Você escolheu não manter {CHOICE_GROUPS[cls.choice_group]}. {cls.reason}", cls.risk
    if cls.action == "keep" and cls.package in choices.hide_apps:
        return cls, CHOICE, "Você escolheu esconder este app.", cls.risk or "O app some da tela inicial até ser reativado."
    return cls, cls.category, cls.reason, cls.risk


def build_plan(
    inventory: Inventory,
    classifications: dict[str, Classification],
    choices: Choices,
    *,
    address: str,
    batch_size: int = 5,
) -> Plan:
    if batch_size < 1:
        raise ValueError("batch_size precisa ser >= 1")
    selected: list[Classification] = []
    skipped: list[tuple[str, str]] = []
    requested = set(choices.opt_in) | set(choices.hide_apps) | set(choices.confirmed_overrides)
    for name, cls in classifications.items():
        wanted = _wants_disable(cls, choices)
        if not wanted and name not in requested:
            continue
        blocked = safety_block(name, inventory, cls, choices)
        if blocked:
            skipped.append((name, blocked))
        elif wanted:
            selected.append(cls)
        else:
            skipped.append((name, "Não incluído: conflita com outra escolha (por exemplo, um recurso que você decidiu manter)."))
    for name in sorted(requested - set(classifications)):
        skipped.append((name, "Pacote não está instalado."))

    order = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}
    described = sorted((_describe(c, choices) for c in selected), key=lambda d: (order.get(d[1], 99), d[0].package))
    changes = [
        Change(c.package, category, reason, risk, c.source, batch=i // batch_size + 1)
        for i, (c, category, reason, risk) in enumerate(described)
    ]

    launcher = None
    if choices.launcher_apk:
        stock = inventory.home_package if inventory.home_package in STOCK_LAUNCHERS else None
        fallback = None
        if inventory.home_package == OUR_LAUNCHER_PACKAGE:
            fallback = next((p for p in STOCK_LAUNCHERS if p in inventory.packages and not inventory.packages[p].enabled), None)
        launcher = LauncherStep(
            apk=choices.launcher_apk,
            component=OUR_LAUNCHER_HOME,
            original_home=inventory.home_component if is_usable_launcher(inventory.home_component) else None,
            stock_launcher=stock if choices.disable_stock_launcher and choices.launcher_set_home else None,
            set_home=choices.launcher_set_home,
            fallback_launcher=fallback,
        )
        if choices.disable_stock_launcher and not choices.launcher_set_home:
            skipped.append((stock or "launcher original", "Só é desativado quando o Clean TV vira a tela inicial."))
        elif choices.disable_stock_launcher and stock is None:
            skipped.append(
                (component_package(inventory.home_component) or "launcher original",
                 "O launcher atual não é um launcher original conhecido: ele não será desativado.")
            )

    hidden = {c.package for c in changes}
    dock = [name for name in choices.dock if name not in hidden][:DOCK_SIZE]
    return Plan(
        device_id=inventory.identity.device_id,
        address=address,
        changes=changes,
        launcher=launcher,
        dock=dock,
        skipped=sorted(set(skipped)),
        batch_size=batch_size,
    )
