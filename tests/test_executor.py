import pytest

from cleantv import device
from cleantv.adb.transport import is_read_only
from cleantv.constants import OUR_LAUNCHER_HOME, OUR_LAUNCHER_PACKAGE
from cleantv.errors import ConnectionLost, UserAborted
from cleantv.executor import dry_run_commands, journal_for
from cleantv.journal import DISABLE_PACKAGE, DISABLE_STOCK_LAUNCHER, INSTALL_LAUNCHER, SET_HOME, VALIDATE_LAUNCHER, Journal
from cleantv.planner import Choices

from conftest import DefaultUI, make_executor, prepare

LAUNCHERX = "com.google.android.apps.tv.launcherx"
FIVE = Choices(opt_in={"com.google.android.tvrecommendations", "com.google.android.feedback"}, hide_apps={"com.netflix.ninja"})
WITH_LAUNCHER = Choices(launcher_apk="sim://launcher.apk", disable_stock_launcher=True)


def start(tv, tmp_path, choices=None, batch_size=5):
    _, _, plan = prepare(tv, choices, batch_size=batch_size)
    return plan, journal_for(plan, tmp_path, tmp_path / "original.json")


def statuses(journal, kind=None):
    return {a.target: a.status for a in journal.actions if kind is None or a.kind == kind}


def test_dry_run_sends_no_writes(tcl):
    _, _, plan = prepare(tcl, Choices(keep_groups={"assistant": False}, launcher_apk="x.apk", disable_stock_launcher=True))
    commands = dry_run_commands(plan)
    assert any("pm disable-user --user 0 com.google.android.katniss" in c for c in commands)
    assert any(f"pm disable-user --user 0 {LAUNCHERX}" in c for c in commands)
    assert all(is_read_only(c) for c in tcl.commands)
    assert all(p.state == (3 if p.name == "com.android.printspooler" else 0) for p in tcl.packages.values())


def test_apply_disables_verifies_and_records_original_state(tcl, tmp_path):
    _, journal = start(tcl, tmp_path)
    make_executor(tcl).run(journal)
    assert journal.status == "completed"
    for action in journal.actions:
        assert action.status == "done"
        assert action.original_state == 0
        assert tcl.packages[action.target].state == 3
    assert Journal.load(journal.path).status == "completed"


def test_protected_package_fails_without_stopping_the_batch(tcl, tmp_path):
    tcl.packages["com.google.android.play.games"].protected = True
    _, journal = start(tcl, tmp_path)
    make_executor(tcl).run(journal)
    by_target = {a.target: a for a in journal.actions}
    assert by_target["com.google.android.play.games"].status == "failed"
    assert "protected" in by_target["com.google.android.play.games"].message
    assert by_target["com.google.android.youtube.tvmusic"].status == "done"
    assert tcl.packages["com.google.android.play.games"].enabled


@pytest.mark.parametrize("fail_after", [8, 9], ids=["antes-do-disable", "depois-do-disable"])
def test_connection_loss_stops_safely_and_resume_finishes(tcl, tmp_path, fail_after):
    # 1 comando inicial + 3 por pacote: com 8 a queda acontece antes do disable do 3º pacote,
    # com 9 acontece depois do disable e antes da verificação.
    _, journal = start(tcl, tmp_path, FIVE)
    tcl.fail_after = fail_after
    with pytest.raises(ConnectionLost):
        make_executor(tcl).run(journal)
    saved = Journal.load(journal.path)
    assert saved.status == "interrupted"
    running = [a for a in saved.actions if a.status == "running"]
    assert len(running) == 1 and running[0].original_state == 0
    assert all(a.status == "planned" for a in saved.actions[3:])

    tcl.online, tcl.fail_after = True, None
    make_executor(tcl).run(saved)
    assert saved.status == "completed"
    assert all(a.status == "done" and a.original_state == 0 for a in saved.actions)
    assert all(not tcl.packages[a.target].enabled for a in saved.actions)


def test_user_says_tv_is_not_ok_and_batch_is_rolled_back(tcl, tmp_path):
    _, journal = start(tcl, tmp_path)
    with pytest.raises(UserAborted):
        make_executor(tcl, DefaultUI(["n", "s"])).run(journal)
    assert journal.status == "aborted"
    assert set(statuses(journal).values()) == {"rolled_back"}
    assert tcl.packages["com.google.android.play.games"].state == 0


def test_health_problem_after_batch_offers_rollback(tcl, tmp_path):
    _, journal = start(tcl, tmp_path, FIVE, batch_size=2)
    tcl.props["sys.boot_completed"] = "0"
    ui = DefaultUI()
    with pytest.raises(UserAborted):
        make_executor(tcl, ui).run(journal)
    assert "terminou de iniciar" in ui.output
    batch1 = [a for a in journal.actions if a.batch == 1]
    assert all(a.status == "rolled_back" for a in batch1)
    assert all(a.status == "planned" for a in journal.actions if a.batch > 1)


