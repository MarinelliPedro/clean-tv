"""Fluxo completo da CLI contra a TV simulada (sem TV real)."""

import json

import pytest

from cleantv import cli, device
from cleantv.adb.fake import FakeTv, load_profile
from cleantv.adb.transport import is_read_only
from cleantv.cli import main
from cleantv.constants import OUR_LAUNCHER_HOME, OUR_LAUNCHER_PACKAGE

from conftest import PromptUI

SIM = ["--simulate", "tcl-google-tv"]
YES = {"autorização": "s", "TV correta": "s"}
DEV = "devices/TCL-SIMTCL0001"


def run_cli(tmp_path, args, answers):
    ui = PromptUI(answers)
    code = main(["--data-dir", str(tmp_path), *args], ui=ui)
    return code, ui


def load_tv(tmp_path):
    return FakeTv.load("tcl-google-tv", tmp_path)


def test_dry_run_changes_nothing_and_writes_backup_and_report(tmp_path):
    code, ui = run_cli(tmp_path, ["run", *SIM], YES)
    assert code == 0, ui.output
    assert "Nada foi alterado" in ui.output
    assert "pm disable-user --user 0 com.google.android.play.games" in ui.output
    tv = load_tv(tmp_path)
    assert tv.packages["com.google.android.play.games"].enabled
    assert OUR_LAUNCHER_PACKAGE not in tv.packages
    assert (tmp_path / DEV / "backups" / "original.json").is_file()
    assert list((tmp_path / DEV / "reports").glob("report-*-dryrun.md"))
    assert json.loads((tmp_path / DEV / "dock.json").read_text())["dock"][0] == "com.google.android.youtube.tv"


def test_apply_then_restore(tmp_path):
    code, ui = run_cli(tmp_path, ["run", *SIM, "--apply"], {**YES, "APLICAR": "APLICAR", "Encerrar a depuração": "n"})
    assert code == 0, ui.output
    tv = load_tv(tmp_path)
    assert not tv.packages["com.google.android.play.games"].enabled
    assert not tv.packages["com.google.android.apps.tv.launcherx"].enabled
    assert device.resolve_home(tv) == OUR_LAUNCHER_HOME
    assert (tmp_path / DEV / "restaurar.cmd").is_file()
    report = sorted((tmp_path / DEV / "reports").glob("report-*.md"))[-1].read_text(encoding="utf-8")
    assert "aplicação real" in report and "com.google.android.play.games" in report

    code, ui = run_cli(tmp_path, ["restore", *SIM], {**YES, "Remover também": "s"})
    assert code == 0, ui.output
    assert "Restauração verificada" in ui.output
    tv = load_tv(tmp_path)
    assert tv.packages["com.google.android.play.games"].enabled
    assert tv.packages["com.google.android.apps.tv.launcherx"].enabled
    assert OUR_LAUNCHER_PACKAGE not in tv.packages
    assert device.resolve_home(tv).startswith("com.google.android.apps.tv.launcherx/")

    code, ui = run_cli(tmp_path, ["restore", *SIM], YES)
    assert code == 0 and "Nada a fazer" in ui.output


def test_apply_requires_typing_the_word(tmp_path):
    code, ui = run_cli(tmp_path, ["run", *SIM, "--apply"], YES)
    assert code == 2
    assert load_tv(tmp_path).packages["com.google.android.play.games"].enabled


def test_refuses_without_authorization(tmp_path):
    code, ui = run_cli(tmp_path, ["run", *SIM], {"autorização": "n"})
    assert code == 2
    assert not (tmp_path / "devices").exists()


def test_wrong_tv_aborts_before_backup(tmp_path):
    code, ui = run_cli(tmp_path, ["run", *SIM], {"autorização": "s", "TV correta": "n"})
    assert code == 2
    assert not (tmp_path / DEV / "backups").exists()


def test_samsung_and_lg_are_rejected(tmp_path):
    code, ui = run_cli(tmp_path, ["run", *SIM, "--brand", "Samsung"], YES)
    assert code == 1 and "Tizen" in ui.output


