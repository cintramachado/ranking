"""Diagnóstico de linha de comando: conecta ao Excel aberto e mostra o que foi detectado.

Uso: python -m tools.check_excel [segundos]
"""

from __future__ import annotations

import sys
import time

from app.capture.multiset_diff import MultisetDiff
from app.config import load_config
from app.excel.connector import ExcelConnector, com_initialize, com_uninitialize
from app.excel.detector import detect_table
from app.excel.snapshot import SnapshotReader


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    config = load_config()
    com_initialize()
    try:
        app = ExcelConnector().connect()
        location = detect_table(app)
        if location is None:
            print("Tabela de Times & Trades não encontrada nas planilhas abertas.")
            return 1
        for line in location.describe():
            print(line)

        ws = app.Workbooks(location.workbook_name).Worksheets(location.worksheet_name)
        reader = SnapshotReader(location, config["capture"]["max_rows"])
        diff = MultisetDiff()
        interval = config["capture"]["interval_ms"] / 1000.0

        deadline = time.time() + seconds
        total_new = 0
        snapshots = 0
        while time.time() < deadline:
            snap = reader.read(ws)
            result = diff.update(snap.keys)
            snapshots += 1
            total_new += result.new_count
            print(
                f"snapshot {snapshots:>3} | linhas={result.snapshot_size:>4} "
                f"novos={result.new_count:>3} sumiram={result.disappeared:>3} "
                f"baseline={result.is_baseline} leitura={snap.read_seconds*1000:.1f} ms"
            )
            time.sleep(interval)

        print(f"\nTotal de negócios novos em {seconds:.0f}s: {total_new}")
        if snap.keys:
            print("Primeiras linhas do último snapshot:")
            for key in snap.keys[:5]:
                print("  ", key)
        return 0
    finally:
        com_uninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
