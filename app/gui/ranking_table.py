"""Tabela de ranking com ordenação numérica por qualquer coluna."""

from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

POSITIVE = QColor("#2e9e4f")
NEGATIVE = QColor("#d05353")
NEUTRAL = QColor("#d8d8d8")


class SortableItem(QTableWidgetItem):
    """Item que ordena pelo valor real (não pelo texto formatado)."""

    def __init__(self, text: str, sort_value: Any = None) -> None:
        super().__init__(text)
        self._sort_value = sort_value if sort_value is not None else text
        self.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

    def __lt__(self, other: "QTableWidgetItem") -> bool:  # type: ignore[override]
        other_value = getattr(other, "_sort_value", other.text())
        try:
            return float(self._sort_value) < float(other_value)
        except (TypeError, ValueError):
            return str(self._sort_value) < str(other_value)


class Cell:
    __slots__ = ("text", "value", "color", "align")

    def __init__(self, text: str, value: Any = None, color: QColor | None = None, align: int = Qt.AlignRight | Qt.AlignVCenter):
        self.text = text
        self.value = value if value is not None else text
        self.color = color
        self.align = align


class RankingTable(QTableWidget):
    def __init__(self, headers: Sequence[str], parent=None) -> None:
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(list(headers))
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setShowGrid(False)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(headers)):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        header.setSortIndicatorShown(True)

    def set_rows(self, rows: Sequence[Sequence[Cell]]) -> None:
        sort_column = self.horizontalHeader().sortIndicatorSection()
        sort_order = self.horizontalHeader().sortIndicatorOrder()
        scroll = self.verticalScrollBar().value()

        self.setSortingEnabled(False)
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                item = SortableItem(cell.text, cell.value)
                item.setTextAlignment(cell.align)
                if cell.color is not None:
                    item.setForeground(QBrush(cell.color))
                self.setItem(r, c, item)
        self.setSortingEnabled(True)
        if sort_column >= 0:
            self.sortItems(sort_column, sort_order)
        self.verticalScrollBar().setValue(scroll)


def balance_color(value: float) -> QColor:
    if value > 0:
        return POSITIVE
    if value < 0:
        return NEGATIVE
    return NEUTRAL
