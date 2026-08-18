"""Snapshot inspector e benchmark de tempos."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget


class DiagnosticsPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.summary = QLabel("Sem snapshots ainda.")
        self.summary.setWordWrap(True)
        self.bench = QLabel("")
        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setMaximumBlockCount(400)

        layout = QVBoxLayout(self)
        layout.addWidget(self.summary)
        layout.addWidget(self.bench)
        layout.addWidget(self.raw)

    def update_snapshot(self, payload: dict[str, Any]) -> None:
        self.summary.setText(
            "Último snapshot: {size} linhas visíveis | novos: {new} | sumiram: {gone} | "
            "inválidas: {invalid} | bloco lido: {block} linhas | baseline: {base}\n"
            "Leitura COM: {read:.1f} ms | diff: {diff:.2f} ms | agregação: {agg:.2f} ms | "
            "utilização: {util:.0%}".format(
                size=payload.get("size", 0),
                new=payload.get("new", 0),
                gone=payload.get("disappeared", 0),
                invalid=payload.get("invalid", 0),
                block=payload.get("block", 0),
                base="sim" if payload.get("baseline") else "não",
                read=payload.get("read_ms", 0.0),
                diff=payload.get("diff_ms", 0.0),
                agg=payload.get("agg_ms", 0.0),
                util=payload.get("utilization", 0.0),
            )
        )
        rows = payload.get("rows", [])
        self.raw.setPlainText(
            "\n".join(" | ".join("" if c is None else str(c) for c in row) for row in rows[:100])
        )

    def update_benchmark(self, metrics: dict[str, Any]) -> None:
        def fmt(name: str) -> str:
            data = metrics.get(name, {})
            return (
                f"{name}: avg {data.get('avg', 0)*1000:.2f} ms | p50 {data.get('p50', 0)*1000:.2f} "
                f"| p95 {data.get('p95', 0)*1000:.2f} | p99 {data.get('p99', 0)*1000:.2f}"
            )

        self.bench.setText(
            "\n".join(
                [
                    fmt("read"),
                    fmt("diff"),
                    fmt("agg"),
                    f"snapshots: {metrics.get('snapshots_total', 0)} "
                    f"({metrics.get('snapshots_per_second', 0):.2f}/s) | "
                    f"trades detectados: {metrics.get('trades_detected', 0)}",
                ]
            )
        )
