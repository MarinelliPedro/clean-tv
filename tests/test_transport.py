import subprocess

import pytest

from cleantv.adb.guard import DryRunTransport
from cleantv.adb.transport import AdbTransport, is_read_only, validate_argv
from cleantv.errors import ConnectionLost, DeviceUnauthorized, UnsafeCommand


@pytest.mark.parametrize("token", ["a;b", "x|y", "$(id)", "a b", "`id`", "'q'", '"q"', "a&&b", "", "a\nb", ">f", "*"])
def test_validate_rejects_shell_metacharacters(token):
    with pytest.raises(UnsafeCommand):
        validate_argv(["pm", token])


def test_validate_accepts_normal_commands():
    validate_argv(["pm", "disable-user", "--user", "0", "com.google.android.youtube.tvmusic"])
    validate_argv(["cmd", "package", "set-home-activity", "--user", "0", "com.cleantv.launcher/.HomeActivity"])
    validate_argv(["settings", "put", "global", "adb_enabled", "0"])


def test_read_only_classification():
    assert is_read_only(["getprop", "ro.product.model"])
    assert is_read_only(["pm", "list", "packages", "-d"])
    assert is_read_only(["dumpsys", "package", "com.x"])
    assert is_read_only(["settings", "get", "global", "adb_enabled"])
    assert is_read_only(["cmd", "package", "resolve-activity", "--brief"])
    assert not is_read_only(["pm", "disable-user", "com.x"])
    assert not is_read_only(["pm", "uninstall", "com.x"])
    assert not is_read_only(["settings", "put", "global", "adb_enabled", "0"])
    assert not is_read_only(["cmd", "package", "set-home-activity", "a/b"])
    assert not is_read_only(["input", "keyevent", "KEYCODE_HOME"])


class FakeRunner:
    def __init__(self, returncode=0, stdout="", stderr="", raise_timeout=False):
        self.returncode, self.stdout, self.stderr, self.raise_timeout = returncode, stdout, stderr, raise_timeout
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if self.raise_timeout:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, self.stderr)


def make(runner):
    return AdbTransport("adb", "192.168.0.40:5555", runner=runner)


def test_shell_targets_the_confirmed_serial():
    runner = FakeRunner(stdout="TCL\n")
    assert make(runner).shell(["getprop", "ro.product.brand"]).stdout == "TCL\n"
    assert runner.calls[0] == ["adb", "-s", "192.168.0.40:5555", "shell", "getprop", "ro.product.brand"]


def test_shell_validates_before_running():
    runner = FakeRunner()
    with pytest.raises(UnsafeCommand):
        make(runner).shell(["pm", "disable-user", "x; reboot"])
    assert runner.calls == []


@pytest.mark.parametrize(
    "stderr",
    ["error: device offline", "error: device '192.168.0.40:5555' not found", "error: closed", "adb: device offline"],
)
def test_adb_client_errors_mean_connection_lost(stderr):
    with pytest.raises(ConnectionLost):
        make(FakeRunner(1, "", stderr)).shell(["getprop", "x"])


def test_unauthorized_is_reported():
    with pytest.raises(DeviceUnauthorized):
        make(FakeRunner(1, "", "error: device unauthorized.")).shell(["getprop", "x"])


def test_remote_command_error_is_a_result_not_a_disconnect():
    err = (
        "Exception occurred while executing 'disable-user':\n"
        "java.lang.IllegalArgumentException: Cannot disable a protected package: com.x"
    )
    result = make(FakeRunner(255, "", err)).shell(["pm", "disable-user", "--user", "0", "com.x"])
    assert result.exit_code == 255
    assert "protected" in result.output


def test_timeout_means_connection_lost():
    with pytest.raises(ConnectionLost):
        make(FakeRunner(raise_timeout=True)).shell(["getprop", "x"])


def test_install_failure_is_a_result(tmp_path):
    apk = tmp_path / "launcher.apk"
    apk.write_bytes(b"x")
    runner = FakeRunner(1, "Performing Streamed Install\n", f"adb: failed to install {apk}: Failure [INSTALL_FAILED_USER_RESTRICTED]")
    assert "Failure [" in make(runner).install(str(apk)).output


def test_install_copies_accented_path_to_ascii_temp(tmp_path):
    folder = tmp_path / "Área de Trabalho"
    folder.mkdir()
    apk = folder / "launcher.apk"
    apk.write_bytes(b"apk")
    runner = FakeRunner(0, "Performing Streamed Install\nSuccess\n")
    make(runner).install(str(apk))
    sent = runner.calls[0][-1]
    assert sent.isascii() and sent.endswith("cleantv-install.apk")


@pytest.mark.parametrize(
    "output, ok",
    [
        ("connected to 192.168.0.40:5555", True),
        ("already connected to 192.168.0.40:5555", True),
        ("failed to authenticate to 192.168.0.40:5555", True),
        ("cannot connect to 192.168.0.40:5555: No connection could be made (10061)", False),
        ("failed to connect to '192.168.0.40:5555': Connection refused", False),
    ],
)
def test_connect_parsing(output, ok):
    transport = make(FakeRunner(0 if ok else 1, output, ""))
    if ok:
        assert transport.connect()
    else:
        with pytest.raises(ConnectionLost):
            transport.connect()


def test_dry_run_transport_blocks_every_write(tcl):
    guard = DryRunTransport(tcl)
    assert guard.shell(["getprop", "ro.product.brand"]).stdout.strip() == "TCL"
    guard.shell(["pm", "disable-user", "--user", "0", "com.google.android.play.games"])
    guard.shell(["settings", "put", "global", "adb_enabled", "0"])
    guard.install("launcher.apk")
    assert guard.blocked == [
        ["pm", "disable-user", "--user", "0", "com.google.android.play.games"],
        ["settings", "put", "global", "adb_enabled", "0"],
        ["install", "-r", "launcher.apk"],
    ]
    assert tcl.packages["com.google.android.play.games"].enabled
    assert tcl.online
    assert all(is_read_only(c) for c in tcl.commands)
    assert tcl.installs == []