def test_launcher_success_and_stock_disabled_last(tcl, tmp_path):
    _, journal = start(tcl, tmp_path, WITH_LAUNCHER)
    make_executor(tcl).run(journal)
    assert [a.kind for a in journal.actions[-4:]] == [INSTALL_LAUNCHER, VALIDATE_LAUNCHER, SET_HOME, DISABLE_STOCK_LAUNCHER]
    assert all(a.status == "done" for a in journal.actions)
    assert tcl.packages[LAUNCHERX].state == 3
    assert device.resolve_home(tcl) == OUR_LAUNCHER_HOME
    assert tcl.foreground == OUR_LAUNCHER_HOME


def test_install_refused_changes_nothing_in_the_launcher(tcl, tmp_path):
    tcl.refuse_install = True
    _, journal = start(tcl, tmp_path, WITH_LAUNCHER)
    make_executor(tcl).run(journal)
    kinds = {a.kind: a.status for a in journal.actions}
    assert kinds[INSTALL_LAUNCHER] == "failed"
    assert kinds[VALIDATE_LAUNCHER] == kinds[SET_HOME] == kinds[DISABLE_STOCK_LAUNCHER] == "skipped"
    assert tcl.packages[LAUNCHERX].enabled
    assert device.resolve_home(tcl).startswith(LAUNCHERX)


def test_crashing_launcher_is_never_made_home(tcl, tmp_path):
    tcl.launcher_apk = {"name": OUR_LAUNCHER_PACKAGE, "system": False, "home": OUR_LAUNCHER_HOME, "crashes": True}
    _, journal = start(tcl, tmp_path, WITH_LAUNCHER)
    make_executor(tcl).run(journal)
    kinds = {a.kind: a.status for a in journal.actions}
    assert kinds[VALIDATE_LAUNCHER] == "failed"
    assert kinds[SET_HOME] == kinds[DISABLE_STOCK_LAUNCHER] == "skipped"
    assert tcl.packages[LAUNCHERX].enabled
    # O HOME continua no launcher original (e não no seletor de launchers).
    assert device.resolve_home(tcl).startswith(LAUNCHERX + "/")
    assert tcl.foreground.startswith(LAUNCHERX + "/")


def test_setupwraith_taking_home_rolls_back_the_stock_launcher(tcl, tmp_path):
    tcl.hijack_home_without_stock = True
    _, journal = start(tcl, tmp_path, WITH_LAUNCHER)
    ui = DefaultUI()
    make_executor(tcl, ui).run(journal)
    stock = next(a for a in journal.actions if a.kind == DISABLE_STOCK_LAUNCHER)
    assert stock.status == "rolled_back"
    assert "setupwraith" in stock.message
    assert tcl.packages[LAUNCHERX].enabled
    assert device.resolve_home(tcl) == OUR_LAUNCHER_HOME


def test_stock_launcher_kept_when_not_requested(tcl, tmp_path):
    _, journal = start(tcl, tmp_path, Choices(launcher_apk="sim://launcher.apk"))
    make_executor(tcl).run(journal)
    assert not journal.by_kind(DISABLE_STOCK_LAUNCHER)
    assert tcl.packages[LAUNCHERX].enabled
    assert device.resolve_home(tcl) == OUR_LAUNCHER_HOME


def test_launcher_test_mode_keeps_original_home_and_sends_dock(tcl, tmp_path):
    dock = ["com.netflix.ninja", "com.google.android.youtube.tv"]
    _, journal = start(tcl, tmp_path, Choices(launcher_apk="sim://l.apk", launcher_set_home=False, dock=dock))
    make_executor(tcl).run(journal)
    launcher_steps = [a.kind for a in journal.actions if a.kind != DISABLE_PACKAGE]
    assert launcher_steps == [INSTALL_LAUNCHER, VALIDATE_LAUNCHER, "configure_launcher", SET_HOME]
    assert all(a.status == "done" for a in journal.actions)
    assert tcl.packages[OUR_LAUNCHER_PACKAGE].enabled
    assert tcl.launcher_config["dock"] == ",".join(dock)
    # Dois launchers instalados: sem fixar o original, o Android mostraria o seletor no HOME.
    assert device.resolve_home(tcl).startswith(LAUNCHERX + "/")
    assert tcl.foreground.startswith(LAUNCHERX + "/")


TVLAUNCHER = "com.google.android.tvlauncher/com.google.android.tvlauncher.MainActivity"


