"""Onde a ferramenta grava backups, diários, relatórios e logs."""

import os
import re
from pathlib import Path


def default_data_dir() -> Path:
    env = os.environ.get("CLEANTV_HOME")
    return Path(env) if env else Path.home() / ".cleantv"


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "tv"


def device_dir(data_dir: Path, device_id: str) -> Path:
    path = data_dir / "devices" / safe_name(device_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def subdir(base: Path, name: str) -> Path:
    path = base / name
    path.mkdir(parents=True, exist_ok=True)
    return path