def test_inventory_is_read_only(tmp_path):
    out = tmp_path / "classes.json"
    code, ui = run_cli(tmp_path, ["inventory", *SIM, "--json", str(out)], YES)
    assert code == 0, ui.output
    assert "Somente leitura" in ui.output
    classes = json.loads(out.read_text(encoding="utf-8"))
    assert classes["com.android.vending"]["action"] == "protect"
    assert classes["com.tcl.sim.channelstore"]["category"] == "unknown"
    assert not (tmp_path / "sim" / "tcl-google-tv.json").exists()  # nenhuma escrita na TV simulada


@pytest.fixture
def real_path(monkeypatch):
    """Exercita o caminho de TV real da CLI; só o transporte adb é trocado pela TV simulada."""
    tv = FakeTv(load_profile("tcl-google-tv"))
    tv.address = "192.168.0.40:5555"
    created = []

    def fake_transport(adb_path, address):
        created.append(address)
        return tv

    monkeypatch.setattr(cli, "find_adb", lambda explicit=None: "adb")
    monkeypatch.setattr(cli.network, "probe", lambda ip, port=5555, timeout=1.5: True)
    monkeypatch.setattr(cli.network, "local_ipv4_addresses", lambda: ["192.168.0.10"])
    monkeypatch.setattr(cli, "AdbTransport", fake_transport)
    return tv, created


REAL = ["--ip", "192.168.0.40", "--brand", "TCL", "--model", "C735"]


def test_real_path_confirms_ip_before_connecting(tmp_path, real_path):
    tv, created = real_path
    code, ui = run_cli(tmp_path, ["inventory", *REAL], {**YES, "Conectar à TV em 192.168.0.40:5555": "s"})
    assert code == 0, ui.output
    assert created == ["192.168.0.40:5555"]
    assert all(is_read_only(c) for c in tv.commands)


def test_real_path_declining_connection_touches_nothing(tmp_path, real_path):
    tv, created = real_path
    code, ui = run_cli(tmp_path, ["inventory", *REAL], {**YES, "Conectar à TV": "n"})
    assert code == 2
    assert created == [] and tv.commands == []


def test_real_path_refuses_public_ip(tmp_path, real_path):
    _, created = real_path
    code, ui = run_cli(tmp_path, ["inventory", "--ip", "8.8.8.8", "--brand", "TCL"], YES)
    assert code == 1 and "internet" in ui.output
    assert created == []


def test_real_path_probes_port_only_after_confirmation(tmp_path, real_path, monkeypatch):
    probed = []
    monkeypatch.setattr(cli.network, "probe", lambda ip, port=5555, timeout=1.5: probed.append(ip) or False)
    code, ui = run_cli(tmp_path, ["inventory", *REAL], {**YES, "Conectar à TV": "n"})
    assert code == 2 and probed == []
    code, ui = run_cli(tmp_path, ["inventory", *REAL], {**YES, "Conectar à TV": "s"})
    assert code == 1 and "Depuração USB" in ui.output
    assert probed == ["192.168.0.40"]


def test_connection_drop_during_apply_then_resume(tmp_path, monkeypatch):
    class FlakyExecutor(cli.Executor):
        dropped = False

        def run(self, journal):
            if not FlakyExecutor.dropped:
                FlakyExecutor.dropped = True
                self.t.fail_after = 4  # 1º pacote completo, cai ao ler o 2º
            return super().run(journal)

    monkeypatch.setattr(cli, "Executor", FlakyExecutor)
    answers = {**YES, "APLICAR": "APLICAR", "Encerrar a depuração": "n"}
    code, ui = run_cli(tmp_path, ["run", *SIM, "--apply"], answers)
    assert code == 3, ui.output
    assert "resume" in ui.output
    run_file = next((tmp_path / DEV / "runs").glob("*.json"))
    assert json.loads(run_file.read_text(encoding="utf-8"))["status"] == "interrupted"
    assert (tmp_path / DEV / "restaurar.cmd").is_file()

    code, ui = run_cli(tmp_path, ["resume", *SIM], answers)
    assert code == 0, ui.output
    assert json.loads(run_file.read_text(encoding="utf-8"))["status"] == "completed"
    tv = load_tv(tmp_path)
    assert not tv.packages["com.google.android.play.games"].enabled
    assert not tv.packages["com.google.android.youtube.tvmusic"].enabled
    assert device.resolve_home(tv) == OUR_LAUNCHER_HOME

    code, ui = run_cli(tmp_path, ["resume", *SIM], YES)
    assert code == 0 and "Nenhuma execução interrompida" in ui.output


