"""Transporte que deixa passar leituras e bloqueia qualquer escrita.

É usado no inventário, no backup e em todo o dry-run. Mesmo que outro módulo tenha
um bug e tente alterar a TV, o comando não sai deste arquivo.
"""

from __future__ import annotations

import logging
from typing import Sequence

from .transport import ShellResult, Transport, is_read_only, validate_argv

log = logging.getLogger(__name__)


class DryRunTransport:
    dry_run = True

    def __init__(self, inner: Transport):
        self.inner = inner
        self.blocked: list[list[str]] = []

    @property
    def address(self) -> str:
        return self.inner.address

    def connect(self) -> str:
        return self.inner.connect()

    def get_state(self) -> str:
        return self.inner.get_state()

    def shell(self, argv: Sequence[str]) -> ShellResult:
        validate_argv(argv)
        if is_read_only(argv):
            return self.inner.shell(argv)
        self.blocked.append(list(argv))
        log.info("[dry-run] bloqueado: adb shell %s", " ".join(argv))
        return ShellResult(stdout="[dry-run] não executado")

    def install(self, apk_path: str) -> ShellResult:
        self.blocked.append(["install", "-r", str(apk_path)])
        log.info("[dry-run] bloqueado: adb install -r %s", apk_path)
        return ShellResult(stdout="[dry-run] não executado")

    def disconnect(self) -> None:
        self.inner.disconnect()

    def switch_to_usb(self) -> ShellResult:
        self.blocked.append(["usb"])
        return ShellResult(stdout="[dry-run] não executado")
