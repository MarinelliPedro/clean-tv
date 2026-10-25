"""Nomes de pacotes, componentes e intents usados em vários módulos."""

HOME_CATEGORY = "android.intent.category.HOME"
LEANBACK_CATEGORY = "android.intent.category.LEANBACK_LAUNCHER"
RESOLVER_ACTIVITY = "android/com.android.internal.app.ResolverActivity"

# Launchers originais que a ferramenta sabe trocar com segurança.
STOCK_LAUNCHERS = (
    "com.google.android.apps.tv.launcherx",  # Google TV
    "com.google.android.tvlauncher",  # Android TV
    "com.google.android.leanbacklauncher",  # Android TV antigo
    "com.mitv.tvhome",  # Xiaomi PatchWall
)

# Assistentes de configuração: respondem ao HOME, mas não são launchers utilizáveis
# e nunca devem ser desativados.
SETUP_WIZARDS = (
    "com.google.android.tungsten.setupwraith",
    "com.google.android.setupwizard",
    "com.android.provision",
)

# Pedaços de nome que indicam um "HOME" que não serve como launcher.
NOT_A_LAUNCHER_HINTS = ("fallbackhome", "factory", "setup", "provision")
NOT_A_LAUNCHER_PACKAGES = ("com.android.settings", "com.android.tv.settings", "android")

# Nomes amigáveis para pacotes comuns (o ADB não expõe o nome do app sem ferramentas extras).
APP_NAMES = {
    "com.google.android.youtube.tv": "YouTube",
    "com.google.android.youtube.tvmusic": "YouTube Music",
    "com.netflix.ninja": "Netflix",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "com.disney.disneyplus": "Disney+",
    "com.hbo.hbonow": "Max",
    "com.wbd.stream": "Max",
    "com.globo.globotv": "Globoplay",
    "com.spotify.tv.android": "Spotify",
    "com.android.vending": "Play Store",
    "com.google.android.tv": "Live TV",
    "com.google.android.videos": "Google TV / Play Filmes",
    "com.google.android.play.games": "Play Games",
    "com.google.android.apps.tv.launcherx": "Tela inicial do Google TV",
    "com.google.android.tvlauncher": "Tela inicial do Android TV",
    "com.google.android.music": "Play Música",
    "tv.pluto.android": "Pluto TV",
    "br.tv.watch.watchbrasil.androidtv": "Watch Brasil",
    "com.tcl.partnercustomizer": "TCL Channel",
    "com.tcl.tvweishi": "TV Guard / Gerenciador TCL",
    "com.tcl.appmarket2": "Loja TCL",
    "com.tcl.tv": "TV (Live TV da TCL)",
    "com.tcl.ui_mediaCenter": "Media Center",
}


def app_label(package: str) -> str:
    name = APP_NAMES.get(package)
    return f"{name} ({package})" if name else package


OUR_LAUNCHER_PACKAGE = "com.cleantv.launcher"
OUR_LAUNCHER_HOME = "com.cleantv.launcher/com.cleantv.launcher.HomeActivity"
OUR_LAUNCHER_RECEIVER = "com.cleantv.launcher/com.cleantv.launcher.ConfigReceiver"
OUR_LAUNCHER_CONFIGURE = "com.cleantv.launcher.action.CONFIGURE"

# Estados de habilitação do Android (PackageManager.COMPONENT_ENABLED_STATE_*).
STATE_DEFAULT = 0
STATE_ENABLED = 1
STATE_DISABLED = 2
STATE_DISABLED_USER = 3
STATE_DISABLED_UNTIL_USED = 4
DISABLED_STATES = (STATE_DISABLED, STATE_DISABLED_USER, STATE_DISABLED_UNTIL_USED)
STATE_NAMES = {
    STATE_DEFAULT: "default",
    STATE_ENABLED: "enabled",
    STATE_DISABLED: "disabled",
    STATE_DISABLED_USER: "disabled-user",
    STATE_DISABLED_UNTIL_USED: "disabled-until-used",
}
