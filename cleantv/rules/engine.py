"""Carrega as regras TOML e classifica cada pacote.

Ordem de decisão:
  1. proteção interna (safety.py)
  2. regra exata pelo nome (arquivo de marca/modelo vence o comum)
  3. regra por prefixo (o mais longo vence)
  4. heurística protetora pelo nome
  5. heurística suspeita pelo nome (sempre opcional, nunca em android/com.android/com.google.android)
  6. app instalado pelo usuário: manter
  7. sem regra: não tocar
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..device import DeviceIdentity
from ..errors import CleanTvError
from ..inventory import Inventory, PackageInfo
from .safety import hard_protection

DATA_DIR = Path(__file__).parent / "data"

CATEGORIES = {
    "ads": "Anúncios / conteúdo patrocinado",
    "telemetry": "Telemetria / rastreamento",
    "bloatware": "Possível bloatware",
    "keep": "Manter",
    "critical": "Sistema crítico (protegido)",
    "unknown": "Não classificado: não tocar",
}
ACTIONS = ("disable", "ask", "keep", "protect")
CONFIDENCES = ("high", "medium", "low")
CHOICE_GROUPS = {
    "assistant": "o Assistente e a busca por voz",
    "chromecast": "o Chromecast (transmitir do celular para a TV)",
    "updates": "as atualizações automáticas",
    "screensaver": "o protetor de tela / modo ambiente original",
}
PLATFORMS = ("google_tv", "android_tv", "android_tv_vendor", "unknown")
STATUSES = ("validado", "parcial", "nao-validado")

_RULE_KEYS = {
    "package", "prefix", "category", "action", "confidence", "reason", "risk", "choice_group",
    "platforms", "min_sdk", "max_sdk", "models", "override_protection",
}
_META_KEYS = {"name", "brand", "status", "match_manufacturer", "notes"}


@dataclass(frozen=True)
class Rule:
    match: str
    is_prefix: bool
    category: str
    action: str
    confidence: str
    reason: str
    risk: str = ""
    choice_group: str | None = None
    platforms: tuple[str, ...] = ()
    min_sdk: int | None = None
    max_sdk: int | None = None
    models: tuple[str, ...] = ()
    override_protection: bool = False
    source: str = ""

    def matches(self, package: str) -> bool:
        return package.startswith(self.match) if self.is_prefix else package == self.match

    def applies_to(self, identity: DeviceIdentity, platform: str) -> bool:
        if self.platforms and platform not in self.platforms:
            return False
        if self.min_sdk is not None and identity.sdk < self.min_sdk:
            return False
        if self.max_sdk is not None and identity.sdk > self.max_sdk:
            return False
        if self.models and not any(re.search(p, identity.model, re.IGNORECASE) for p in self.models):
            return False
        return True


@dataclass(frozen=True)
class Classification:
    package: str
    category: str
    action: str
    confidence: str
    reason: str
    risk: str = ""
    source: str = ""
    choice_group: str | None = None
    override_protection: bool = False

    @property
    def category_label(self) -> str:
        return CATEGORIES[self.category]


@dataclass(frozen=True)
class RuleFile:
    path: Path
    meta: dict
    rules: tuple[Rule, ...]

    @property
    def label(self) -> str:
        return self.meta.get("name", self.path.stem)

    @property
    def status(self) -> str:
        return self.meta.get("status", "nao-validado")


def _invalid(path: Path, message: str) -> CleanTvError:
    return CleanTvError(f"Regra inválida em {path.name}: {message}")


def _parse_rule(path: Path, index: int, raw: dict) -> Rule:
    where = f"regra #{index}"
    extra = set(raw) - _RULE_KEYS
    if extra:
        raise _invalid(path, f"{where}: campos desconhecidos {sorted(extra)}")
    if ("package" in raw) == ("prefix" in raw):
        raise _invalid(path, f"{where}: use exatamente um de 'package' ou 'prefix'")
    match = raw.get("package") or raw.get("prefix")
    category, action = raw.get("category"), raw.get("action")
    confidence = raw.get("confidence", "low")
    group = raw.get("choice_group")
    if category not in CATEGORIES:
        raise _invalid(path, f"{where} ({match}): category deve ser um de {sorted(CATEGORIES)}")
    if action not in ACTIONS:
        raise _invalid(path, f"{where} ({match}): action deve ser um de {list(ACTIONS)}")
    if confidence not in CONFIDENCES:
        raise _invalid(path, f"{where} ({match}): confidence deve ser um de {list(CONFIDENCES)}")
    if group is not None and group not in CHOICE_GROUPS:
        raise _invalid(path, f"{where} ({match}): choice_group deve ser um de {sorted(CHOICE_GROUPS)}")
    if not str(raw.get("reason", "")).strip():
        raise _invalid(path, f"{where} ({match}): 'reason' é obrigatório")
    # Política do projeto: só é proposto automaticamente o que tem confiança alta, ou o que
    # depende de uma pergunta explícita ao usuário (grupo de escolha).
    if action == "disable" and confidence != "high" and group is None:
        raise _invalid(path, f"{where} ({match}): action='disable' exige confidence='high'; use 'ask'")
    if raw.get("override_protection") and action != "ask":
        raise _invalid(path, f"{where} ({match}): override_protection exige action='ask'")
    platforms = tuple(raw.get("platforms", ()))
    if set(platforms) - set(PLATFORMS):
        raise _invalid(path, f"{where} ({match}): plataformas válidas: {list(PLATFORMS)}")
    models = tuple(raw.get("models", ()))
    for pattern in models:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise _invalid(path, f"{where} ({match}): regex de modelo inválida {pattern!r}: {exc}") from exc
    return Rule(
        match=match,
        is_prefix="prefix" in raw,
        category=category,
        action=action,
        confidence=confidence,
        reason=raw["reason"].strip(),
        risk=raw.get("risk", "").strip(),
        choice_group=group,
        platforms=platforms,
        min_sdk=raw.get("min_sdk"),
        max_sdk=raw.get("max_sdk"),
        models=models,
        override_protection=bool(raw.get("override_protection", False)),
        source=path.name,
    )


def load_rule_file(path: Path) -> RuleFile:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise _invalid(path, str(exc)) from exc
    unknown = set(data) - {"meta", "rule"}
    if unknown:
        raise _invalid(path, f"seções desconhecidas {sorted(unknown)}")
    meta = data.get("meta", {})
    if set(meta) - _META_KEYS:
        raise _invalid(path, f"campos desconhecidos em [meta]: {sorted(set(meta) - _META_KEYS)}")
    if meta.get("status", "nao-validado") not in STATUSES:
        raise _invalid(path, f"status deve ser um de {list(STATUSES)}")
    rules: list[Rule] = []
    seen: set[tuple[str, bool]] = set()
    for index, raw in enumerate(data.get("rule", []), 1):
        rule = _parse_rule(path, index, raw)
        key = (rule.match, rule.is_prefix)
        if key in seen and not (rule.models or rule.platforms or rule.min_sdk or rule.max_sdk):
            raise _invalid(path, f"regra duplicada para {rule.match}")
        seen.add(key)
        rules.append(rule)
    return RuleFile(path, meta, tuple(rules))


# ---- heurísticas pelo nome ----

_PROTECT_TOKENS = {
    "ota", "fota", "update", "updater", "upgrade", "systemupdate", "updatecenter",
    "wifi", "wlan", "ethernet", "network", "networkstack", "connectivity", "netd", "dhcp", "tethering",
    "bluetooth", "bt", "tvinput", "input", "inputs", "hdmi", "cec", "tuner", "dtv", "atv", "tvservice", "livetv",
    "setup", "setupwizard", "provision", "oobe", "settings", "factory", "factorytest", "remote", "rcu",
    "ime", "keyboard", "inputmethod", "launcher", "home", "tvhome",
}
# Trechos que protegem mesmo grudados em outras palavras (ex.: com.tcl.versionUpdateApp,
# com.tcl.initsetup). Proteger a mais é sempre seguro.
_PROTECT_SUBSTRINGS = (
    "update", "upgrade", "setup", "provision", "factory", "overlay", "bluetooth", "wifi", "ethernet",
    "network", "netstate", "inputmethod", "keyboard", "launcher", "tvinput", "passthrough", "autopair", "settings",
)
_SUSPECT_TOKENS = {
    "ads": "ads", "ad": "ads", "adservice": "ads", "adsdk": "ads", "advert": "ads", "advertising": "ads",
    "promo": "ads", "promotion": "ads",
    "analytics": "telemetry", "telemetry": "telemetry", "tracking": "telemetry", "tracker": "telemetry",
    "acr": "telemetry", "inscape": "telemetry", "statistics": "telemetry", "datacollection": "telemetry",
    "datacollect": "telemetry", "logcollector": "telemetry", "bigdata": "telemetry",
}
_PLATFORM_NAMESPACES = ("android.", "com.android.", "com.google.android.")


def classify_by_name(package: str) -> Classification | None:
    lowered = package.lower()
    tokens = set(re.split(r"[._]+", lowered))
    protect = sorted(tokens & _PROTECT_TOKENS) or [s for s in _PROTECT_SUBSTRINGS if s in lowered]
    if protect:
        return Classification(
            package, "critical", "protect", "medium",
            f"O nome indica componente essencial ('{protect[0]}'): protegido por precaução.",
            source="heurística",
        )
    if package == "android" or package.startswith(_PLATFORM_NAMESPACES):
        return None
    suspect = sorted(tokens & set(_SUSPECT_TOKENS))
    if suspect:
        category = _SUSPECT_TOKENS[suspect[0]]
        return Classification(
            package, category, "ask", "low",
            f"O nome sugere {CATEGORIES[category].lower()} ('{suspect[0]}'). Heurística NÃO verificada: "
            "só desative se você reconhecer o pacote.",
            risk="Efeito desconhecido; reversível com cleantv restore.",
            source="heurística",
        )
    return None


# ---- conjunto de regras ----


@dataclass
class RuleSet:
    files: list[RuleFile]  # em ordem crescente de prioridade

    def _explicit(self, package: str, identity: DeviceIdentity, platform: str) -> Rule | None:
        exact: Rule | None = None
        prefix: Rule | None = None
        for rule_file in self.files:
            for rule in rule_file.rules:
                if not rule.matches(package) or not rule.applies_to(identity, platform):
                    continue
                if not rule.is_prefix:
                    exact = rule
                elif prefix is None or len(rule.match) >= len(prefix.match):
                    prefix = rule
        return exact or prefix

    def classify(self, info: PackageInfo, identity: DeviceIdentity, platform: str) -> Classification:
        rule = self._explicit(info.name, identity, platform)
        protected = hard_protection(info.name)
        if protected and not (rule and rule.override_protection):
            return Classification(info.name, "critical", "protect", "high", protected, source="proteção interna")
        if rule:
            return Classification(
                info.name, rule.category, rule.action, rule.confidence, rule.reason, rule.risk,
                rule.source, rule.choice_group, rule.override_protection,
            )
        by_name = classify_by_name(info.name)
        if by_name:
            return by_name
        if not info.system:
            return Classification(info.name, "keep", "keep", "high", "App instalado por você: a ferramenta não mexe.", source="padrão")
        return Classification(info.name, "unknown", "keep", "low", "Sem regra para este pacote: por segurança, não tocar.", source="padrão")

    def classify_all(self, inventory: Inventory) -> dict[str, "Classification"]:
        return {
            name: self.classify(info, inventory.identity, inventory.platform)
            for name, info in inventory.packages.items()
        }


def brand_rule_files() -> list[Path]:
    return sorted((DATA_DIR / "brands").glob("*.toml"))


def _brand_matches(rule_file: RuleFile, identity: DeviceIdentity | None, declared_brand: str | None) -> bool:
    keys = [k.lower() for k in rule_file.meta.get("match_manufacturer", [])]
    parts = [declared_brand or ""]
    if identity:
        parts += [identity.manufacturer, identity.brand]
    haystack = " ".join(parts).lower()
    return any(key in haystack for key in keys)


def load_ruleset(
    identity: DeviceIdentity | None, declared_brand: str | None = None, extra_dirs: Iterable[Path] = ()
) -> RuleSet:
    files = [load_rule_file(DATA_DIR / "common.toml")]
    for path in brand_rule_files():
        rule_file = load_rule_file(path)
        if _brand_matches(rule_file, identity, declared_brand):
            files.append(rule_file)
    for directory in extra_dirs:
        files += [load_rule_file(path) for path in sorted(Path(directory).glob("*.toml"))]
    return RuleSet(files)
