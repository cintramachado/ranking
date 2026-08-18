"""Tela de histórico com filtros sobre o SQLite."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.gui.ranking_table import Cell, RankingTable
from app.persistence.database import Database
from app.persistence.export import export_csv
from app.utils.normalization import SIDE_BUY, SIDE_RLP, SIDE_SELL, format_int_ptbr

HEADERS = ("Hora", "Ativo", "Preço", "Qtd", "Corretora", "Lado", "Captura")


class HistoryDialog(QDialog):
    def __init__(self, database: Database, parent=None) -> None:
        super().__init__(parent)
        self.database = database
        self.setWindowTitle("FlowRank - Histórico")
        self.resize(900, 600)

        self.session = QComboBox()
        self.session.addItem("(todas)")
        for s in database.sessions():
            self.session.addItem(s)
        self.broker = QLineEdit()
        self.side = QComboBox()
        self.side.addItems(["Todos", SIDE_BUY, SIDE_SELL, SIDE_RLP])
        self.time_from = QLineEdit()
        self.time_from.setPlaceholderText("09:00:00.000")
        self.time_to = QLineEdit()
        self.time_to.setPlaceholderText("18:00:00.000")
        self.min_qty = QSpinBox()
        self.min_qty.setRange(0, 1_000_000)
        self.limit = QSpinBox()
        self.limit.setRange(100, 500_000)
        self.limit.setValue(5000)

        form = QFormLayout()
        form.addRow("Sessão", self.session)
        form.addRow("Corretora", self.broker)
        form.addRow("Lado", self.side)
        form.addRow("Hora inicial", self.time_from)
        form.addRow("Hora final", self.time_to)
        form.addRow("Quantidade mínima", self.min_qty)
        form.addRow("Limite", self.limit)

        self.table = RankingTable(HEADERS)
        self.summary = QLabel("")

        search_btn = QPushButton("Consultar")
        search_btn.clicked.connect(self.refresh)
        export_btn = QPushButton("Exportar CSV")
        export_btn.clicked.connect(self.export)

        buttons = QHBoxLayout()
        buttons.addWidget(search_btn)
        buttons.addWidget(export_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.summary)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.table)

        self._rows: list[dict] = []
        self.refresh()

    def _filters(self) -> dict:
        return {
            "session_date": None if self.session.currentIndex() == 0 else self.session.currentText(),
            "broker": self.broker.text().strip() or None,
            "side": None if self.side.currentIndex() == 0 else self.side.currentText(),
            "time_from": self.time_from.text().strip() or None,
            "time_to": self.time_to.text().strip() or None,
            "min_quantity": self.min_qty.value() or None,
            "limit": self.limit.value(),
        }

    def refresh(self) -> None:
        rows = self.database.query_trades(**self._filters())
        self._rows = [dict(r) for r in rows]
        cells = [
            [
                Cell(r["trade_time"], r["trade_time"]),
                Cell(r["symbol"] or "", r["symbol"] or ""),
                Cell(f"{r['price']:.2f}".replace(".", ","), r["price"]),
                Cell(format_int_ptbr(r["quantity"]), r["quantity"]),
                Cell(r["broker"], r["broker"]),
                Cell(r["aggressor_side"], r["aggressor_side"]),
                Cell(f"{r['capture_timestamp']:.3f}", r["capture_timestamp"]),
            ]
            for r in self._rows
        ]
        self.table.set_rows(cells)
        total = sum(r["quantity"] for r in self._rows)
        self.summary.setText(
            f"{len(self._rows)} negócios | {format_int_ptbr(total)} contratos"
        )

    def export(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "FlowRank", "Nada para exportar.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar negócios", "negocios.csv", "CSV (*.csv)")
        if not path:
            return
        export_csv(self._rows, path)
        QMessageBox.information(self, "FlowRank", f"{len(self._rows)} negócios exportados.")
