from __future__ import annotations

import os
import shutil
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AV2CONVERTER_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    return here.parents[2]


def data_dir() -> Path:
    env = os.environ.get("AV2CONVERTER_DATA_DIR")
    if env:
        path = Path(env)
    else:
        path = repo_root() / ".av2converter-data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def converted_dir() -> Path:
    path = data_dir() / "converted"
    path.mkdir(parents=True, exist_ok=True)
    return path


def library_path() -> Path:
    return data_dir() / "library.json"


def which(name: str, env_var: str | None = None) -> str | None:
    if env_var:
        override = os.environ.get(env_var)
        if override and Path(override).exists():
            return override
    found = shutil.which(name)
    return found
