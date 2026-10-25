from cleantv import device
from cleantv.adb.fake import FakePackage, FakeTv
from cleantv.check import applied_state
from cleantv.cli import CHECK_DRIFT, main
from cleantv.constants import OUR_LAUNCHER_HOME
from cleantv.journal import DISABLE_STOCK_LAUNCHER, SET_HOME, VALIDATE_LAUNCHER, Action, Journal

from conftest import PromptUI

SIM = ["--simulate", "tcl-google-tv"]
UNION = ["--simulate", "tcl-uniontv-atv9"]
YES = {"autorização": "s", "TV correta": "s"}
APPLY = {**YES, "APLICAR": "APLICAR", "Encerrar a depuração": "n"}
LAUNCHERX = "com.google.android.apps.tv.launcherx"
TVLAUNCHER = "com.google.android.tvlauncher"


def run_cli(tmp_path, args, answers):
    ui = PromptUI(answers)
    return main(["--data-dir", str(tmp_path), *args], ui=ui), ui


def ota(tmp_path, profile, *, reenable=(), new=(), fingerprint="TCL/ota/2.0"):
    """Simula uma atualização de sistema: pacotes reativados, pacotes novos e outro build."""
    tv = FakeTv.load(profile, tmp_path)
    for name in reenable:
        tv.packages[name].state = 0
    for name in new:
        tv.packages[name] = FakePackage(name=name)
    tv.props["ro.build.fingerprint"] = fingerprint
    tv.save()


def test_check_right_after_apply_is_all_ok(tmp_path):
    assert run_cli(tmp_path, ["run", *SIM, "--apply"], APPLY)[0] == 0
    code, ui = run_cli(tmp_path, ["check", *SIM], YES)
    assert code == 0, ui.output
    assert "Tudo em ordem" in ui.output
    assert "mesma versão" in ui.output


def test_check_finds_what_an_update_brought_back_and_reapplies_it(tmp_path):
    assert run_cli(tmp_path, ["run", *SIM, "--apply"], APPLY)[0] == 0
    ota(tmp_path, "tcl-google-tv", reenable=["com.google.android.play.games"], new=["com.example.analytics.tracker"])

    code, ui = run_cli(tmp_path, ["check", *SIM], YES)
    assert code == CHECK_DRIFT, ui.output
    assert "Sistema da TV atualizado" in ui.output
    assert "reativado" in ui.output and "Play Games" in ui.output
    assert "com.example.analytics.tracker" in ui.output  # novo, só sugerido para revisão
    assert FakeTv.load("tcl-google-tv", tmp_path).packages["com.google.android.play.games"].enabled  # só leitura

    code, ui = run_cli(tmp_path, ["check", *SIM, "--apply"], APPLY)
    assert code == 0, ui.output
    tv = FakeTv.load("tcl-google-tv", tmp_path)
    assert not tv.packages["com.google.android.play.games"].enabled
    assert tv.packages["com.example.analytics.tracker"].enabled  # pacote novo nunca é desativado pelo check
    assert run_cli(tmp_path, ["check", *SIM], YES)[0] == 0


def test_check_brings_the_home_back_when_the_stock_launcher_returns(tmp_path):
    # TCL do usuário: o tvlauncher tem prioridade de sistema; reativado, ele toma o HOME de volta.
    answers = {**APPLY, "Instalar o launcher": "s"}
    code, ui = run_cli(tmp_path, ["launcher", *UNION, "--apply", "--set-home", "--disable-stock"], answers)
    assert code == 0, ui.output
    ota(tmp_path, "tcl-uniontv-atv9", reenable=[TVLAUNCHER])
    assert device.resolve_home(FakeTv.load("tcl-uniontv-atv9", tmp_path)).startswith(TVLAUNCHER)

    code, ui = run_cli(tmp_path, ["check", *UNION], YES)
    assert code == CHECK_DRIFT
    assert "Launcher original reativado" in ui.output and "deveria abrir o Clean TV" in ui.output
    assert "já instalado" in ui.output  # não reinstala o launcher

    code, ui = run_cli(tmp_path, ["check", *UNION, "--apply"], APPLY)
    assert code == 0, ui.output
    tv = FakeTv.load("tcl-uniontv-atv9", tmp_path)
    assert not tv.packages[TVLAUNCHER].enabled
    assert device.resolve_home(tv) == OUR_LAUNCHER_HOME


def test_after_restore_check_proposes_nothing(tmp_path):
    assert run_cli(tmp_path, ["run", *SIM, "--apply"], APPLY)[0] == 0
    assert run_cli(tmp_path, ["restore", *SIM], {**YES, "Remover também": "n"})[0] == 0
    code, ui = run_cli(tmp_path, ["check", *SIM], YES)
    assert code == 0, ui.output
    assert "não aplicou nada" in ui.output


def test_failed_launcher_update_keeps_the_stock_launcher_as_intended(tmp_path):
    first = Journal(run_id="1", device_id="x", address="a", backup_path="b", batch_size=5, status="completed", actions=[
        Action(id=1, kind=SET_HOME, target=OUR_LAUNCHER_HOME, batch=1, status="done"),
        Action(id=2, kind=DISABLE_STOCK_LAUNCHER, target=TVLAUNCHER, batch=1, status="done"),
    ])
    update = Journal(run_id="2", device_id="x", address="a", backup_path="b", batch_size=5, status="completed",
                     fallback_launcher=TVLAUNCHER, actions=[
                         Action(id=1, kind=VALIDATE_LAUNCHER, target=OUR_LAUNCHER_HOME, batch=1, status="failed"),
                     ])
    applied = applied_state([first, update])
    assert applied.stock_launcher is None and not applied.home_ours
    assert applied_state([first]).stock_launcher == TVLAUNCHER
