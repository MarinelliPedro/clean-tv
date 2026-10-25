"""Execução do binário oficial `adb`.

Todo comando enviado ao shell da TV passa por `validate_argv`: só tokens simples são
aceitos, então não há como injetar `;`, `|`, `&&`, `$()` ou espaços.
"""

from __future__ import annotations

import glob
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, Sequence

from ..errors import AdbNotFound, CleanTvError, ConnectionLost, DeviceUnauthorized, UnsafeCommand

log = logging.getLogger(__name__)

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:/=@%+,\-]+$")

# Comandos que só leem. Qualquer outro é tratado como escrita.
READ_ONLY_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("getprop",),
    ("pm", "list"),
    ("dumpsys",),
    ("cmd", "package", "resolve-activity"),
    ("cmd", "package", "query-activities"),
    ("settings", "get"),
)


def validate_argv(argv: Sequence[str]) -> None:
    if not argv:
        raise UnsafeCommand("Comando vazio.")
    for token in argv:
        if not isinstance(token, str) or not _SAFE_TOKEN.match(token):
            raise UnsafeCommand(f"Argumento recusado por segurança: {token!r}")


def is_read_only(argv: Sequence[str]) -> bool:
    return any(tuple(argv[: len(prefix)]) == prefix for prefix in READ_ONLY_PREFIXES)


@dataclass(frozen=True)
class ShellResult:
    stdout: str
    stderr: str = ""
    exit_code: int = 0

    @property
    def output(self) -> str:
        return "\n".join(part for part in (self.stdout.strip(), self.stderr.strip()) if part)


class Transport(Protocol):
    address: str

    def connect(self) -> str: ...
    def get_state(self) -> str: ...
    def shell(self, argv: Sequence[str]) -> ShellResult: ...
    def install(self, apk_path: str) -> ShellResult: ...
    def disconnect(self) -> None: ...
    def switch_to_usb(self) -> ShellResult: ...


def find_adb(explicit: str | None = None) -> str:
    candidates: list[str | None] = [explicit, os.environ.get("CLEANTV_ADB"), shutil.which("adb")]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(os.path.join(local, "Android", "Sdk", "platform-tools", "adb.exe"))
        candidates.append(os.path.join(local, "Microsoft", "WinGet", "Links", "adb.exe"))
        candidates += glob.glob(
            os.path.join(local, "Microsoft", "WinGet", "Packages", "Google.PlatformTools*", "platform-tools", "adb.exe")
        )
    home = Path.home()
    candidates += [str(home / "Android" / "Sdk" / "platform-tools" / "adb"), str(home / "Library" / "Android" / "sdk" / "platform-tools" / "adb")]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise AdbNotFound(
        "ADB não encontrado. No Windows instale com: winget install Google.PlatformTools "
        "(ou informe o caminho com --adb)."
    )


def _clip(text: str, limit: int = 4000) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + f"... [+{len(text) - limit} caracteres]"


class AdbTransport:
    """Fala com uma TV pela rede usando `adb -s <ip:porta>`."""

    def __init__(
        self,
        adb_path: str,
        address: str,
        timeout: float = 60.0,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self.adb_path = adb_path
        self.address = address
        self.timeout = timeout
        self._runner = runner

    def _run(self, args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
        cmd = [self.adb_path, *args]
        log.debug("$ adb %s", " ".join(args))
        limit = timeout or self.timeout
        try:
            cp = self._runner(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=limit)
        except subprocess.TimeoutExpired as exc:
            raise ConnectionLost(f"A TV não respondeu em {limit:.0f}s (adb {' '.join(args[:5])}).") from exc
        except FileNotFoundError as exc:
            raise AdbNotFound(f"Não consegui executar o adb em {self.adb_path}.") from exc
        log.debug("exit=%s stdout=%s stderr=%s", cp.returncode, _clip(cp.stdout or ""), _clip(cp.stderr or ""))
        return cp

    def _raise_if_lost(self, cp: subprocess.CompletedProcess) -> None:
        """Separa erro do cliente adb (conexão) de erro do comando na TV (resultado normal)."""
        if cp.returncode == 0:
            return
        err = (cp.stderr or "").strip()
        if "Failure [" in err or "Failure [" in (cp.stdout or ""):
            return  # falha de instalação: resultado do comando, não queda
        if err.startswith(("error:", "adb: ")):
            if "unauthorized" in err.lower():
                raise DeviceUnauthorized("A TV ainda não autorizou este computador. Aceite o aviso na tela da TV.")
            raise ConnectionLost(f"Conexão com a TV perdida: {err}")

    def connect(self) -> str:
        cp = self._run(["connect", self.address], timeout=20)
        out = ((cp.stdout or "") + (cp.stderr or "")).strip()
        low = out.lower()
        if low.startswith(("connected to", "already connected to")) or "failed to authenticate" in low:
            return out
        raise ConnectionLost(f"Não foi possível conectar em {self.address}: {out or 'sem resposta'}")

    def get_state(self) -> str:
        cp = self._run(["-s", self.address, "get-state"], timeout=10)
        text = ((cp.stdout or "") + (cp.stderr or "")).lower()
        if cp.returncode == 0 and (cp.stdout or "").strip() == "device":
            return "device"
        if "unauthorized" in text or "authenticating" in text:
            return "unauthorized"
        if "offline" in text:
            return "offline"
        return "absent"

    def shell(self, argv: Sequence[str]) -> ShellResult:
        validate_argv(argv)
        cp = self._run(["-s", self.address, "shell", *argv])
        self._raise_if_lost(cp)
        return ShellResult(cp.stdout or "", cp.stderr or "", cp.returncode)

    def install(self, apk_path: str) -> ShellResult:
        path = Path(apk_path)
        if path.suffix.lower() != ".apk" or not path.is_file():
            raise CleanTvError(f"APK não encontrado: {apk_path}")
        if not str(path).isascii():  # caminhos com acento (ex.: "Área de Trabalho") podem confundir o adb
            ascii_copy = Path(tempfile.gettempdir()) / "cleantv-install.apk"
            shutil.copyfile(path, ascii_copy)
            path = ascii_copy
        cp = self._run(["-s", self.address, "install", "-r", str(path)], timeout=300)
        self._raise_if_lost(cp)
        return ShellResult(cp.stdout or "", cp.stderr or "", cp.returncode)

    def disconnect(self) -> None:
        self._run(["disconnect", self.address], timeout=10)

    def switch_to_usb(self) -> ShellResult:
        cp = self._run(["-s", self.address, "usb"], timeout=15)
        return ShellResult(cp.stdout or "", cp.stderr or "", cp.returncode)

    def version(self) -> str:
        cp = self._run(["version"], timeout=10)
        return (cp.stdout or "").strip().splitlines()[0] if cp.stdout else ""
