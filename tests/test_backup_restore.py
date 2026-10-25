import shutil

from cleantv import device
from cleantv.adb.guard import DryRunTransport
from cleantv.backup import (
    build_restore_plan,
    execute_restore,
    load_backup,
    save_backup,
    verify_restore,
    write_restore_scripts,
)
from cleantv.constants import OUR_LAUNCHER_HOME, OUR_LAUNCHER_PACKAGE
from cleantv.executor import journal_for
from cleantv.inventory import collect
from cleantv.journal import DISABLE_PACKAGE, list_journals
from cleantv.planner import Choices, build_plan
from cleantv.rules.engine import load_ruleset

from conftest import DefaultUI, make_executor

LAUNCHERX = "com.google.android.apps.tv.launcherx"
EVERYTHING = Choices(
    keep_groups={"assistant": False, "screensaver": False},
    opt_in={"com.google.android.tvrecommendations"},
    hide_apps={"com.netflix.ninja"},
    launcher_apk="sim://launcher.apk",
    disable_stock_launcher=True,
)


def apply(tv, dev_dir, choices=EVERYTHING):
    inventory = collect(DryRunTransport(tv))
    original, _, _ = save_backup(inventory, dev_dir, address=tv.address)
    classes = load_ruleset(inventory.identity, "TCL").classify_all(inventory)
    plan = build_plan(inventory, classes, choices, address=tv.address, batch_size=2)
    journal = journal_for(plan, dev_dir, original)
    make_executor(tv).run(journal)
    assert journal.status == "completed"
    return original, journal


def restore(tv, original, dev_dir, uninstall=True):
    backup, _ = load_backup(original)
    plan = build_restore_plan(backup, collect(DryRunTransport(tv)), list_journals(dev_dir))
    execute_restore(tv, plan, DefaultUI(), uninstall_ours=uninstall)
    return backup, plan, collect(DryRunTransport(tv))


def test_full_roundtrip_returns_tv_to_original_state(tcl, tmp_path):
    original, journal = apply(tcl, tmp_path)
    assert device.resolve_home(tcl) == OUR_LAUNCHER_HOME
    backup, plan, final = restore(tcl, original, tmp_path)
    assert plan.enable[0][0] == LAUNCHERX  # launcher original volta primeiro
    assert verify_restore(backup, final) == []
    assert final.disabled == backup.disabled == {"com.android.printspooler"}
    assert final.home_component == backup.home_component
    assert OUR_LAUNCHER_PACKAGE not in final.packages
    for action in journal.by_kind(DISABLE_PACKAGE):
        assert tcl.packages[action.target].state == 0  # estado exato, via pm default-state
    again = build_restore_plan(backup, final, list_journals(tmp_path))
    assert again.is_empty


def test_restore_keeping_our_launcher_still_returns_home(tcl, tmp_path):
    original, _ = apply(tcl, tmp_path)
    backup, plan, final = restore(tcl, original, tmp_path, uninstall=False)
    assert plan.set_home == backup.home_component
    assert verify_restore(backup, final) == []
    assert OUR_LAUNCHER_PACKAGE in final.packages


def test_restore_works_without_journals(tcl, tmp_path):
    original, _ = apply(tcl, tmp_path)
    shutil.rmtree(tmp_path / "runs")
    backup, _, final = restore(tcl, original, tmp_path)
    assert verify_restore(backup, final) == []
    assert tcl.packages["com.google.android.play.games"].state == 1  # sem diário: pm enable


def test_restore_on_android_without_default_state(atv, tmp_path):
    original, _ = apply(atv, tmp_path, Choices(keep_groups={"assistant": False}, launcher_apk="sim://l.apk", disable_stock_launcher=True))
    backup, _, final = restore(atv, original, tmp_path)
    assert verify_restore(backup, final) == []
    assert atv.packages["com.google.android.katniss"].state == 1


def test_roundtrip_on_copy_of_the_real_tcl(uniontv, tmp_path):
    choices = Choices(
        opt_in={"com.tcl.bi", "com.tcl.esticker", "com.tcl.tvweishi", "com.google.android.tv.bugreportsender"},
        hide_apps={"tv.pluto.android"},
        launcher_apk="sim://launcher.apk",
        disable_stock_launcher=True,
    )
    original, journal = apply(uniontv, tmp_path, choices)
    assert all(a.status == "done" for a in journal.actions)
    assert device.resolve_home(uniontv) == OUR_LAUNCHER_HOME
    assert not uniontv.packages["com.google.android.tvlauncher"].enabled
    backup, _, final = restore(uniontv, original, tmp_path)
    assert verify_restore(backup, final) == []
    assert final.home_component == "com.google.android.tvlauncher/com.google.android.tvlauncher.MainActivity"


def test_original_restore_point_is_never_overwritten(tcl, tmp_path):
    first = collect(DryRunTransport(tcl))
    original, stamp1, created1 = save_backup(first, tmp_path)
    device.disable_user(tcl, "com.google.android.play.games")
    original2, stamp2, created2 = save_backup(collect(DryRunTransport(tcl)), tmp_path)
    assert created1 and not created2
    assert original == original2 and stamp1 != stamp2
    backup, _ = load_backup(original)
    assert backup.packages["com.google.android.play.games"].enabled


def test_emergency_scripts_restore_the_tv(tcl, tmp_path):
    original, _ = apply(tcl, tmp_path)
    backup, _ = load_backup(original)
    cmd_path, sh_path = write_restore_scripts(tmp_path, address="192.168.0.40:5555", adb_path=r"C:\tools\adb.exe",
                                              backup=backup, journals=list_journals(tmp_path))
    cmd = cmd_path.read_bytes()
    assert b"\r\n" in cmd and b"\r\r\n" not in cmd
    assert "?" not in cmd.decode("ascii")  # acentos e travessão convertidos, não trocados por '?'
    sh = sh_path.read_text(encoding="ascii")
    assert "\r" not in sh
    for text in (cmd.decode(), sh):
        assert "disable-user" not in text
        assert f"pm uninstall {OUR_LAUNCHER_PACKAGE}" in text
        uninstall_lines = [line for line in text.splitlines() if "pm uninstall" in line]
        assert all(line.lstrip().startswith(("rem", "#")) for line in uninstall_lines)
        assert f"set-home-activity --user 0 {backup.home_component}" in text
    assert '"%ADB%" -s %TV% shell pm enable com.google.android.play.games' in cmd.decode()

    # Executa o .sh linha a linha contra a TV simulada.
    prefix = '"$ADB" -s "$TV" shell '
    for line in sh.splitlines():
        if line.startswith(prefix):
            tcl.shell(line[len(prefix):].split())
    final = collect(DryRunTransport(tcl))
    assert verify_restore(backup, final) == []