def test_batch_by_batch_with_pause_and_resume(tmp_path):
    answers = {**YES, "APLICAR": "APLICAR", "Encerrar a depuração": "n", "Opcionais": "", "esconder": ""}
    code, ui = run_cli(tmp_path, ["run", *SIM, "--apply", "--batch-size", "1", "--max-batches", "1"], answers)
    assert code == 0, ui.output
    assert "Pausado depois do lote 1" in ui.output and "resume" in ui.output
    assert not any("Encerrar a depuração" in p for p in ui.prompts)
    tv = load_tv(tmp_path)
    assert sum(not tv.packages[n].enabled for n in ("com.google.android.play.games", "com.google.android.youtube.tvmusic")) == 1
    code, ui = run_cli(tmp_path, ["resume", *SIM, "--max-batches", "1"], answers)
    assert code == 0, ui.output
    tv = load_tv(tmp_path)
    assert not tv.packages["com.google.android.play.games"].enabled
    assert not tv.packages["com.google.android.youtube.tvmusic"].enabled


def test_launcher_command_dry_run_then_test_mode_then_home(tmp_path):
    answers = {**YES, "APLICAR": "APLICAR", "Encerrar a depuração": "n"}
    code, ui = run_cli(tmp_path, ["launcher", *SIM, "--dock", "com.netflix.ninja,com.google.android.youtube.tv"], YES)
    assert code == 0 and "Nada foi alterado" in ui.output
    assert OUR_LAUNCHER_PACKAGE not in load_tv(tmp_path).packages

    code, ui = run_cli(tmp_path, ["launcher", *SIM, "--dock", "com.netflix.ninja,com.google.android.youtube.tv", "--apply"], answers)
    assert code == 0, ui.output
    tv = load_tv(tmp_path)
    assert OUR_LAUNCHER_PACKAGE in tv.packages
    assert tv.launcher_config["dock"] == "com.netflix.ninja,com.google.android.youtube.tv"
    assert device.resolve_home(tv).startswith("com.google.android.apps.tv.launcherx/")

    code, ui = run_cli(tmp_path, ["launcher", *SIM, "--set-home", "--apply"], answers)
    assert code == 0, ui.output
    assert device.resolve_home(load_tv(tmp_path)) == OUR_LAUNCHER_HOME

    code, ui = run_cli(tmp_path, ["restore", *SIM], {**YES, "Remover também": "s"})
    assert code == 0 and "Restauração verificada" in ui.output
    assert OUR_LAUNCHER_PACKAGE not in load_tv(tmp_path).packages


def test_finish_turns_adb_off(tmp_path):
    code, ui = run_cli(tmp_path, ["finish", *SIM], {**YES, "Escolha": "1"})
    assert code == 0, ui.output
    assert load_tv(tmp_path).settings["global"]["adb_enabled"] == "0"


def test_sim_reset(tmp_path):
    run_cli(tmp_path, ["run", *SIM, "--apply"], {**YES, "APLICAR": "APLICAR", "Encerrar a depuração": "n"})
    code, ui = run_cli(tmp_path, ["sim-reset", "tcl-google-tv"], {})
    assert code == 0
    assert load_tv(tmp_path).packages["com.google.android.play.games"].enabled
