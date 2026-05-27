from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class JSONStorage:
    def __init__(self, base_path: str) -> None:
        self.base = Path(base_path)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.base / f"{key}.json"

    def write(self, key: str, data: Dict[str, Any]) -> None:
        tmp = self._path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(self._path(key))

    def read(self, key: str) -> Optional[Dict[str, Any]]:
        p = self._path(key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception as e:
            logger.error(f"Failed to read {key}: {e}")
            return None

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    def list_keys(self) -> list[str]:
        return [p.stem for p in self.base.glob("*.json")]
