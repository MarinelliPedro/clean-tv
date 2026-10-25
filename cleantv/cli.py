"""Linha de comando do Clean TV.

Comandos:
  doctor      verifica o ambiente (Python, adb, rede)
  discover    procura TVs com ADB pela rede na sua /24
  inventory   somente leitura: identidade, backup e classificação de todos os pacotes
  run         fluxo guiado completo; dry-run por padrão, --apply para aplicar
  resume      continua uma execução interrompida ou pausada
  launcher    instala o launcher Clean TV (como app ou como tela inicial)
  restore     desfaz tudo usando o ponto de restauração original
  finish      desliga a depuração ADB na TV
  sim-reset   reinicia uma TV simulada
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import __version__, device, network
from .adb.fake import FakeTv, available_profiles
from .adb.guard import DryRunTransport
from .adb.transport import AdbTransport, Transport, find_adb
from .backup import (
    build_restore_plan,
    execute_restore,
    load_backup,
    original_backup_path,
    save_backup,
    verify_restore,
    write_restore_scripts,
)
from .check import Applied, Drift, applied_state, find_drift, reapply_plan
from .constants import STOCK_LAUNCHERS, app_label
from .errors import AdbNotFound, CleanTvError, ConnectionLost, DeviceUnauthorized, UserAborted
from .executor import Executor, dry_run_commands, journal_for
from .inventory import PLATFORM_LABELS, Inventory, collect
from .journal import Journal, latest_resumable, list_journals
from .logsetup import setup_logging
from .paths import default_data_dir, device_dir
from .planner import CATEGORY_LABELS, DOCK_SIZE, Choices, Plan, build_plan, find_candidates, suggest_dock
from .report import write_report
from .rules.engine import CATEGORIES, CHOICE_GROUPS, Classification, RuleSet, load_ruleset
from .ui import UI, ConsoleUI

log = logging.getLogger("cleantv.cli")

SIM_LAUNCHER_APK = "sim://cleantv-launcher.apk"
DEFAULT_LAUNCHER_APK = Path(__file__).resolve().parent.parent / "launcher" / "dist" / "clean-tv-launcher.apk"
CHECK_DRIFT = 4  # código de saída do check quando algo voltou (útil em scripts)
ACTION_LABELS = {"disable": "desativar (proposto)", "ask": "opcional", "keep": "manter", "protect": "protegido"}
CATEGORY_ORDER = ("ads", "telemetry", "bloatware", "keep", "unknown", "critical")


@dataclass
class Session:
    ui: UI
    data_dir: Path
    raw: Transport  # escreve na TV: só o executor e a restauração usam
    read: DryRunTransport  # leitura: bloqueia qualquer escrita
    identity: device.DeviceIdentity
    address: str
    simulated: bool
    adb_path: str | None
    brand: str
    model: str
    log_path: Path | None

    @property
    def device_dir(self) -> Path:
        return device_dir(self.data_dir, self.identity.device_id)

    def hint(self, command: str) -> str:
        if self.simulated:
            target = f"--simulate {self.address.removeprefix('sim:')}"
        else:
            ip, port = self.address.rsplit(":", 1)
            target = f"--ip {ip}" + ("" if port == "5555" else f" --port {port}")
        return f"python -m cleantv {command} {target}"


# ---------------------------------------------------------------- conexão


def _choose_ip(args: argparse.Namespace, ui: UI) -> str:
    local_ips = network.local_ipv4_addresses()
    if local_ips:
        ui.say(f"Este computador está na rede local: {', '.join(local_ips)}")
    else:
        ui.warn("Não encontrei um IP de rede local neste computador. Ele precisa estar no mesmo roteador da TV.")
    ip = args.ip or ui.ask("IP da TV (Enter para procurar na rede local)")
    if not ip:
        ip = _discover(ui, local_ips, args.port)
    network.check_target_ip(ip)
    route = network.local_address_for(ip)
    if route and not network.same_subnet(route, ip):
        ui.warn(f"A TV ({ip}) parece estar em outra sub-rede que este computador ({route}). Confirme que estão na mesma rede.")
    return ip


def _discover(ui: UI, local_ips: list[str], port: int) -> str:
    if not local_ips:
        raise CleanTvError("Sem rede local para procurar. Informe o IP da TV com --ip.")
    base = local_ips[0]
    ui.require(f"Procurar aparelhos com a porta {port} aberta nos 254 endereços da sua rede {base}/24?", default=True)
    found = network.scan_subnet(base, port)
    if not found:
        raise CleanTvError(
            "Nenhum aparelho com ADB pela rede encontrado. Confira se a depuração está ativa na TV e informe o IP com --ip."
        )
    if len(found) == 1:
        ui.say(f"Encontrado: {found[0]}")
        return found[0]
    for i, ip in enumerate(found, 1):
        ui.say(f"  {i}. {ip}")
    while True:
        answer = ui.ask("Qual é a sua TV? (número)", "1")
        if answer.isdigit() and 1 <= int(answer) <= len(found):
            return found[int(answer) - 1]


def _wait_authorized(raw: AdbTransport, ui: UI, timeout: float = 90.0) -> None:
    ui.say(raw.connect())
    deadline = time.monotonic() + timeout
    warned = False
    while True:
        state = raw.get_state()
        if state == "device":
            return
        if state == "unauthorized" and not warned:
            ui.say("Na TV deve aparecer 'Permitir depuração?'. Marque 'Sempre permitir deste computador' e confirme.")
            warned = True
        elif state in ("offline", "absent"):
            raw.connect()
        if time.monotonic() > deadline:
            raise DeviceUnauthorized("A TV não autorizou a conexão a tempo. Aceite o aviso na tela da TV e rode de novo.")
        time.sleep(2)


def open_session(args: argparse.Namespace, ui: UI, log_path: Path | None, brand: str = "", model: str = "") -> Session:
    adb_path: str | None = None
    if args.simulate:
        raw: Transport = FakeTv.load(args.simulate, args.data_dir)
        ui.say(f"Modo SIMULAÇÃO: TV fictícia '{args.simulate}'. Nenhuma TV real é usada.")
    else:
        adb_path = find_adb(args.adb)
        ip = _choose_ip(args, ui)
        address = f"{ip}:{args.port}"
        ui.require(f"Conectar à TV em {address}?", default=False)
        if not network.probe(ip, args.port):
            raise CleanTvError(
                f"A porta {args.port} da TV {ip} não respondeu. Na TV, ative Opções do desenvolvedor > Depuração USB "
                "(e 'Depuração de rede' / 'ADB pela rede', se existir), confira o IP e tente de novo."
            )
        raw = AdbTransport(adb_path, address)
        _wait_authorized(raw, ui)
    read = DryRunTransport(raw)
    identity = device.read_identity(read)
    return Session(ui, args.data_dir, raw, read, identity, raw.address, bool(args.simulate), adb_path, brand, model, log_path)


def confirm_identity(s: Session) -> None:
    ui, ident = s.ui, s.identity
    ui.title("TV conectada")
    ui.say(f"Fabricante: {ident.manufacturer}   Marca: {ident.brand}   Modelo: {ident.model}")
    ui.say(f"Android {ident.android_release} (SDK {ident.sdk})   Build: {ident.fingerprint}")
    ui.say(f"Endereço: {s.address}")
    seen = f"{ident.manufacturer} {ident.brand}".lower()
    if s.brand and s.brand.lower() not in seen:
        ui.warn(f"Você informou a marca '{s.brand}', mas a TV se identifica como '{ident.manufacturer} / {ident.brand}'.")
    if ident.adb_secure == "0":
        ui.warn(
            "Esta TV aceita ADB sem autorização (ro.adb.secure=0): qualquer aparelho da sua rede consegue um shell nela. "
            "Desligue a depuração ao terminar."
        )
    ui.require("Esta é a TV correta?", default=False)


def _ask_owner(ui: UI) -> None:
    ui.require("Esta TV é sua, ou você tem autorização explícita do dono para alterá-la?", default=False)


def _ask_brand_model(args: argparse.Namespace, ui: UI) -> tuple[str, str]:
    default_brand = default_model = None
    if args.simulate:
        profile = FakeTv.load(args.simulate, args.data_dir)
        default_brand = profile.props.get("ro.product.brand")
        default_model = profile.props.get("ro.product.model")
    brand = args.brand or ui.ask("Marca da TV (ex.: TCL, Xiaomi, Sony, Hisense, Skyworth)", default_brand)
    if brand.strip().lower() in ("samsung", "lg"):
        raise CleanTvError("Samsung (Tizen) e LG (webOS) não usam Android TV e não são suportadas por esta ferramenta.")
    model = args.model or ui.ask("Modelo da TV (Enter se não souber)", default_model)
    return brand.strip(), model.strip()


def _check_is_tv(inventory: Inventory) -> None:
    if not inventory.is_tv:
        raise CleanTvError(
            "Este aparelho não se declara Android TV (falta o recurso android.software.leanback). "
            "A ferramenta só funciona com Android TV / Google TV."
        )


# ---------------------------------------------------------------- telas


def _category_rank(cls: Classification) -> tuple[int, str]:
    return (CATEGORY_ORDER.index(cls.category), cls.package)


def show_inventory(s: Session, inv: Inventory, rules: RuleSet, classes: dict[str, Classification], full: bool) -> None:
    ui = s.ui
    ui.title("Inventário")
    ui.say(f"Plataforma: {PLATFORM_LABELS.get(inv.platform, inv.platform)}")
    ui.say(f"Tela inicial atual: {inv.home_component or 'não identificada'}")
    ui.say(f"Pacotes instalados: {len(inv.packages)} (já desativados antes da ferramenta: {len(inv.disabled)})")
    for rule_file in rules.files:
        ui.say(f"Regras: {rule_file.label} (status: {rule_file.status})")
        if rule_file.status != "validado" and rule_file.meta.get("notes"):
            ui.wrap(rule_file.meta["notes"], "    ")
    if inv.platform == "google_tv":
        ui.say("Google TV: o assistente de configuração (setupwraith) fica sempre protegido.")
    counts: dict[str, int] = {}
    for cls in classes.values():
        counts[cls.category] = counts.get(cls.category, 0) + 1
    ui.say("")
    ui.table(["Categoria", "Pacotes"], [[CATEGORIES[c], str(counts[c])] for c in CATEGORY_ORDER if c in counts])
    shown = [c for c in classes.values() if full or c.category in ("ads", "telemetry", "bloatware") or c.choice_group]
    if shown:
        ui.say("")
        ui.table(
            ["Pacote", "Categoria", "Ação", "Confiança", "Origem"],
            [[c.package, CATEGORIES[c.category], "sua escolha" if c.choice_group else ACTION_LABELS[c.action],
              c.confidence, c.source]
             for c in sorted(shown, key=_category_rank)],
        )


def _label(cls: Classification) -> str:
    return f"{cls.package}  [{cls.category_label}, confiança {cls.confidence}]\n         {cls.reason}"


def ask_choices(s: Session, inv: Inventory, classes: dict[str, Classification], launcher_apk: str | None) -> Choices:
    ui = s.ui
    cand = find_candidates(inv, classes)
    choices = Choices()
    ui.title("Suas escolhas")
    for group in ("assistant", "chromecast", "updates", "screensaver"):
        members = cand.groups.get(group, [])
        if group == "screensaver" and not members:
            continue
        names = ", ".join(c.package for c in members) or "nenhum pacote com regra nesta TV"
        keep = ui.confirm(f"Manter {CHOICE_GROUPS[group]}? ({names})", default=True)
        choices.keep_groups[group] = keep
        if keep:
            continue
        if group == "updates" and not any(c.action != "protect" for c in members):
            ui.wrap(
                "Por segurança, componentes de atualização só são desativados com uma regra específica para o seu "
                "modelo. Nada será alterado nas atualizações.", "  ",
            )
        for c in members:
            if c.risk:
                ui.wrap(f"- {c.package}: {c.risk}", "  ")

    if cand.recommended:
        all_recommended = {c.package for c in cand.recommended}
        kept = ui.pick_many(
            "Recomendados para desativar (desmarque o que quiser manter)",
            [(c.package, _label(c)) for c in cand.recommended],
            all_recommended,
        )
        choices.opt_out = all_recommended - kept
    if cand.optional:
        picked = ui.pick_many(
            "Opcionais (confiança média ou baixa): marque só o que quiser desativar",
            [(c.package, _label(c)) for c in cand.optional],
        )
        for c in cand.optional:
            if c.package in picked and c.override_protection:
                if ui.confirm_word(f"{c.package} é um pacote protegido. Tem certeza?", c.package):
                    choices.confirmed_overrides.add(c.package)
                else:
                    picked.discard(c.package)
        choices.opt_in = picked
    if cand.apps:
        choices.hide_apps = ui.pick_many(
            "Apps na tela inicial: marque os que quer esconder (desativar)", [(n, app_label(n)) for n in cand.apps]
        )

    disabled_groups = {c.package for g, members in cand.groups.items() if not choices.keep_groups.get(g, True) for c in members}
    hidden = ({c.package for c in cand.recommended} - choices.opt_out) | choices.opt_in | choices.hide_apps | disabled_groups
    dock_options = [p.name for p in inv.launchable_apps() if p.name not in hidden]
    choices.dock = ui.pick_ordered(
        f"Dock do novo launcher: escolha os {DOCK_SIZE} apps favoritos",
        [(n, app_label(n)) for n in dock_options], DOCK_SIZE, suggest_dock(inv, hidden),
    )

    if launcher_apk:
        if ui.confirm("Instalar o launcher Clean TV?", default=True):
            choices.launcher_apk = launcher_apk
            choices.launcher_set_home = ui.confirm(
                "Tornar o Clean TV a tela inicial agora? (não = fica como app para você testar)", default=True,
            )
            stock = inv.home_package if inv.home_package in STOCK_LAUNCHERS else None
            if stock and choices.launcher_set_home:
                choices.disable_stock_launcher = ui.confirm(
                    f"Depois de validar o novo launcher, desativar o launcher original ({stock})? "
                    "Se o HOME falhar, ele é reativado na hora.", default=True,
                )
    else:
        ui.wrap(
            "Launcher: o APK do Clean TV não foi encontrado (compile com launcher/build.ps1 ou use --launcher-apk). A troca de launcher fica "
            "de fora desta execução; o launcher original continua."
        )
    return choices


def show_plan(ui: UI, plan: Plan) -> None:
    ui.title("Plano de mudanças")
    if plan.changes:
        for batch in plan.batches:
            ui.say(f"Lote {batch[0].batch}:")
            for change in batch:
                ui.say(f"  - {app_label(change.package)}  [{CATEGORY_LABELS[change.category]}]")
                ui.wrap(f"Por quê: {change.reason}", "      ")
                if change.risk:
                    ui.wrap(f"Risco: {change.risk}", "      ")
                ui.say(f"      Desfazer: {change.undo_command(plan.address)}")
    else:
        ui.say("Nenhum pacote será desativado.")
    if plan.launcher:
        ui.say("")
        what = f"instalar {plan.launcher.apk}, abrir e validar" if plan.launcher.apk else "abrir e validar o Clean TV (já instalado)"
        ui.say(f"Launcher: {what}" + (", enviar o dock." if plan.dock else "."))
        if plan.launcher.set_home:
            ui.say("  Depois, definir o Clean TV como tela inicial (botão HOME).")
        else:
            ui.say("  O botão HOME continua na tela inicial original; o Clean TV fica disponível como app para testar.")
        if plan.launcher.stock_launcher:
            ui.say(f"  Depois, desativar {plan.launcher.stock_launcher} (reativado na hora se o HOME falhar).")
        if plan.launcher.fallback_launcher:
            ui.say(f"  Atualização: se a versão nova não abrir, {plan.launcher.fallback_launcher} é reativado na hora "
                   "(a TV nunca fica sem tela inicial).")
    if plan.dock:
        ui.say(f"Dock: {', '.join(app_label(n) for n in plan.dock)}")
    if plan.skipped:
        ui.say("")
        ui.say("Não incluídos (e por quê):")
        for name, reason in plan.skipped:
            ui.wrap(f"- {name}: {reason}", "  ")
    ui.say("")
    if plan.changes:
        ui.say("Tudo no plano é reversível (pm disable-user, sem desinstalar nada).")
    if plan.launcher:
        ui.say("Para desfazer o launcher: 'restore' devolve a tela inicial original e pode removê-lo.")


# ---------------------------------------------------------------- comandos


def cmd_doctor(args: argparse.Namespace, ui: UI, log_path: Path | None) -> int:
    ui.title("Clean TV — verificação do ambiente")
    ui.say(f"cleantv {__version__} | Python {platform.python_version()} | {platform.system()} {platform.release()}")
    try:
        adb_path = find_adb(args.adb)
        ui.say(f"ADB: {adb_path}")
        ui.say(f"     {AdbTransport(adb_path, '').version()}")
    except AdbNotFound as exc:
        ui.warn(str(exc))
    ui.say(f"Pasta de dados: {args.data_dir}")
    ui.say(f"Log desta execução: {log_path}")
    ips = network.local_ipv4_addresses()
    ui.say(f"IPs de rede local: {', '.join(ips) if ips else 'nenhum encontrado'}")
    ui.say(f"TVs simuladas: {', '.join(available_profiles())}")
    return 0


def cmd_discover(args: argparse.Namespace, ui: UI, log_path: Path | None) -> int:
    local_ips = network.local_ipv4_addresses()
    if not local_ips:
        raise CleanTvError("Nenhum IP de rede local encontrado neste computador.")
    ui.require(f"Procurar a porta {args.port} nos 254 endereços da rede {local_ips[0]}/24?", default=True)
    found = network.scan_subnet(local_ips[0], args.port)
    if not found:
        ui.say("Nenhum aparelho encontrado. Confira se a depuração ADB está ativa na TV.")
        return 1
    ui.say("Aparelhos com ADB pela rede: " + ", ".join(found))
    return 0


def cmd_inventory(args: argparse.Namespace, ui: UI, log_path: Path | None) -> int:
    _ask_owner(ui)
    brand, model = _ask_brand_model(args, ui)
    s = open_session(args, ui, log_path, brand, model)
    confirm_identity(s)
    inv = collect(s.read)
    _check_is_tv(inv)
    original, stamp, created = save_backup(inv, s.device_dir, address=s.address, declared_brand=brand, declared_model=model)
    ui.say(f"Backup gravado: {stamp}")
    ui.say(("Ponto de restauração original criado: " if created else "Ponto de restauração original: ") + str(original))
    rules = load_ruleset(s.identity, brand, args.rules_dir)
    classes = rules.classify_all(inv)
    show_inventory(s, inv, rules, classes, full=True)
    if args.json:
        rows = {name: c.__dict__ for name, c in sorted(classes.items())}
        args.json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        ui.say(f"Classificação salva em {args.json}")
    ui.say("")
    ui.say("Somente leitura: nada foi alterado na TV.")
    return 0


def cmd_run(args: argparse.Namespace, ui: UI, log_path: Path | None) -> int:
    ui.title("Clean TV " + ("— APLICAR (com confirmação)" if args.apply else "— DRY-RUN (nada será alterado)"))
    _ask_owner(ui)
    brand, model = _ask_brand_model(args, ui)
    s = open_session(args, ui, log_path, brand, model)
    confirm_identity(s)
    inv = collect(s.read)
    _check_is_tv(inv)
    dev_dir = s.device_dir
    original, stamp, created = save_backup(inv, dev_dir, address=s.address, declared_brand=brand, declared_model=model)
    ui.say(f"Backup gravado: {stamp}")
    ui.say(("Ponto de restauração original criado: " if created else "Ponto de restauração original (mantido): ") + str(original))

    rules = load_ruleset(s.identity, brand, args.rules_dir)
    classes = rules.classify_all(inv)
    show_inventory(s, inv, rules, classes, full=False)
    choices = ask_choices(s, inv, classes, _launcher_apk(args, s))
    plan = build_plan(inv, classes, choices, address=s.address, batch_size=args.batch_size)
    show_plan(ui, plan)
    (dev_dir / "dock.json").write_text(json.dumps({"dock": plan.dock}, indent=2), encoding="utf-8")

    if plan.is_empty or not args.apply:
        if plan.is_empty:
            ui.say("Nada para fazer.")
        else:
            ui.title("Dry-run: comandos que seriam enviados")
            for command in dry_run_commands(plan):
                ui.say("  " + command)
        report = write_report(dev_dir, inventory=inv, address=s.address, backup_path=original, plan=plan,
                              journal=None, restore_scripts=None, log_path=log_path, restore_hint=s.hint("restore"))
        ui.say("")
        ui.say(f"Relatório: {report}")
        if not plan.is_empty:
            ui.say(f"Nada foi alterado. Para aplicar: {s.hint('run')} --apply")
        return 0

    if not ui.confirm_word("Aplicar este plano na TV agora?", "APLICAR"):
        raise UserAborted("Cancelado. Nada foi alterado na TV.")
    journal = journal_for(plan, dev_dir, original)
    return _execute(s, args, journal, inv, plan)


def _launcher_apk(args: argparse.Namespace, s: Session) -> str | None:
    if getattr(args, "launcher_apk", None):
        return args.launcher_apk
    if s.simulated:
        return SIM_LAUNCHER_APK
    return str(DEFAULT_LAUNCHER_APK) if DEFAULT_LAUNCHER_APK.is_file() else None


def _saved_dock(dev_dir: Path) -> list[str]:
    path = dev_dir / "dock.json"
    try:
        return list(json.loads(path.read_text(encoding="utf-8")).get("dock", []))
    except (OSError, ValueError):
        return []


def cmd_launcher(args: argparse.Namespace, ui: UI, log_path: Path | None) -> int:
    """Só a etapa do launcher: instalar, validar, enviar o dock e (opcional) virar a tela inicial."""
    ui.title("Clean TV — launcher " + ("(APLICAR, com confirmação)" if args.apply else "(DRY-RUN, nada será alterado)"))
    s = open_session(args, ui, log_path)
    confirm_identity(s)
    apk = _launcher_apk(args, s)
    if not apk:
        raise CleanTvError("APK do launcher não encontrado. Compile com launcher\\build.ps1 ou informe --launcher-apk.")
    inv = collect(s.read)
    _check_is_tv(inv)
    dev_dir = s.device_dir
    original, stamp, _ = save_backup(inv, dev_dir, address=s.address)
    ui.say(f"Backup gravado: {stamp}")
    dock = [p for p in (args.dock.split(",") if args.dock else _saved_dock(dev_dir)) if p in inv.packages]
    choices = Choices(
        dock=dock,
        launcher_apk=apk,
        launcher_set_home=args.set_home,
        disable_stock_launcher=args.disable_stock,
    )
    plan = build_plan(inv, {}, choices, address=s.address)
    show_plan(ui, plan)
    if not args.apply:
        ui.title("Dry-run: comandos que seriam enviados")
        for command in dry_run_commands(plan):
            ui.say("  " + command)
        ui.say(f"Nada foi alterado. Para aplicar: {s.hint('launcher')} --apply" + (" --set-home" if args.set_home else ""))
        return 0
    if not ui.confirm_word("Aplicar na TV agora?", "APLICAR"):
        raise UserAborted("Cancelado. Nada foi alterado na TV.")
    return _execute(s, args, journal_for(plan, dev_dir, original), inv, plan)


def _execute(s: Session, args: argparse.Namespace, journal: Journal, inv: Inventory, plan: Plan | None) -> int:
    ui, dev_dir = s.ui, s.device_dir
    original_path = original_backup_path(dev_dir)
    backup_inv, _ = load_backup(original_path)

    def checkpoint(_: Journal) -> None:
        write_restore_scripts(dev_dir, address=s.address, adb_path=s.adb_path, backup=backup_inv,
                              journals=list_journals(dev_dir))

    executor = Executor(
        s.raw, ui,
        confirm_batches=not getattr(args, "no_batch_confirm", False),
        settle_seconds=0.0 if s.simulated else 2.0,
        on_checkpoint=checkpoint,
        max_batches=getattr(args, "max_batches", None),
    )
    code = 0
    try:
        executor.run(journal)
    except ConnectionLost as exc:
        ui.error(f"{exc} Nada mais será enviado à TV.")
        ui.say(f"Quando a TV voltar: {s.hint('resume')}   (ou {s.hint('restore')} para desfazer)")
        code = 3
    except UserAborted as exc:
        ui.warn(str(exc))
        code = 2
    finally:
        checkpoint(journal)
        scripts = (dev_dir / "restaurar.cmd", dev_dir / "restaurar.sh")
        report = write_report(dev_dir, inventory=inv, address=s.address, backup_path=original_path, plan=plan,
                              journal=journal, restore_scripts=scripts, log_path=s.log_path, restore_hint=s.hint("restore"))
        ui.title("Resultado")
        counts: dict[str, int] = {}
        for action in journal.actions:
            counts[action.status] = counts.get(action.status, 0) + 1
        ui.say(", ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
        ui.say(f"Relatório: {report}")
        if journal.status == "paused":
            ui.say(f"Continuar: {s.hint('resume')}")
        ui.say(f"Desfazer tudo: {s.hint('restore')}")
        ui.say(f"Emergência sem Python: {scripts[0]}")
    if journal.status == "paused":
        return code
    if code == 0 and ui.confirm("Encerrar a depuração ADB da TV agora (recomendado)?", default=True):
        finish_adb(s)
    return code


def cmd_resume(args: argparse.Namespace, ui: UI, log_path: Path | None) -> int:
    s = open_session(args, ui, log_path)
    confirm_identity(s)
    journal = latest_resumable(s.device_dir)
    if journal is None:
        ui.say("Nenhuma execução interrompida para esta TV.")
        return 0
    ui.say(f"Execução {journal.run_id}: {len(journal.pending())} ação(ões) pendente(s).")
    ui.require("Continuar de onde parou?", default=True)
    inv = collect(s.read)
    return _execute(s, args, journal, inv, None)


def cmd_restore(args: argparse.Namespace, ui: UI, log_path: Path | None) -> int:
    s = open_session(args, ui, log_path)
    confirm_identity(s)
    path = args.backup or original_backup_path(s.device_dir)
    if not path:
        raise CleanTvError("Não há ponto de restauração para esta TV neste computador (use --backup ARQUIVO).")
    backup_inv, _ = load_backup(Path(path))
    if backup_inv.identity.device_id != s.identity.device_id:
        ui.warn(f"O backup é de outra TV ({backup_inv.identity.label()}).")
        ui.require("Usar mesmo assim?", default=False)
    current = collect(s.read)
    journals = list_journals(s.device_dir)
    plan = build_restore_plan(backup_inv, current, journals)

    ui.title("Restauração")
    ui.say(f"Ponto de restauração: {path} ({backup_inv.collected_at})")
    if plan.is_empty:
        ui.say("A TV já está como no ponto de restauração. Nada a fazer.")
        return 0
    for name, state in plan.enable:
        how = "pm default-state" if state == 0 else "pm enable"
        ui.say(f"  reativar  {name}   ({how})")
    if plan.set_home:
        ui.say(f"  HOME      voltar para {plan.set_home}")
    if plan.our_launcher_installed:
        ui.say("  launcher  Clean TV está instalado (pode ser removido)")
    for name in plan.missing:
        ui.say(f"  aviso     {name} estava instalado no backup e não está mais (não é reinstalado por aqui)")
    if args.dry_run:
        ui.say("Dry-run: nada foi alterado.")
        return 0
    uninstall = plan.our_launcher_installed and (
        args.uninstall_launcher or ui.confirm("Remover também o launcher do Clean TV?", default=False)
    )
    ui.require("Restaurar agora?", default=True)
    execute_restore(s.raw, plan, ui, uninstall_ours=uninstall)
    # Tudo o que essas execuções aplicaram foi desfeito (o check não deve propor reaplicar).
    for journal in journals:
        if journal.status != "restored":
            journal.status = "restored"
            journal.save()
    problems = verify_restore(backup_inv, collect(s.read))
    if problems:
        for problem in problems:
            ui.warn(problem)
        ui.say("A restauração não ficou completa. Veja docs/TROUBLESHOOTING.md.")
        return 1
    ui.say("Restauração verificada: a TV voltou ao estado do ponto de restauração.")
    return 0


def show_drift(ui: UI, drift: Drift, applied: Applied) -> None:
    ui.title("Verificação")
    if drift.system_update:
        before, now = drift.system_update
        ui.say("Sistema da TV atualizado desde o ponto de restauração:")
        ui.say(f"  antes  {before}")
        ui.say(f"  agora  {now}")
    else:
        ui.say("Sistema da TV: mesma versão do ponto de restauração.")
    total = len(applied.disabled)
    back = len(drift.reenabled) + len(drift.blocked)
    still = total - back - len(drift.gone)
    ui.say(f"Pacotes desativados pela ferramenta: {total} ({still} continuam desativados)")
    for name in drift.reenabled:
        ui.say(f"  reativado   {app_label(name)}")
    for name, reason in drift.blocked:
        ui.say(f"  reativado   {app_label(name)}  (não será reaplicado: {reason})")
    for name in drift.gone:
        ui.say(f"  removido    {app_label(name)}  (não está mais instalado; nada a fazer)")
    if drift.stock_reenabled:
        ui.say(f"Launcher original reativado: {app_label(drift.stock_reenabled)}")
    if drift.home:
        ui.say(f"Botão HOME: abre {drift.home} (deveria abrir o Clean TV)")
    elif applied.home_ours:
        ui.say("Botão HOME: Clean TV")
    if drift.launcher_missing:
        ui.say("Launcher Clean TV: não está mais instalado ou ativo.")
    if drift.new_suggested:
        ui.say("")
        ui.say(f"Pacotes novos desde o ponto de restauração que as regras sugerem revisar ({len(drift.new_suggested)}):")
        for cls in drift.new_suggested:
            ui.say(f"  {CATEGORY_LABELS.get(cls.category, cls.category):<12} {app_label(cls.package)}  {cls.reason}")


def cmd_check(args: argparse.Namespace, ui: UI, log_path: Path | None) -> int:
    """Confere se o que foi aplicado continua aplicado; com --apply, reaplica o que voltou."""
    ui.title("Clean TV — verificação " + ("(REAPLICAR, com confirmação)" if args.apply else "(somente leitura)"))
    s = open_session(args, ui, log_path)
    confirm_identity(s)
    original = original_backup_path(s.device_dir)
    if not original:
        raise CleanTvError("Não há ponto de restauração desta TV neste computador. Rode 'inventory' ou 'run' primeiro.")
    backup_inv, _ = load_backup(original)
    current = collect(s.read)
    applied = applied_state(list_journals(s.device_dir))
    if applied.is_empty:
        ui.say("A ferramenta ainda não aplicou nada nesta TV: não há o que conferir.")
        return 0
    classes = load_ruleset(s.identity, args.brand or "", args.rules_dir).classify_all(current)
    drift = find_drift(applied, backup_inv, current, classes)
    show_drift(ui, drift, applied)
    ui.say("")
    if drift.launcher_missing:
        ui.say(f"Para reinstalar o launcher: {s.hint('launcher')} --apply --set-home --disable-stock")
    if drift.new_suggested:
        ui.say(f"Para revisar os pacotes novos: {s.hint('run')}")
    if drift.ok:
        ui.say("Tudo em ordem: o que foi aplicado continua aplicado.")
        return 0
    if not drift.fixable:
        return CHECK_DRIFT
    plan = reapply_plan(drift, applied, current, address=s.address)
    show_plan(ui, plan)
    if not args.apply:
        ui.say(f"Nada foi alterado. Para reaplicar: {s.hint('check')} --apply")
        return CHECK_DRIFT
    if not ui.confirm_word("Reaplicar na TV agora?", "APLICAR"):
        raise UserAborted("Cancelado. Nada foi alterado na TV.")
    return _execute(s, args, journal_for(plan, s.device_dir, original), current, plan)


def finish_adb(s: Session) -> None:
    ui = s.ui
    ui.title("Encerrar a depuração ADB")
    ui.wrap("Deixar o ADB pela rede ligado permite que outros aparelhos da sua rede tentem controlar a TV.")
    ui.say("  1. Desligar a depuração ADB agora (mais seguro; a conexão cai em seguida)")
    ui.say("  2. Só desconectar este computador (a depuração continua ligada na TV)")
    if ui.ask("Escolha", "1") == "1":
        try:
            device.put_setting(s.raw, "global", "adb_wifi_enabled", "0")
            device.put_setting(s.raw, "global", "adb_enabled", "0")
        except ConnectionLost:
            pass  # esperado: o adbd desliga junto
        ui.say("Depuração ADB desligada. Para usar a ferramenta de novo (inclusive restore), reative nas Opções do desenvolvedor.")
    else:
        s.raw.disconnect()
        ui.say("Desconectado.")
    ui.wrap("Confira na TV: Configurações > Sistema > Opções do desenvolvedor > 'Depuração USB' e 'Depuração de rede' desligadas.")


def cmd_finish(args: argparse.Namespace, ui: UI, log_path: Path | None) -> int:
    s = open_session(args, ui, log_path)
    confirm_identity(s)
    finish_adb(s)
    return 0


def cmd_sim_reset(args: argparse.Namespace, ui: UI, log_path: Path | None) -> int:
    existed = FakeTv.reset(args.profile, args.data_dir)
    ui.say(f"TV simulada '{args.profile}' " + ("reiniciada." if existed else "já estava no estado inicial."))
    return 0


# ---------------------------------------------------------------- argumentos


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cleantv", description="Limpeza reversível de Android TV / Google TV via ADB na rede local, sem root."
    )
    parser.add_argument("--version", action="version", version=f"cleantv {__version__}")
    parser.add_argument("--data-dir", type=Path, default=default_data_dir(), help="pasta de backups, diários e logs (padrão: ~/.cleantv)")
    parser.add_argument("--adb", help="caminho do executável adb")
    parser.add_argument("-v", "--verbose", action="store_true", help="mostra no terminal os comandos enviados à TV")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMANDO")

    def device_args(sp: argparse.ArgumentParser) -> None:
        target = sp.add_mutually_exclusive_group()
        target.add_argument("--ip", help="IP da TV na rede local")
        target.add_argument("--simulate", choices=available_profiles(), metavar="PERFIL",
                            help=f"usa uma TV simulada ({', '.join(available_profiles())})")
        sp.add_argument("--port", type=int, default=network.DEFAULT_PORT, help="porta ADB (padrão 5555)")
        sp.add_argument("--brand", help="marca da TV")
        sp.add_argument("--model", help="modelo da TV")

    def rules_arg(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--rules-dir", type=Path, action="append", default=[], help="pasta extra com regras .toml (maior prioridade)")

    sp = sub.add_parser("doctor", help="verifica o ambiente")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("discover", help="procura TVs com ADB pela rede na sua /24")
    sp.add_argument("--port", type=int, default=network.DEFAULT_PORT)
    sp.set_defaults(func=cmd_discover)

    sp = sub.add_parser("inventory", help="somente leitura: identidade, backup e classificação dos pacotes")
    device_args(sp)
    rules_arg(sp)
    sp.add_argument("--json", type=Path, help="grava a classificação em JSON")
    sp.set_defaults(func=cmd_inventory)

    sp = sub.add_parser("run", help="fluxo guiado; dry-run por padrão")
    device_args(sp)
    rules_arg(sp)
    sp.add_argument("--apply", action="store_true", help="aplica de verdade (pede para digitar APLICAR)")
    sp.add_argument("--batch-size", type=int, default=5, help="pacotes por lote (padrão 5)")
    sp.add_argument("--launcher-apk", help="APK do launcher Clean TV")
    sp.add_argument("--no-batch-confirm", action="store_true", help="não pergunta entre os lotes")
    sp.add_argument("--max-batches", type=int, metavar="N", help="aplica até N lotes e pausa (continue com resume)")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("resume", help="continua uma execução interrompida ou pausada")
    device_args(sp)
    sp.add_argument("--no-batch-confirm", action="store_true")
    sp.add_argument("--max-batches", type=int, metavar="N", help="aplica até N lotes e pausa de novo")
    sp.set_defaults(func=cmd_resume)

    sp = sub.add_parser("restore", help="desfaz tudo usando o ponto de restauração")
    device_args(sp)
    sp.add_argument("--backup", type=Path, help="arquivo de backup (padrão: o ponto de restauração original)")
    sp.add_argument("--dry-run", action="store_true", help="só mostra o que seria feito")
    sp.add_argument("--uninstall-launcher", action="store_true", help="remove também o launcher Clean TV")
    sp.set_defaults(func=cmd_restore)

    sp = sub.add_parser("check", help="depois de atualizar a TV: confere o que voltou (somente leitura por padrão)")
    device_args(sp)
    rules_arg(sp)
    sp.add_argument("--apply", action="store_true", help="reaplica o que voltou (pede para digitar APLICAR)")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("launcher", help="instala o launcher Clean TV (dry-run por padrão)")
    device_args(sp)
    sp.add_argument("--launcher-apk", help="APK do launcher (padrão: launcher/dist/clean-tv-launcher.apk)")
    sp.add_argument("--dock", help="apps do dock separados por vírgula (padrão: o dock escolhido no run)")
    sp.add_argument("--set-home", action="store_true", help="torna o Clean TV a tela inicial (sem isso, fica como app)")
    sp.add_argument("--disable-stock", action="store_true", help="com --set-home: desativa o launcher original depois de validar")
    sp.add_argument("--apply", action="store_true", help="aplica de verdade (pede para digitar APLICAR)")
    sp.set_defaults(func=cmd_launcher)

    sp = sub.add_parser("finish", help="desliga a depuração ADB na TV")
    device_args(sp)
    sp.set_defaults(func=cmd_finish)

    sp = sub.add_parser("sim-reset", help="reinicia uma TV simulada")
    sp.add_argument("profile", choices=available_profiles())
    sp.set_defaults(func=cmd_sim_reset)
    return parser


def _close_logging() -> None:
    for handler in list(logging.getLogger("cleantv").handlers):
        handler.close()
        logging.getLogger("cleantv").removeHandler(handler)


def main(argv: list[str] | None = None, ui: UI | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    ui = ui or ConsoleUI()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    log_path = setup_logging(args.data_dir, args.verbose)
    log.info("cleantv %s %s", __version__, argv if argv is not None else sys.argv[1:])
    try:
        return args.func(args, ui, log_path)
    except UserAborted as exc:
        ui.say(str(exc))
        return 2
    except ConnectionLost as exc:
        ui.error(f"{exc} Nada mais foi enviado à TV.")
        return 3
    except CleanTvError as exc:
        ui.error(str(exc))
        return 1
    except KeyboardInterrupt:
        ui.say("")
        ui.say("Interrompido. Nada mais será enviado à TV.")
        return 130
    finally:
        log.info("fim")
        _close_logging()
