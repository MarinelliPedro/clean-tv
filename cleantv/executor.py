"""Aplica um plano em lotes, com verificação, rollback por lote e retomada.

Regras de execução:
- antes de desativar, grava o estado original exato do pacote no diário;
- depois de desativar, confere o novo estado na TV;
- ao fim de cada lote, checa a saúde da TV e pergunta se está tudo funcionando;
- se a conexão cair, para na hora; `resume` confere o estado real e continua;
- o launcher original só é desativado depois que o nosso foi instalado, abriu e
  assumiu o HOME; se o HOME cair em outro lugar, o original é reativado na hora.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from . import device
from .adb.transport import Transport
from .constants import DISABLED_STATES, OUR_LAUNCHER_HOME, OUR_LAUNCHER_PACKAGE, STOCK_LAUNCHERS
from .device import component_package, is_usable_launcher
from .errors import ConnectionLost, UserAborted
from .journal import (
    CONFIGURE_LAUNCHER,
    DISABLE_PACKAGE,
    DISABLE_STOCK_LAUNCHER,
    FINISHED,
    INSTALL_LAUNCHER,
    SET_HOME,
    VALIDATE_LAUNCHER,
    Action,
    Journal,
)
from .planner import Plan
from .ui import UI


def _first_line(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    # Em exceções do pm, a linha útil costuma ser a última ("...: Cannot disable a protected package").
    return lines[-1] if lines else ""


def dry_run_commands(plan: Plan) -> list[str]:
    """Comandos que seriam enviados, na ordem, sem executar nada."""
    prefix = f"adb -s {plan.address}"
    commands = [
        f"[lote {c.batch}] {prefix} shell pm disable-user --user 0 {c.package}" for c in plan.changes
    ]
    if plan.launcher:
        step = plan.launcher
        if step.apk:
            commands.append(f"[launcher] {prefix} install -r {step.apk}")
        commands.append(f"[launcher] {prefix} shell am start -n {step.component}   (confere se abriu)")
        if plan.dock:
            commands.append(f"[launcher] {prefix} shell am broadcast ... --es dock {','.join(plan.dock)}   (envia o dock)")
        if step.home_target:
            where = "no novo launcher" if step.set_home else "na tela inicial original (o Clean TV fica como app)"
            commands += [
                f"[launcher] {prefix} shell cmd package set-home-activity --user 0 {step.home_target}",
                f"[launcher] {prefix} shell input keyevent KEYCODE_HOME   (confere se o HOME caiu {where})",
            ]
        if step.stock_launcher:
            commands.append(
                f"[launcher] {prefix} shell pm disable-user --user 0 {step.stock_launcher}   "
                "(só se as etapas anteriores passarem; reativado na hora se o HOME falhar)"
            )
    return commands


def journal_for(plan: Plan, device_dir: Path, backup_path: Path) -> Journal:
    actions: list[Action] = []

    def add(kind: str, target: str, batch: int, category: str = "", reason: str = "") -> None:
        actions.append(Action(id=len(actions) + 1, kind=kind, target=target, batch=batch, category=category, reason=reason))

    for change in plan.changes:
        add(DISABLE_PACKAGE, change.package, change.batch, change.category, change.reason)
    if plan.launcher:
        batch = (plan.changes[-1].batch if plan.changes else 0) + 1
        if plan.launcher.apk:  # sem APK: o launcher já está instalado (reaplicação pelo check)
            add(INSTALL_LAUNCHER, plan.launcher.apk, batch)
        add(VALIDATE_LAUNCHER, plan.launcher.component, batch)
        if plan.dock:
            add(CONFIGURE_LAUNCHER, ",".join(plan.dock), batch)
        if plan.launcher.home_target:
            add(SET_HOME, plan.launcher.home_target, batch)
        if plan.launcher.stock_launcher:
            add(DISABLE_STOCK_LAUNCHER, plan.launcher.stock_launcher, batch)
    return Journal.create(
        device_dir,
        device_id=plan.device_id,
        address=plan.address,
        backup_path=str(backup_path),
        batch_size=plan.batch_size,
        actions=actions,
        dock=plan.dock,
        original_home=plan.launcher.original_home if plan.launcher else None,
        fallback_launcher=plan.launcher.fallback_launcher if plan.launcher else None,
    )


class Executor:
    def __init__(
        self,
        transport: Transport,
        ui: UI,
        *,
        confirm_batches: bool = True,
        settle_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
        on_checkpoint: Callable[[Journal], None] | None = None,
        max_batches: int | None = None,
    ):
        self.t = transport
        self.ui = ui
        self.confirm_batches = confirm_batches
        self.settle_seconds = settle_seconds
        self.sleep = sleep
        self.on_checkpoint = on_checkpoint
        self.max_batches = max_batches  # lotes por sessão; depois pausa (continua com resume)
        self._home_was_ok = True

    # ---- ciclo principal ----

    def run(self, journal: Journal) -> Journal:
        journal.status = "in_progress"
        journal.save()
        try:
            self._home_was_ok = is_usable_launcher(device.resolve_home(self.t))
            if self._run_packages(journal):
                self._finish(journal, "paused")
                return journal
            self._run_launcher(journal)
        except ConnectionLost:
            self._finish(journal, "interrupted")
            raise
        except KeyboardInterrupt:
            self._finish(journal, "interrupted")
            raise UserAborted(
                "Interrompido (Ctrl+C). Nada mais será alterado. Use 'cleantv resume' para continuar "
                "ou 'cleantv restore' para desfazer."
            ) from None
        except UserAborted:
            self._finish(journal, "aborted")
            raise
        self._finish(journal, "completed")
        return journal

    def _finish(self, journal: Journal, status: str) -> None:
        journal.status = status
        journal.save()
        self._checkpoint(journal)

    def _checkpoint(self, journal: Journal) -> None:
        if self.on_checkpoint:
            self.on_checkpoint(journal)

    # ---- pacotes ----

    def _run_packages(self, journal: Journal) -> bool:
        """Aplica os lotes pendentes. Retorna True se pausou por causa de `max_batches`."""
        actions = journal.by_kind(DISABLE_PACKAGE)
        batches = sorted({a.batch for a in actions})
        pending = [n for n in batches if not all(a.status in FINISHED for a in actions if a.batch == n)]
        has_launcher = any(a.kind != DISABLE_PACKAGE for a in journal.actions)
        for done_now, number in enumerate(pending, 1):
            batch = [a for a in actions if a.batch == number]
            self.ui.title(f"Lote {number} de {len(batches)}")
            for action in batch:
                self._disable(journal, action)
            self._checkpoint(journal)
            more_work = number != pending[-1] or has_launcher
            pause = self.max_batches is not None and done_now >= self.max_batches and more_work
            self._after_batch(journal, number, batch, is_last=number == batches[-1], pausing=pause)
            if pause:
                self.ui.say(f"Pausado depois do lote {number}. Confira a TV; para continuar use 'resume', para desfazer 'restore'.")
                return True
        return False

    def _disable(self, journal: Journal, action: Action) -> None:
        if action.status in FINISHED:
            return
        state = device.package_state(self.t, action.target)
        if action.status == "planned":
            if state is None:
                journal.mark(action, "skipped", "Pacote não encontrado na TV.")
                self.ui.say(f"  ignorado  {action.target} (não encontrado)")
                return
            if state in DISABLED_STATES:
                journal.mark(action, "skipped", "Já estava desativado.")
                self.ui.say(f"  ignorado  {action.target} (já estava desativado)")
                return
            action.original_state = state
            journal.mark(action, "running")
        else:  # "running": a conexão caiu no meio deste pacote; confere o estado real
            if state in DISABLED_STATES:
                journal.mark(action, "done", "Desativado (confirmado na retomada).")
                self.ui.say(f"  ok        {action.target} (já tinha sido aplicado)")
                return
            if state is None:
                journal.mark(action, "skipped", "Pacote não encontrado na TV.")
                return
        result = device.disable_user(self.t, action.target)
        after = device.package_state(self.t, action.target)
        if result.ok and after in DISABLED_STATES:
            journal.mark(action, "done", "Desativado.")
            self.ui.say(f"  ok        {action.target}")
        else:
            reason = _first_line(result.message) or "O estado do pacote não mudou."
            journal.mark(action, "failed", reason)
            self.ui.warn(f"  falhou    {action.target}: {reason}")

    def _health_problems(self) -> list[str]:
        problems = []
        if not device.boot_completed(self.t):
            problems.append("a TV não informa que terminou de iniciar (sys.boot_completed)")
        home = device.resolve_home(self.t)
        if self._home_was_ok and not is_usable_launcher(home):
            problems.append(f"o botão HOME não leva mais a um launcher (agora: {home or 'nenhum'})")
        return problems

    def _after_batch(self, journal: Journal, number: int, batch: list[Action], is_last: bool, pausing: bool = False) -> None:
        problems = self._health_problems()
        if problems:
            self.ui.warn(f"Depois do lote {number}: " + "; ".join(problems) + ".")
            if self.ui.confirm("Desfazer este lote agora?", default=True):
                self.rollback(journal, batch)
            raise UserAborted("Execução parada por segurança. Use 'cleantv restore' para desfazer tudo.")
        self.ui.say("  checagem automática ok: TV iniciada e botão HOME levando a um launcher")
        if not self.confirm_batches or pausing:
            return  # ao pausar, a conferência é feita por você antes do resume
        question = (
            f"Lote {number} aplicado. Confira a TV (tela inicial, controle, rede). Está tudo funcionando?"
            + ("" if is_last else " Continuar com o próximo lote?")
        )
        if not self.ui.confirm(question, default=True):
            if self.ui.confirm("Desfazer este lote agora?", default=True):
                self.rollback(journal, batch)
            raise UserAborted("Execução parada a seu pedido.")

    def rollback(self, journal: Journal, batch: list[Action]) -> None:
        for action in reversed(batch):
            if action.status not in ("done", "running"):
                continue
            result = device.restore_state(self.t, action.target, action.original_state)
            if result.ok:
                journal.mark(action, "rolled_back", "Revertido.")
                self.ui.say(f"  revertido {action.target}")
            else:
                journal.mark(action, action.status, f"Falha ao reverter: {_first_line(result.message)}")
                self.ui.warn(f"  não consegui reverter {action.target}; use 'cleantv restore'.")
        self._checkpoint(journal)

    # ---- launcher ----

    def _run_launcher(self, journal: Journal) -> None:
        kinds = (INSTALL_LAUNCHER, VALIDATE_LAUNCHER, CONFIGURE_LAUNCHER, SET_HOME, DISABLE_STOCK_LAUNCHER)
        steps = {a.kind: a for a in journal.by_kind(*kinds)}
        if not steps:
            return
        self.ui.title("Troca de launcher")
        sequence = [
            (INSTALL_LAUNCHER, self._install),
            (VALIDATE_LAUNCHER, lambda j, a: self._validate(j, a, journal.original_home)),
            (CONFIGURE_LAUNCHER, self._configure),
            (SET_HOME, lambda j, a: self._set_home(j, a, journal.original_home)),
            (DISABLE_STOCK_LAUNCHER, self._disable_stock),
        ]
        for index, (kind, step) in enumerate(sequence):
            action = steps.get(kind)
            if action is None:
                continue
            ok = action.status == "done" or (action.status not in FINISHED and step(journal, action))
            self._checkpoint(journal)
            if not ok:
                for later_kind, _ in sequence[index + 1:]:
                    later = steps.get(later_kind)
                    if later and later.status not in FINISHED:
                        journal.mark(later, "skipped", "Etapa anterior do launcher não passou; nada mais foi alterado.")
                return

    def _settle(self) -> None:
        self.sleep(self.settle_seconds)

    def _install(self, journal: Journal, action: Action) -> bool:
        journal.mark(action, "running")
        result = self.t.install(action.target)
        installed = OUR_LAUNCHER_PACKAGE in device.list_packages(self.t)
        if "Success" in result.output and installed:
            journal.mark(action, "done", "Instalado.")
            self.ui.say("  ok        launcher instalado")
            return True
        reason = _first_line(result.output) or "instalação não confirmada"
        journal.mark(action, "failed", f"Instalação recusada pela TV: {reason}")
        self.ui.warn(
            f"  A TV recusou a instalação do launcher ({reason}). Algumas TCL bloqueiam launchers de "
            "terceiros. O launcher original continua ativo e nada mais foi alterado."
        )
        return False

    def _validate(self, journal: Journal, action: Action, original_home: str | None) -> bool:
        journal.mark(action, "running")
        foreground = None
        for _ in range(3):
            device.start_activity(self.t, action.target)
            self._settle()
            foreground = device.foreground_activity(self.t)
            if foreground == action.target:
                journal.mark(action, "done", "Abriu e ficou em primeiro plano.")
                self.ui.say("  ok        launcher abriu normalmente")
                return True
        message = f"O launcher não ficou em primeiro plano (atual: {foreground or 'nenhum'})."
        if journal.fallback_launcher:
            # Atualização que não abre, com o launcher original desativado: sem ele a TV ficaria sem tela inicial.
            device.enable(self.t, journal.fallback_launcher)
            fallback_home = next((h for h in device.query_activities(self.t, "android.intent.category.HOME")
                                  if component_package(h) == journal.fallback_launcher), None)
            if fallback_home:
                device.set_home_activity(self.t, fallback_home)
            device.press_home(self.t)
            journal.mark(action, "failed", message + f" Launcher original reativado: {journal.fallback_launcher}.")
            self.ui.warn(
                f"  A versão nova do launcher não abriu. Reativei o launcher original ({journal.fallback_launcher}) "
                "para a TV não ficar sem tela inicial."
            )
            return False
        # Com dois launchers instalados o Android mostraria o seletor no HOME: fixa o original.
        if original_home:
            device.set_home_activity(self.t, original_home)
        device.press_home(self.t)
        journal.mark(action, "failed", message)
        self.ui.warn("  O launcher não abriu direito (pode ter travado). O launcher original continua.")
        return False

    def _configure(self, journal: Journal, action: Action) -> bool:
        """Envia o dock. Se falhar, segue em frente: o dock pode ser montado na própria TV."""
        journal.mark(action, "running")
        result = device.configure_launcher(self.t, action.target.split(","))
        if result.ok:
            journal.mark(action, "done", "Dock enviado ao launcher.")
            self.ui.say("  ok        dock configurado")
        else:
            journal.mark(action, "failed", f"O launcher não confirmou o dock: {_first_line(result.message)}")
            self.ui.warn("  O launcher não confirmou o dock; dá para montar pelo próprio launcher (segure OK num app).")
        return True

    def _set_home(self, journal: Journal, action: Action, original_home: str | None) -> bool:
        """Fixa o HOME no alvo (o Clean TV, ou o launcher original no modo de teste) e confere."""
        ours = action.target == OUR_LAUNCHER_HOME
        journal.mark(action, "running")
        result = device.set_home_activity(self.t, action.target)
        device.press_home(self.t)
        self._settle()
        home = device.resolve_home(self.t)
        foreground = device.foreground_activity(self.t)
        if result.ok and home == action.target and foreground == action.target:
            if ours:
                journal.mark(action, "done", "HOME aponta para o Clean TV.")
                self.ui.say("  ok        botão HOME agora abre o Clean TV")
            else:
                journal.mark(action, "done", "HOME continua na tela inicial original; o Clean TV fica como app.")
                self.ui.say("  ok        botão HOME continua na tela inicial original (Clean TV disponível como app)")
            return True
        stock_pending = next(
            (a for a in journal.actions if a.kind == DISABLE_STOCK_LAUNCHER and a.status not in FINISHED), None
        )
        priority = device.home_priority(self.t)
        outranked = ours and result.ok and priority > 0 and component_package(home) in STOCK_LAUNCHERS
        if outranked and stock_pending is not None and component_package(home) == stock_pending.target:
            # O original tem prioridade de sistema: a preferência só vale quando ele for desativado.
            # A etapa seguinte desativa, aperta HOME, confere e reativa o original se algo falhar.
            journal.mark(
                action, "done",
                f"Preferência gravada; o launcher original tem prioridade de sistema (priority={priority}) "
                "e o HOME passa para o Clean TV quando ele for desativado (próxima etapa, com verificação).",
            )
            self.ui.say(f"  ok        Clean TV registrado; o original tem prioridade fixa ({priority}) e será desativado a seguir")
            return True
        if original_home and ours:
            device.set_home_activity(self.t, original_home)
            device.press_home(self.t)
        journal.mark(action, "failed", f"O HOME não foi para {action.target} (HOME={home}, tela={foreground}, priority={priority}).")
        if outranked:
            self.ui.warn(
                f"  O launcher original tem prioridade de sistema ({priority}): enquanto estiver ativo, o Android não "
                "deixa outro launcher ser o HOME. Rode de novo com --disable-stock (ele é reativado na hora se algo falhar)."
            )
        else:
            self.ui.warn("  Não consegui fixar o botão HOME como planejado. Confira a TV; 'restore' desfaz tudo.")
        return False

    def _disable_stock(self, journal: Journal, action: Action) -> bool:
        ours = next(a.target for a in journal.actions if a.kind == SET_HOME)
        state = device.package_state(self.t, action.target)
        if action.status == "planned":
            if state is None:
                journal.mark(action, "skipped", "Launcher original não encontrado.")
                return True
            if state in DISABLED_STATES:
                journal.mark(action, "skipped", "Launcher original já estava desativado.")
                return True
            action.original_state = state
            journal.mark(action, "running")
        if state not in DISABLED_STATES:
            device.disable_user(self.t, action.target)
        device.press_home(self.t)
        self._settle()
        home = device.resolve_home(self.t)
        foreground = device.foreground_activity(self.t)
        if home == ours and foreground == ours:
            journal.mark(action, "done", "Launcher original desativado; HOME continua no Clean TV.")
            self.ui.say(f"  ok        launcher original desativado ({action.target})")
            return True
        device.restore_state(self.t, action.target, action.original_state)
        device.set_home_activity(self.t, ours)
        device.press_home(self.t)
        landed = foreground or home or "nenhum"
        journal.mark(
            action, "rolled_back",
            f"Ao desativar o launcher original, o HOME foi para {landed}. O launcher original foi reativado na hora.",
        )
        self.ui.warn(
            f"  Ao desativar o launcher original, o HOME caiu em {landed}. Reativei o launcher original; "
            "o Clean TV continua como HOME."
        )
        return False
