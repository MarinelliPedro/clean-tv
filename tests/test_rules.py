import pytest

from cleantv.device import DeviceIdentity
from cleantv.errors import CleanTvError
from cleantv.inventory import PackageInfo
from cleantv.rules.engine import DATA_DIR, brand_rule_files, classify_by_name, load_rule_file, load_ruleset
from cleantv.rules.safety import hard_protection


def identity(**overrides):
    values = dict(manufacturer="TCL", brand="TCL", model="55C735", device="d", android_release="11", sdk=30,
                  fingerprint="f", serial="S1", adb_secure="1")
    values.update(overrides)
    return DeviceIdentity(**values)


def pkg(name, system=True):
    return PackageInfo(name, system, True)


def write_rule(tmp_path, body, name="extra.toml"):
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def all_rule_files():
    return [load_rule_file(DATA_DIR / "common.toml")] + [load_rule_file(p) for p in brand_rule_files()]


def test_all_shipped_rule_files_are_valid():
    files = all_rule_files()
    assert {f.meta["brand"] for f in files[1:]} == {"TCL", "Xiaomi", "Sony", "Hisense", "Skyworth"}


def test_no_brand_is_marked_validated_yet():
    # "validado" exige aplicação E restauração testadas em TV real (docs/COMPATIBILITY.md).
    statuses = {f.meta["brand"]: f.status for f in all_rule_files()[1:]}
    assert "validado" not in statuses.values()
    assert statuses["TCL"] == "parcial"
    assert all(s == "nao-validado" for brand, s in statuses.items() if brand != "TCL")


def test_shipped_disable_rules_are_high_confidence_or_need_a_question():
    for rule_file in all_rule_files():
        for rule in rule_file.rules:
            if rule.action == "disable":
                assert rule.confidence == "high" or rule.choice_group, rule.match


def test_shipped_rules_never_disable_hard_protected_packages():
    for rule_file in all_rule_files():
        for rule in rule_file.rules:
            if not rule.is_prefix and hard_protection(rule.match):
                assert rule.action in ("protect", "keep"), rule.match


def test_hard_protection_beats_any_rule(tmp_path):
    extra = write_rule(tmp_path, '[[rule]]\npackage = "com.android.vending"\ncategory = "bloatware"\n'
                                 'action = "disable"\nconfidence = "high"\nreason = "teste"\n')
    rules = load_ruleset(identity(), "TCL", [extra])
    cls = rules.classify(pkg("com.android.vending"), identity(), "google_tv")
    assert (cls.action, cls.source) == ("protect", "proteção interna")


def test_override_protection_only_as_optional(tmp_path):
    extra = write_rule(tmp_path, '[[rule]]\npackage = "com.android.vending"\ncategory = "bloatware"\naction = "ask"\n'
                                 'confidence = "low"\nreason = "teste"\noverride_protection = true\n')
    cls = load_ruleset(identity(), None, [extra]).classify(pkg("com.android.vending"), identity(), "google_tv")
    assert cls.action == "ask" and cls.override_protection


@pytest.mark.parametrize(
    "body, message",
    [
        ('[[rule]]\npackage = "a.b"\ncategory = "ads"\naction = "disable"\nconfidence = "medium"\nreason = "x"\n', "high"),
        ('[[rule]]\npackage = "a.b"\ncategory = "ads"\naction = "disable"\nconfidence = "high"\nreason = "x"\noverride_protection = true\n', "override"),
        ('[[rule]]\npackage = "a.b"\ncategory = "ads"\naction = "ask"\nconfidence = "low"\nreason = "x"\nextra = 1\n', "desconhecidos"),
        ('[[rule]]\npackage = "a.b"\nprefix = "a."\ncategory = "ads"\naction = "ask"\nreason = "x"\n', "exatamente um"),
        ('[[rule]]\npackage = "a.b"\ncategory = "spam"\naction = "ask"\nreason = "x"\n', "category"),
        ('[[rule]]\npackage = "a.b"\ncategory = "ads"\naction = "ask"\nreason = ""\n', "reason"),
        ('[[rule]]\npackage = "a.b"\ncategory = "ads"\naction = "ask"\nreason = "x"\nmodels = ["("]\n', "regex"),
        ('[meta]\nstatus = "talvez"\n', "status"),
    ],
)
def test_invalid_rules_are_rejected(tmp_path, body, message):
    with pytest.raises(CleanTvError, match=message):
        load_rule_file(write_rule(tmp_path, body) / "extra.toml")


