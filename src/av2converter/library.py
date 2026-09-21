from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from av2converter.paths import library_path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load() -> dict[str, Any]:
    path = library_path()
    if not path.is_file():
        return {"items": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": []}
    items = data.get("items")
    if not isinstance(items, list):
        data["items"] = []
    return data


def save(data: dict[str, Any]) -> None:
    path = library_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def items() -> list[dict[str, Any]]:
    existing = []
    for item in load().get("items", []):
        output = item.get("output")
        if output and Path(output).is_file():
            existing.append(item)
    return existing


def add_item(
    *,
    source: str,
    output: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = load()
    item: dict[str, Any] = {
        "id": uuid.uuid4().hex,
        "source": source,
        "output": output,
        "created": _now(),
        "video_codec": "AV2",
        "audio_codec": "xHE-AAC",
        "size": Path(output).stat().st_size if Path(output).is_file() else 0,
    }
    if extra:
        item.update(extra)
    data.setdefault("items", [])
    data["items"] = [item, *[i for i in data["items"] if i.get("output") != output]]
    save(data)
    return item


def remove_item(item_id: str, delete_file: bool = False) -> None:
    data = load()
    kept = []
    for item in data.get("items", []):
        if item.get("id") == item_id:
            if delete_file:
                path = Path(item.get("output") or "")
                if path.is_file():
                    path.unlink()
            continue
        kept.append(item)
    data["items"] = kept
    save(data)
