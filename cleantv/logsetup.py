"""Log detalhado em arquivo; o terminal só mostra o que a interface imprime."""

import logging
from datetime import datetime
from pathlib import Path

from .paths import subdir


def setup_logging(data_dir: Path, verbose: bool = False) -> Path:
    log_path = subdir(data_dir, "logs") / f"run-{datetime.now():%Y%m%d-%H%M%S}.log"
    root = logging.getLogger("cleantv")
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console.setFormatter(logging.Formatter("[log] %(message)s"))
    root.addHandler(console)
    return log_path
