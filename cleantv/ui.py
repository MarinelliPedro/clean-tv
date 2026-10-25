"""Perguntas, confirmações e tabelas no terminal.

Toda a lógica fica em `UI`; `ConsoleUI` usa input()/print() e `ScriptedUI` responde
a partir de uma lista (testes).
"""

from __future__ import annotations

import shutil
import textwrap
from typing import Iterable, Sequence

from .errors import UserAborted

YES = ("s", "sim", "y", "yes")
NO = ("n", "nao", "não", "no")


class UI:
    def _print(self, text: str) -> None:
        raise NotImplementedError

    def _input(self, prompt: str) -> str:
        raise NotImplementedError

    # ---- saída ----

    def say(self, text: str = "") -> None:
        self._print(text)

    def title(self, text: str) -> None:
        self._print("")
        self._print(f"== {text} ==")

    def warn(self, text: str) -> None:
        self._print(f"ATENÇÃO: {text}")

    def error(self, text: str) -> None:
        self._print(f"ERRO: {text}")

    def wrap(self, text: str, indent: str = "") -> None:
        width = max(60, min(110, shutil.get_terminal_size((100, 20)).columns)) - len(indent)
        for line in textwrap.wrap(text, width) or [""]:
            self._print(indent + line)

    def table(self, headers: Sequence[str], rows: Iterable[Sequence[str]], max_width: int = 60) -> None:
        rows = [[str(c) for c in row] for row in rows]
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = min(max(widths[i], len(cell)), max_width)

        def fmt(cells: Sequence[str]) -> str:
            return "  ".join(
                (c if len(c) <= widths[i] else c[: widths[i] - 1] + "…").ljust(widths[i]) for i, c in enumerate(cells)
            ).rstrip()

        self._print(fmt(headers))
        self._print("  ".join("-" * w for w in widths))
        for row in rows:
            self._print(fmt(row))

    # ---- entrada ----

    def ask(self, prompt: str, default: str | None = None) -> str:
        suffix = f" [{default}]" if default else ""
        answer = self._input(f"{prompt}{suffix}: ").strip()
        return answer or (default or "")

    def confirm(self, prompt: str, default: bool = False) -> bool:
        hint = "[S/n]" if default else "[s/N]"
        while True:
            answer = self._input(f"{prompt} {hint} ").strip().lower()
            if not answer:
                return default
            if answer in YES:
                return True
            if answer in NO:
                return False
            self._print("Responda 's' para sim ou 'n' para não.")

    def confirm_word(self, prompt: str, word: str) -> bool:
        answer = self._input(f"{prompt} (digite {word} para confirmar, Enter para cancelar): ").strip()
        return answer == word

    def require(self, prompt: str, default: bool = False) -> None:
        if not self.confirm(prompt, default):
            raise UserAborted("Cancelado. Nada foi alterado na TV.")

    def _parse_numbers(self, text: str, count: int) -> list[int] | None:
        try:
            numbers = [int(part) for part in text.replace(" ", ",").split(",") if part]
        except ValueError:
            return None
        if any(n < 1 or n > count for n in numbers):
            return None
        return numbers

    def pick_many(self, title: str, options: Sequence[tuple[str, str]], selected: Iterable[str] = ()) -> set[str]:
        """Lista com marcação [x]. Números alternam a marcação; Enter confirma."""
        chosen = set(selected)
        if not options:
            return chosen
        while True:
            self.title(title)
            for i, (key, label) in enumerate(options, 1):
                mark = "x" if key in chosen else " "
                self._print(f"  {i:>2}. [{mark}] {label}")
            answer = self._input("Números para marcar/desmarcar (ex.: 1,3) ou Enter para confirmar: ").strip()
            if not answer:
                return chosen
            numbers = self._parse_numbers(answer, len(options))
            if numbers is None:
                self._print(f"Use números de 1 a {len(options)} separados por vírgula.")
                continue
            for n in numbers:
                key = options[n - 1][0]
                chosen.symmetric_difference_update({key})

    def pick_ordered(
        self, title: str, options: Sequence[tuple[str, str]], limit: int, default: Sequence[str]
    ) -> list[str]:
        if not options:
            return []
        keys = [key for key, _ in options]
        self.title(title)
        for i, (_, label) in enumerate(options, 1):
            self._print(f"  {i:>2}. {label}")
        default_numbers = ",".join(str(keys.index(k) + 1) for k in default if k in keys)
        while True:
            answer = self.ask(f"Até {limit} números, na ordem desejada", default_numbers or None)
            numbers = self._parse_numbers(answer, len(options)) if answer else []
            if numbers is None or len(numbers) > limit or len(set(numbers)) != len(numbers):
                self._print(f"Escolha até {limit} números diferentes, de 1 a {len(options)}.")
                continue
            return [keys[n - 1] for n in numbers]


class ConsoleUI(UI):
    def _print(self, text: str) -> None:
        print(text, flush=True)

    def _input(self, prompt: str) -> str:
        try:
            return input(prompt)
        except EOFError:
            return ""


class ScriptedUI(UI):
    """Responde a partir de uma lista; grava tudo que foi mostrado."""

    def __init__(self, answers: Iterable[str] = (), echo: bool = False):
        self.answers = list(answers)
        self.lines: list[str] = []
        self.prompts: list[str] = []
        self.echo = echo

    def _print(self, text: str) -> None:
        self.lines.append(text)
        if self.echo:
            print(text)

    def _input(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError(f"ScriptedUI sem resposta para: {prompt!r}")
        answer = self.answers.pop(0)
        self.lines.append(f"{prompt}{answer}")
        return answer

    @property
    def output(self) -> str:
        return "\n".join(self.lines)