def test_stock_with_system_priority_blocks_set_home_alone(uniontv, tmp_path):
    # Na TCL real o tvlauncher declara priority=2 no HOME: a preferência do usuário é ignorada.
    ui = DefaultUI()
    _, journal = start(uniontv, tmp_path, Choices(opt_out={"com.google.android.music", "com.google.android.play.games"},
                                                  launcher_apk="sim://l.apk"))
    make_executor(uniontv, ui).run(journal)
    set_home = next(a for a in journal.actions if a.kind == SET_HOME)
    assert set_home.status == "failed" and "priority=2" in set_home.message
    assert "--disable-stock" in ui.output
    assert device.resolve_home(uniontv) == TVLAUNCHER
    assert uniontv.packages["com.google.android.tvlauncher"].enabled


def test_stock_with_system_priority_is_replaced_when_disabled(uniontv, tmp_path):
    choices = Choices(opt_out={"com.google.android.music", "com.google.android.play.games"},
                      launcher_apk="sim://l.apk", disable_stock_launcher=True)
    _, journal = start(uniontv, tmp_path, choices)
    make_executor(uniontv).run(journal)
    assert all(a.status == "done" for a in journal.actions), [(a.kind, a.status, a.message) for a in journal.actions]
    assert "prioridade de sistema" in next(a for a in journal.actions if a.kind == SET_HOME).message
    assert device.resolve_home(uniontv) == OUR_LAUNCHER_HOME
    assert not uniontv.packages["com.google.android.tvlauncher"].enabled


def test_max_batches_pauses_and_resume_continues(tcl, tmp_path):
    _, journal = start(tcl, tmp_path, FIVE, batch_size=2)
    ui = DefaultUI()
    make_executor(tcl, ui, max_batches=1).run(journal)
    assert journal.status == "paused"
    assert [a.status for a in journal.actions] == ["done", "done", "planned", "planned", "planned"]
    assert not any("Está tudo funcionando" in p for p in ui.prompts)  # a conferência fica com o usuário
    saved = Journal.load(journal.path)
    make_executor(tcl, max_batches=1).run(saved)
    assert saved.status == "paused"
    make_executor(tcl).run(saved)
    assert saved.status == "completed" and all(a.status == "done" for a in saved.actions)


def test_max_batches_does_not_pause_after_the_last_batch(tcl, tmp_path):
    _, journal = start(tcl, tmp_path)
    make_executor(tcl, max_batches=1).run(journal)
    assert journal.status == "completed"


def test_checkpoint_called_after_each_batch(tcl, tmp_path):
    _, journal = start(tcl, tmp_path, FIVE, batch_size=2)
    calls = []
    make_executor(tcl, on_checkpoint=lambda j: calls.append(len([a for a in j.by_kind(DISABLE_PACKAGE) if a.status == "done"]))).run(journal)
    assert calls[:3] == [2, 4, 5]


def test_launcher_update_that_does_not_open_brings_back_the_stock_launcher(uniontv, tmp_path):
    # Clean TV já é o HOME e o tvlauncher está desativado; a versão nova trava ao abrir.
    keep = {"com.google.android.music", "com.google.android.play.games"}
    _, first = start(uniontv, tmp_path, Choices(opt_out=keep, launcher_apk="sim://l.apk", disable_stock_launcher=True))
    make_executor(uniontv).run(first)
    assert device.resolve_home(uniontv) == OUR_LAUNCHER_HOME
    assert not uniontv.packages["com.google.android.tvlauncher"].enabled

    uniontv.launcher_apk = {**uniontv.launcher_apk, "crashes": True}
    plan, update = start(uniontv, tmp_path, Choices(opt_out=keep, launcher_apk="sim://l2.apk"))
    assert plan.launcher.fallback_launcher == "com.google.android.tvlauncher"
    ui = DefaultUI()
    make_executor(uniontv, ui).run(update)
    validate = next(a for a in update.actions if a.kind == VALIDATE_LAUNCHER)
    assert validate.status == "failed" and "reativado" in validate.message
    assert uniontv.packages["com.google.android.tvlauncher"].enabled
    assert device.resolve_home(uniontv) == TVLAUNCHER
    assert "não ficar sem tela inicial" in ui.output


def test_launcher_update_that_opens_keeps_the_stock_launcher_disabled(uniontv, tmp_path):
    keep = {"com.google.android.music", "com.google.android.play.games"}
    _, first = start(uniontv, tmp_path, Choices(opt_out=keep, launcher_apk="sim://l.apk", disable_stock_launcher=True))
    make_executor(uniontv).run(first)
    _, update = start(uniontv, tmp_path, Choices(opt_out=keep, launcher_apk="sim://l2.apk"))
    make_executor(uniontv).run(update)
    assert all(a.status == "done" for a in update.actions), [(a.kind, a.status, a.message) for a in update.actions]
    assert not uniontv.packages["com.google.android.tvlauncher"].enabled
    assert device.resolve_home(uniontv) == OUR_LAUNCHER_HOME
