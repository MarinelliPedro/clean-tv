import pytest

from cleantv.adb.fake import FakeTv, load_profile
from cleantv.adb.guard import DryRunTransport
from cleantv.executor import Executor
from cleantv.inventory import collect
from cleantv.planner import Choices, build_plan
from cleantv.rules.engine import load_ruleset
from cleantv.ui import ScriptedUI


class DefaultUI(ScriptedUI):
    """Usa as respostas da lista, na ordem, e depois Enter (o padrão) para tudo."""

    def _input(self, prompt: str) -> str:
        self.prompts.append(prompt)
        answer = self.answers.pop(0) if self.answers else ""
        self.lines.append(prompt + answer)
        return answer


class PromptUI(ScriptedUI):
    """Responde conforme um trecho do texto da pergunta; Enter (padrão) para o resto."""

    def __init__(self, rules: dict[str, str]):
        super().__init__()
        self.rules = rules

    def _input(self, prompt: str) -> str:
        self.prompts.append(prompt)
        answer = next((value for key, value in self.rules.items() if key in prompt), "")
        self.lines.append(prompt + answer)
        return answer


@pytest.fixture
def tcl():
    return FakeTv(load_profile("tcl-google-tv"))


@pytest.fixture
def atv():
    return FakeTv(load_profile("android-tv-generic"))


@pytest.fixture
def uniontv():
    """Cópia do inventário real da TCL do usuário (Android TV 9, UnionTV)."""
    return FakeTv(load_profile("tcl-uniontv-atv9"))


def prepare(tv, choices=None, brand="TCL", batch_size=5):
    inventory = collect(DryRunTransport(tv))
    classes = load_ruleset(inventory.identity, brand).classify_all(inventory)
    plan = build_plan(inventory, classes, choices or Choices(), address=tv.address, batch_size=batch_size)
    return inventory, classes, plan


def make_executor(tv, ui=None, **kwargs):
    return Executor(tv, ui or DefaultUI(), settle_seconds=0, sleep=lambda _: None, **kwargs)
