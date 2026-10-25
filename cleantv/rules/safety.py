"""Proteção interna: pacotes que a ferramenta nunca desativa.

Esta lista fica no código, e não nos arquivos de regras, para que uma regra errada
não consiga desligar algo essencial. Uma regra só passa por cima dela com
`override_protection = true` E confirmação digitada do pacote pelo usuário.
"""

from __future__ import annotations

_SETTINGS = "Configurações do sistema"
_STORE = "Play Store / serviços Google: necessários para apps e atualizações"
_NET = "Rede, Wi-Fi ou Bluetooth"
_CORE = "Componente central do Android"
_INPUT = "Teclado, controle remoto ou entradas de TV"
_MAINLINE = "Módulo do sistema atualizado pelo Google (mainline)"
_CHIPSET = "Serviço do chipset da TV (imagem, som, sintonizador, HDMI)"
_SETUP = (
    "Assistente de configuração: desativar pode apagar a rede Wi-Fi salva e travar a tela inicial "
    "(relatado no projeto de referência)"
)

HARD_PROTECTED_EXACT: dict[str, str] = {
    "android": _CORE,
    "com.android.systemui": _CORE,
    "com.android.shell": "Shell do ADB: usado pela própria ferramenta para restaurar",
    "com.android.settings": _SETTINGS,
    "com.android.tv.settings": _SETTINGS,
    "com.android.vending": _STORE,
    "com.google.android.gms": _STORE,
    "com.google.android.gsf": _STORE,
    "com.android.packageinstaller": _CORE,
    "com.google.android.packageinstaller": _CORE,
    "com.android.permissioncontroller": _CORE,
    "com.google.android.permissioncontroller": _MAINLINE,
    "com.android.webview": "WebView: vários apps param de abrir sem ele",
    "com.google.android.webview": "WebView: vários apps param de abrir sem ele",
    "com.android.keychain": _CORE,
    "com.android.certinstaller": _CORE,
    "com.android.externalstorage": _CORE,
    "com.android.location.fused": _CORE,
    "com.android.inputdevices": _INPUT,
    "com.android.bluetooth": _NET,
    "com.google.android.bluetooth": _NET,
    "com.android.tv.remote": _INPUT,
    "com.google.android.tv.remote.service": _INPUT,
    "com.google.android.leanback.ime": _INPUT,
    "com.google.android.inputmethod.latin": _INPUT,
    "com.android.inputmethod.latin": _INPUT,
    "com.android.tv": "Live TV / entradas de TV",
    "com.google.android.tv": "Live TV / entradas de TV",
    "com.google.android.ext.services": _MAINLINE,
    "com.android.ext.services": _MAINLINE,
    "com.google.android.modulemetadata": _MAINLINE,
    "com.google.android.mediaprovider": _MAINLINE,
    "com.android.mediaprovider": _MAINLINE,
    "com.google.android.documentsui": _MAINLINE,
    "com.google.android.rkpdapp": _MAINLINE,
    "com.google.android.tungsten.setupwraith": _SETUP,
    "com.google.android.setupwizard": _SETUP,
    "com.android.provision": _SETUP,
}

HARD_PROTECTED_PREFIXES: dict[str, str] = {
    "com.android.providers.": "Provedor de dados do sistema",
    "com.android.server.": _CORE,
    "com.android.networkstack": _NET,
    "com.google.android.networkstack": _NET,
    "com.android.wifi": _NET,
    "com.google.android.wifi": _NET,
    "com.android.tethering": _NET,
    "com.google.android.tethering": _NET,
    "com.android.connectivity": _NET,
    "com.google.android.connectivity": _NET,
    "com.android.captiveportallogin": _NET,
    "com.google.android.captiveportallogin": _NET,
    "com.android.adservices": _MAINLINE,
    "com.google.android.adservices": _MAINLINE,
    "com.google.android.ondevicepersonalization": _MAINLINE,
    "com.mediatek.": _CHIPSET,
    "com.mstar.": _CHIPSET,
    "com.realtek.": _CHIPSET,
    "com.rtk.": _CHIPSET,
    "com.amlogic.": _CHIPSET,
    "com.droidlogic.": _CHIPSET,
    "com.novatek.": _CHIPSET,
    "com.hisilicon.": _CHIPSET,
}


def hard_protection(package: str) -> str | None:
    """Motivo da proteção, ou None se o pacote não está na lista interna."""
    if package in HARD_PROTECTED_EXACT:
        return HARD_PROTECTED_EXACT[package]
    for prefix, reason in HARD_PROTECTED_PREFIXES.items():
        if package.startswith(prefix):
            return reason
    return None