def test_unknown_system_package_is_not_touched():
    cls = load_ruleset(identity()).classify(pkg("com.vendor.something"), identity(), "google_tv")
    assert (cls.category, cls.action) == ("unknown", "keep")


def test_user_installed_app_is_kept():
    cls = load_ruleset(identity()).classify(pkg("com.vendor.something", system=False), identity(), "google_tv")
    assert (cls.category, cls.action) == ("keep", "keep")


@pytest.mark.parametrize(
    "name, category, action",
    [
        ("com.tcl.sim.ota", "critical", "protect"),
        ("com.vendor.networkservice.wifi", "critical", "protect"),
        ("com.vendor.sim.adservice", "ads", "ask"),
        ("com.vendor.analytics", "telemetry", "ask"),
    ],
)
def test_name_heuristics(name, category, action):
    cls = classify_by_name(name)
    assert (cls.category, cls.action) == (category, action)


def test_suspect_heuristic_never_applies_to_platform_packages():
    assert classify_by_name("com.google.android.ads.dummy") is None
    cls = load_ruleset(identity()).classify(pkg("com.google.android.adservices.api"), identity(), "google_tv")
    assert cls.action == "protect"


def test_brand_file_selected_by_manufacturer_or_declared_brand():
    assert "TCL" in [f.label for f in load_ruleset(identity()).files]
    sony = identity(manufacturer="Sony", brand="Sony")
    assert "TCL" not in [f.label for f in load_ruleset(sony).files]
    generic = identity(manufacturer="Generic", brand="Generic")
    assert "TCL" in [f.label for f in load_ruleset(generic, "TCL").files]


def test_model_filter_and_precedence(tmp_path):
    extra = write_rule(tmp_path, (
        '[[rule]]\nprefix = "com.v."\ncategory = "bloatware"\naction = "ask"\nreason = "curto"\n'
        '[[rule]]\nprefix = "com.v.app"\ncategory = "telemetry"\naction = "ask"\nreason = "longo"\n'
        '[[rule]]\npackage = "com.v.app.x"\ncategory = "ads"\naction = "ask"\nreason = "exato"\nmodels = ["^55C7"]\n'
    ))
    rules = load_ruleset(identity(), None, [extra])
    assert rules.classify(pkg("com.v.app.x"), identity(), "google_tv").reason == "exato"
    assert rules.classify(pkg("com.v.app.x"), identity(model="43S5"), "google_tv").reason == "longo"
    assert rules.classify(pkg("com.v.other"), identity(), "google_tv").reason == "curto"


@pytest.mark.parametrize(
    "name",
    ["com.tcl.versionUpdateApp", "com.tcl.initsetup", "com.tcl.systemuioverlay", "com.android.ListenNetStateService",
     "com.tcl.autopair", "com.tcl.sourcemananger", "com.tcl.keycustomfunctionservice", "com.tcl.rc.ota",
     "com.vendor.SystemUpgradeService", "com.vendor.ota.client"],
)
def test_essential_tcl_and_update_packages_are_protected(name):
    uniontv = identity(model="UnionTV", sdk=28)
    assert load_ruleset(uniontv).classify(pkg(name), uniontv, "android_tv").action == "protect"


def test_tcl_optional_rules_only_apply_to_the_evidence_model():
    uniontv = identity(model="UnionTV", sdk=28)
    rules = load_ruleset(uniontv)
    bi = rules.classify(pkg("com.tcl.bi"), uniontv, "android_tv")
    assert (bi.category, bi.action) == ("telemetry", "ask")
    assert rules.classify(pkg("com.tcl.tvweishi"), uniontv, "android_tv").action == "ask"
    other = identity(model="55C735")
    assert rules.classify(pkg("com.tcl.tvweishi"), other, "google_tv").action == "protect"  # prefixo com.tcl.tv
    assert rules.classify(pkg("com.tcl.bi"), other, "google_tv").category == "unknown"


def test_tcl_vendor_services_are_protected():
    cls = load_ruleset(identity()).classify(pkg("com.tcl.tvinputs"), identity(), "google_tv")
    assert cls.action == "protect"
