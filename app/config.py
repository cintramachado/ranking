"""Carregamento de configuração do FlowRank."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "capture": {
        "interval_ms": 250,
        "max_rows": 5000,
        "risk_warn": 0.70,
        "risk_critical": 0.90,
    },
    "gui": {"refresh_ms": 500, "top_n": 15},
    "database": {
        "path": "data/flowrank.db",
        "flush_interval_ms": 1000,
        "batch_size": 500,
    },
    "excel": {
        "workbook": "auto",
        "worksheet": "auto",
        "header_row": "auto",
        "symbol": "auto",
    },
    "analytics": {"windows_s": [5, 10, 30, 60, 300], "buffer_seconds": 330},
    "logging": {
        "path": "logs/flowrank.log",
        "level": "INFO",
        "max_bytes": 5_000_000,
        "backup_count": 5,
    },
    "broker_aliases": {},
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    cfg_path = Path(path) if path else CONFIG_PATH
    data: dict[str, Any] = {}
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    return _deep_merge(DEFAULTS, data)


def save_config(config: dict[str, Any], path: Path | str | None = None) -> None:
    cfg_path = Path(path) if path else CONFIG_PATH
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(config, fh, allow_unicode=True, sort_keys=False)


def resolve_path(relative: str | Path) -> Path:
    p = Path(relative)
    return p if p.is_absolute() else PROJECT_ROOT / p
