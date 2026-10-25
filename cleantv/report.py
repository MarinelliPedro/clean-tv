"""Relatório em Markdown de cada execução (dry-run ou real)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .inventory import PLATFORM_LABELS, Inventory
from .journal import DISABLE_PACKAGE, Journal
from .paths import subdir
from .planner import CATEGORY_LABELS, Plan

STATUS_LABELS = {
    "planned": "não executado",
    "running": "interrompido no meio",
    "done": "feito",
    "failed": "falhou",
    "skipped": "ignorado",
    "rolled_back": "revertido",
}
LAUNCHER_STEP_LABELS = {
    "install_launcher": "Instalar o launcher",
    "validate_launcher": "Abrir e validar o launcher",
    "configure_launcher": "Enviar o dock ao launcher",
    "set_home": "Fixar o botão HOME",
    "disable_stock_launcher": "Desativar o launcher original",
}
RUN_STATUS = {
    "in_progress": "em andamento",
    "paused": "pausada entre lotes (use cleantv resume)",
    "interrupted": "interrompida (use cleantv resume)",
    "completed": "concluída",
    "aborted": "parada a pedido ou por segurança",
    "restored": "desfeita com cleantv restore",
}


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _undo(address: str, package: str) -> str:
    return f"adb -s {address} shell pm enable {package}"


def write_report(
    device_dir: Path,
    *,
    inventory: Inventory,
    address: str,
    backup_path: Path,
    plan: Plan | None,
    journal: Journal | None,
    restore_scripts: tuple[Path, Path] | None,
    log_path: Path | None,
    restore_hint: str,
) -> Path:
    """Sem `journal` é um relatório de dry-run (exige `plan`); com `journal`, o plano é opcional."""
    if journal is None and plan is None:
        raise ValueError("relatório precisa de um plano ou de um diário")
    now = datetime.now()
    mode = "DRY-RUN (nada foi alterado)" if journal is None else "aplicação real"
    lines = [
        f"# Relatório Clean TV — {mode}",
        "",
        f"- Data: {now:%d/%m/%Y %H:%M}",
        f"- TV: {inventory.identity.label()}",
        f"- Plataforma: {PLATFORM_LABELS.get(inventory.platform, inventory.platform)}",
        f"- Identificador: `{inventory.identity.device_id}` — endereço `{address}`",
        f"- Ponto de restauração: `{backup_path}`",
    ]
    if journal:
        lines.append(f"- Execução `{journal.run_id}`: {RUN_STATUS.get(journal.status, journal.status)}")

    if journal:
        rows = []
        for action in journal.by_kind(DISABLE_PACKAGE):
            result = STATUS_LABELS.get(action.status, action.status)
            if action.message and action.status != "done":
                result += f": {action.message}"
            rows.append((action.batch, action.target, action.category, result, action.reason))
    else:
        rows = [(c.batch, c.package, c.category, "simulado (dry-run)", c.reason) for c in plan.changes]

    lines += ["", "## Pacotes", ""]
    if rows:
        lines += ["| Lote | Pacote | Categoria | Resultado | Motivo | Como desfazer |", "|---|---|---|---|---|---|"]
        for batch, package, category, result, reason in rows:
            lines.append(
                f"| {batch} | `{package}` | {CATEGORY_LABELS.get(category, category or '-')} | {_cell(result)} | "
                f"{_cell(reason)} | `{_undo(address, package)}` |"
            )
    else:
        lines.append("Nenhum pacote no plano.")

    lines += ["", "## Launcher", ""]
    launcher_actions = [a for a in journal.actions if a.kind in LAUNCHER_STEP_LABELS] if journal else []
    if launcher_actions:
        for action in launcher_actions:
            lines.append(
                f"- {LAUNCHER_STEP_LABELS[action.kind]}: {STATUS_LABELS.get(action.status, action.status)}"
                + (f" — {action.message}" if action.message else "")
            )
    elif journal is None and plan.launcher:
        step = plan.launcher
        lines.append(
            f"Simulado: instalar `{step.apk}`, validar e definir como HOME"
            + (f"; depois desativar `{step.stock_launcher}`." if step.stock_launcher else ".")
        )
    else:
        lines.append("Troca de launcher não incluída nesta execução.")

    dock = journal.dock if journal else plan.dock
    if dock:
        lines += ["", "## Dock", ""] + [f"{i}. `{name}`" for i, name in enumerate(dock, 1)]

    if plan and plan.skipped:
        lines += ["", "## Não incluídos (e por quê)", ""]
        lines += [f"- `{name}`: {_cell(reason)}" for name, reason in plan.skipped]

    lines += ["", "## Como desfazer tudo", "", f"- Com a ferramenta: `{restore_hint}`"]
    if restore_scripts:
        lines += [f"- Sem Python (Windows): `{restore_scripts[0]}`", f"- Sem Python (macOS/Linux): `{restore_scripts[1]}`"]
    if log_path:
        lines += ["", f"Log detalhado: `{log_path}`"]

    reports = subdir(device_dir, "reports")
    path = reports / f"report-{now:%Y%m%d-%H%M%S}{'-dryrun' if journal is None else ''}.md"
    counter = 1
    while path.exists():
        counter += 1
        path = reports / f"report-{now:%Y%m%d-%H%M%S}-{counter}{'-dryrun' if journal is None else ''}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
