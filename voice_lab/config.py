from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = PROJECT_ROOT / "data"
MAX_MODEL_BYTES = 4 * 1024 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
MAX_IMPORT_BYTES = 2 * 1024 * 1024 * 1024
MAX_SEGMENT_SECONDS = 30 * 60
MIN_SEGMENT_SECONDS = 2.0


def get_data_root(value: str | None = None) -> Path:
    """取得資料根目錄；不把使用者的素材寫入版本庫。"""
    raw = value or os.environ.get("VOICE_LAB_DATA_ROOT")
    root = Path(raw).expanduser() if raw else DEFAULT_DATA_ROOT
    return root.resolve()
