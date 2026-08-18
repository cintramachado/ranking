"""Barra de saúde: Excel, RTD, fila, banco, capture risk."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

GREEN = "#2e9e4f"
YELLOW = "#d1a01f"
RED = "#d05353"
GREY = "#8a8a8a"


class HealthBar(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(16)

        self.state = QLabel("● DESCONECTADO")
        self.excel = QLabel("Excel: -")
        self.rtd = QLabel("Último negócio: -")
        self.snapshots = QLabel("Snapshots: 0 (0/s)")
        self.queue = QLabel("Fila: 0")
        self.db = QLabel("Banco: 0")
        self.risk = QLabel("Capture risk: 0%")
        self.errors = QLabel("Erros COM: 0 | DB: 0")

        for w in (
            self.state,
            self.excel,
            self.rtd,
            self.snapshots,
            self.queue,
            self.db,
            self.risk,
            self.errors,
        ):
            layout.addWidget(w)
        layout.addStretch(1)

    def update_state(self, color: str, text: str) -> None:
        self.state.setText(f"● {text}")
        self.state.setStyleSheet(f"color: {color}; font-weight: 600;")

    def update_risk(self, utilization: float, warn: float, critical: float) -> None:
        pct = utilization * 100
        color = GREEN
        label = "Capture risk"
        if utilization >= critical:
            color = RED
            label = "CAPTURE RISK"
        elif utilization >= warn:
            color = YELLOW
            label = "CAPTURE RISK"
        self.risk.setText(f"{label}: {pct:.0f}%")
        self.risk.setStyleSheet(f"color: {color};")
