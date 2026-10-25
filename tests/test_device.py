import pytest

from cleantv import device
from cleantv.adb.transport import ShellResult
from cleantv.constants import OUR_LAUNCHER_HOME
from cleantv.errors import UnsafeCommand

HOME_CMD = "cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME"
QUERY_CMD = "cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.HOME"


class Canned:
    """Transporte que devolve saídas fixas, copiadas do formato real do Android."""

    address = "canned"

    def __init__(self, outputs):
        self.outputs = outputs

    def shell(self, argv):
        return ShellResult(self.outputs.get(" ".join(argv), ""))


def test_resolve_home_expands_short_component():
    t = Canned({HOME_CMD: "priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=true\n"
                          "com.google.android.apps.tv.launcherx/.home.HomeActivity\n"})
    assert device.resolve_home(t) == "com.google.android.apps.tv.launcherx/com.google.android.apps.tv.launcherx.home.HomeActivity"


def test_resolve_home_none():
    assert device.resolve_home(Canned({HOME_CMD: "No activity found\n"})) is None


def test_query_activities_parses_each_block():
    out = (
        "2 activities found:\n"
        "  Activity #0:\n"
        "    priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=false\n"
        "    com.google.android.apps.tv.launcherx/.home.HomeActivity\n"
        "  Activity #1:\n"
        "    priority=-100 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=false\n"
        "    com.google.android.tungsten.setupwraith/.MainActivity\n"
    )
    assert device.query_activities(Canned({QUERY_CMD: out}), "android.intent.category.HOME") == [
        "com.google.android.apps.tv.launcherx/com.google.android.apps.tv.launcherx.home.HomeActivity",
        "com.google.android.tungsten.setupwraith/com.google.android.tungsten.setupwraith.MainActivity",
    ]


@pytest.mark.parametrize(
    "dumpsys, expected",
    [
        ("Display #0\n    topResumedActivity=ActivityRecord{a1b2c3 u0 com.cleantv.launcher/.HomeActivity t31}\n", OUR_LAUNCHER_HOME),
        ("  Stack #1:\n    mResumedActivity: ActivityRecord{1f2e u0 com.google.android.tvlauncher/.MainActivity t5}\n",
         "com.google.android.tvlauncher/com.google.android.tvlauncher.MainActivity"),
        ("ACTIVITY MANAGER ACTIVITIES\n  (nothing)\n", None),
    ],
)
def test_foreground_activity_android_9_and_12(dumpsys, expected):
    assert device.foreground_activity(Canned({"dumpsys activity activities": dumpsys})) == expected


def test_package_state_reads_user_0():
    out = (
        "Packages:\n  Package [com.x] (abc):\n    userId=10050\n"
        "    User 0: ceDataInode=1 installed=true hidden=false suspended=false stopped=false notLaunched=false enabled=3 instant=false\n"
    )
    assert device.package_state(Canned({"dumpsys package com.x": out}), "com.x") == 3
    assert device.package_state(Canned({"dumpsys package com.y": "Dexopt state:\n"}), "com.y") is None


def test_list_packages_accepts_path_format():
    t = Canned({"pm list packages -f": "package:/system/app/Foo/Foo.apk=com.foo\npackage:com.bar\n"})
    assert device.list_packages(t, "-f") == {"com.foo", "com.bar"}


def test_restore_state_uses_default_state_when_original_was_default(tcl):
    device.disable_user(tcl, "com.google.android.play.games")
    assert device.restore_state(tcl, "com.google.android.play.games", 0).ok
    assert tcl.packages["com.google.android.play.games"].state == 0


def test_restore_state_falls_back_to_enable(atv):
    device.disable_user(atv, "com.google.android.play.games")
    assert device.restore_state(atv, "com.google.android.play.games", 0).ok
    assert atv.packages["com.google.android.play.games"].state == 1


@pytest.mark.parametrize(
    "component, usable",
    [
        (OUR_LAUNCHER_HOME, True),
        ("com.google.android.apps.tv.launcherx/com.google.android.apps.tv.launcherx.home.HomeActivity", True),
        ("com.google.android.tungsten.setupwraith/com.google.android.tungsten.setupwraith.MainActivity", False),
        ("android/com.android.internal.app.ResolverActivity", False),
        ("com.duokan.factorytest/com.duokan.factorytest.Home", False),
        ("com.android.settings/com.android.settings.FallbackHome", False),
        (None, False),
    ],
)
def test_is_usable_launcher(component, usable):
    assert device.is_usable_launcher(component) is usable


def test_check_package_rejects_injection():
    with pytest.raises(UnsafeCommand):
        device.check_package("com.x;reboot")


def test_identity(tcl):
    identity = device.read_identity(tcl)
    assert identity.device_id == "TCL-SIMTCL0001"
    assert identity.sdk == 30
    assert "Android 11" in identity.label()
