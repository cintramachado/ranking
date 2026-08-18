"""Exportação de ranking e negócios (CSV pt-BR e Parquet)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Sequence


def _format_ptbr(value: Any) -> Any:
    if isinstance(value, float):
        return f"{value:.2f}".replace(".", ",")
    return value


def export_csv(rows: Sequence[dict], path: str | Path) -> int:
    """CSV compatível com Excel brasileiro: separador ';' e decimal ','."""
    rows = list(rows)
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        file_path.write_text("", encoding="utf-8-sig")
        return 0
    fieldnames = list(rows[0].keys())
    with file_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _format_ptbr(v) for k, v in row.items()})
    return len(rows)


def export_parquet(rows: Sequence[dict], path: str | Path) -> int:
    import pandas as pd

    rows = list(rows)
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(file_path, index=False)
    return len(rows)
