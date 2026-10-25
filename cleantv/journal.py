"""Diário de execução: cada ação é gravada em disco antes e depois de ir para a TV.

Se a conexão cair no meio, o diário diz exatamente onde parou e qual era o estado
original de cada pacote, para `resume` e `restore`.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .paths import subdir

log = logging.getLogger(__name__)

# Tipos de ação
DISABLE_PACKAGE = "disable_package"
INSTALL_LAUNCHER = "install_launcher"
VALIDATE_LAUNCHER = "validate_launcher"
CONFIGURE_LAUNCHER = "configure_launcher"
SET_HOME = "set_home"
DISABLE_STOCK_LAUNCHER = "disable_stock_launcher"

# Status de ação: planned -> running -> done | failed | skipped | rolled_back
FINISHED = ("done", "failed", "skipped", "rolled_back")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Action:
    id: int
    kind: str
    target: str
    batch: int = 0
    status: str = "planned"
    original_state: int | None = None
    message: str = ""
    updated_at: str = ""
    category: str = ""
    reason: str = ""


@dataclass
class Journal:
    run_id: str
    device_id: str
    address: str
    backup_path: str
    batch_size: int
    actions: list[Action]
    dock: list[str] = field(default_factory=list)
    original_home: str | None = None
    fallback_launcher: str | None = None  # ver planner.LauncherStep.fallback_launcher
    status: str = "in_progress"  # in_progress | paused | interrupted | completed | aborted | restored
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    path: Path | None = None

    @classmethod
    def create(cls, device_dir: Path, **kwargs) -> "Journal":
        run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        runs = subdir(device_dir, "runs")
        path = runs / f"{run_id}.json"
        suffix = 1
        while path.exists():
            suffix += 1
            path = runs / f"{run_id}-{suffix}.json"
        journal = cls(run_id=path.stem, path=path, **kwargs)
        journal.save()
        return journal

    def save(self) -> None:
        assert self.path is not None
        self.updated_at = _now()
        data = asdict(self)
        data.pop("path")
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)  # troca atômica: o arquivo nunca fica pela metade

    @classmethod
    def load(cls, path: Path) -> "Journal":
        data = json.loads(path.read_text(encoding="utf-8"))
        data["actions"] = [Action(**a) for a in data["actions"]]
        return cls(path=path, **data)

    def mark(self, action: Action, status: str, message: str = "") -> None:
        action.status = status
        if message:
            action.message = message
        action.updated_at = _now()
        log.info("[%s] ação %d %s %s -> %s %s", self.run_id, action.id, action.kind, action.target, status, message)
        self.save()

    def pending(self) -> list[Action]:
        return [a for a in self.actions if a.status not in FINISHED]

    def by_kind(self, *kinds: str) -> list[Action]:
        return [a for a in self.actions if a.kind in kinds]


def list_journals(device_dir: Path) -> list[Journal]:
    runs = device_dir / "runs"
    if not runs.is_dir():
        return []
    return [Journal.load(p) for p in sorted(runs.glob("*.json"))]


def latest_resumable(device_dir: Path) -> Journal | None:
    for journal in reversed(list_journals(device_dir)):
        if journal.status in ("in_progress", "paused", "interrupted") and journal.pending():
            return journal
    return None
