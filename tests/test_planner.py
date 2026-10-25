from cleantv.constants import OUR_LAUNCHER_HOME
from cleantv.planner import Choices, find_candidates, suggest_dock

from conftest import prepare

LAUNCHERX = "com.google.android.apps.tv.launcherx"


def names(plan):
    return {c.package for c in plan.changes}


def test_default_plan_only_has_high_confidence_items(tcl):
    _, _, plan = prepare(tcl)
    assert names(plan) == {"com.google.android.youtube.tvmusic", "com.google.android.play.games"}
    assert plan.launcher is None


def test_never_disables_launchers_setup_or_protected_even_if_asked(tcl):
    dangerous = {LAUNCHERX, "com.google.android.tungsten.setupwraith", "com.android.vending", "com.google.android.tv",
                 "com.tcl.tv", "com.mediatek.tvinput"}
    _, _, plan = prepare(tcl, Choices(opt_in=set(dangerous), hide_apps=set(dangerous)))
    assert not names(plan) & dangerous
    skipped = dict(plan.skipped)
    assert dangerous <= set(skipped)
    assert "Assistente de configuração" in skipped["com.google.android.tungsten.setupwraith"]
    assert "Launcher" in skipped[LAUNCHERX]


def test_choice_groups(tcl):
    _, _, plan = prepare(tcl, Choices(keep_groups={"assistant": False, "chromecast": True, "screensaver": False}))
    assert {"com.google.android.katniss", "com.google.android.apps.tv.dreamx"} <= names(plan)
    assert "com.google.android.apps.mediashell" not in names(plan)
    katniss = next(c for c in plan.changes if c.package == "com.google.android.katniss")
    assert katniss.category == "choice" and katniss.reason.startswith("Você escolheu não manter o Assistente")


def test_hidden_user_app_is_described_as_your_choice(tcl):
    _, _, plan = prepare(tcl, Choices(hide_apps={"com.disney.disneyplus"}))
    change = next(c for c in plan.changes if c.package == "com.disney.disneyplus")
    assert (change.category, change.reason) == ("choice", "Você escolheu esconder este app.")
    assert change.risk


def test_optional_items_need_opt_in(tcl):
    _, _, plan = prepare(tcl)
    assert "com.google.android.tvrecommendations" not in names(plan)
    _, _, plan = prepare(tcl, Choices(opt_in={"com.google.android.tvrecommendations"}))
    assert "com.google.android.tvrecommendations" in names(plan)


def test_opt_out_keeps_recommended_item(tcl):
    _, _, plan = prepare(tcl, Choices(opt_out={"com.google.android.play.games"}))
    assert names(plan) == {"com.google.android.youtube.tvmusic"}


def test_hide_app_and_already_disabled(tcl):
    _, _, plan = prepare(tcl, Choices(hide_apps={"com.netflix.ninja", "com.android.printspooler"}))
    assert "com.netflix.ninja" in names(plan)
    assert dict(plan.skipped)["com.android.printspooler"] == "Já está desativado."


def test_batches_respect_size(tcl):
    choices = Choices(opt_in={"com.google.android.tvrecommendations", "com.google.android.feedback"},
                      hide_apps={"com.netflix.ninja"})
    _, _, plan = prepare(tcl, choices, batch_size=2)
    assert [len(b) for b in plan.batches] == [2, 2, 1]
    assert [c.batch for c in plan.changes] == [1, 1, 2, 2, 3]
    assert plan.changes[0].category == "ads"  # anúncios primeiro


def test_candidates(tcl):
    inventory, classes, _ = prepare(tcl)
    cand = find_candidates(inventory, classes)
    assert {c.package for c in cand.recommended} == {"com.google.android.youtube.tvmusic", "com.google.android.play.games"}
    assert {"com.google.android.tvrecommendations", "com.google.android.feedback", "com.tcl.sim.adservice"} <= {
        c.package for c in cand.optional}
    assert set(cand.groups) == {"assistant", "chromecast", "screensaver"}
    assert "com.netflix.ninja" in cand.apps
    assert "com.android.vending" not in cand.apps and "com.google.android.tv" not in cand.apps


def test_dock_suggestion_and_exclusion(tcl):
    inventory, _, _ = prepare(tcl)
    assert suggest_dock(inventory, set()) == [
        "com.google.android.youtube.tv", "com.netflix.ninja", "com.amazon.amazonvideo.livingroom", "com.disney.disneyplus"]
    _, _, plan = prepare(tcl, Choices(hide_apps={"com.netflix.ninja"}, dock=["com.netflix.ninja", "com.google.android.youtube.tv"]))
    assert plan.dock == ["com.google.android.youtube.tv"]


def test_real_tcl_inventory_default_plan(uniontv):
    inventory, classes, plan = prepare(uniontv)
    assert inventory.platform == "android_tv"
    assert inventory.home_component == "com.google.android.tvlauncher/com.google.android.tvlauncher.MainActivity"
    assert names(plan) == {"com.google.android.play.games", "com.google.android.music"}
    cand = find_candidates(inventory, classes)
    assert {"com.tcl.bi", "com.tcl.esticker", "com.tcl.tvweishi", "com.tcl.appmarket2",
            "com.google.android.tv.bugreportsender"} <= {c.package for c in cand.optional}
    assert {c.package for c in cand.groups["assistant"]} == {"com.google.android.katniss", "com.google.android.speech.pumpkin"}
    # FallbackHome da TCL responde ao HOME: nunca pode entrar no plano.
    _, _, plan = prepare(uniontv, Choices(hide_apps={"com.tcl.keycustomfunctionservice", "com.tcl.tv"}))
    assert not names(plan) & {"com.tcl.keycustomfunctionservice", "com.tcl.tv"}


def test_launcher_step(tcl):
    _, _, plan = prepare(tcl, Choices(launcher_apk="x.apk", disable_stock_launcher=True))
    assert plan.launcher.component == OUR_LAUNCHER_HOME
    assert plan.launcher.stock_launcher == LAUNCHERX
    assert plan.launcher.original_home.startswith(LAUNCHERX + "/")
    _, _, plan = prepare(tcl, Choices(launcher_apk="x.apk"))
    assert plan.launcher.stock_launcher is None
