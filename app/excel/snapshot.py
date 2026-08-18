"""Leitura de um snapshot da tabela de Times & Trades."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.domain.trade import TradeKey
from app.excel.detector import TableLocation
from app.utils.normalization import (
    FIELD_BROKER,
    FIELD_PRICE,
    FIELD_QUANTITY,
    FIELD_SIDE,
    FIELD_TIME,
    normalize_broker,
    normalize_side,
    normalize_time,
    parse_number,
    parse_quantity,
)

MIN_BLOCK = 128


@dataclass(slots=True)
class Snapshot:
    keys: list[TradeKey]
    raw_rows: list[tuple]
    read_seconds: float
    block_size: int
    last_price: float | None = None
    invalid_rows: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.keys)


class SnapshotReader:
    """Lê a região de dados abaixo do cabeçalho em uma única chamada COM."""

    def __init__(self, location: TableLocation, max_rows: int = 5000, aliases: dict | None = None):
        self.location = location
        self.max_rows = max(MIN_BLOCK, int(max_rows))
        self.aliases = aliases or {}
        self._block = MIN_BLOCK

    def read(self, worksheet: Any) -> Snapshot:
        loc = self.location
        first_col = loc.first_column
        last_col = loc.last_column
        start_row = loc.header_row + 1
        block = min(self._block, self.max_rows)
        end_row = start_row + block - 1

        t0 = time.perf_counter()
        rng = worksheet.Range(
            worksheet.Cells(start_row, first_col), worksheet.Cells(end_row, last_col)
        )
        values = rng.Value
        read_seconds = time.perf_counter() - t0

        rows = _as_rows(values)
        keys, raw_rows, invalid, last_price = self._convert(rows, first_col)

        used = len(raw_rows)
        if used >= block and block < self.max_rows:
            self._block = min(self.max_rows, block * 2)
        elif used * 4 < block and block > MIN_BLOCK:
            self._block = max(MIN_BLOCK, block // 2)

        return Snapshot(
            keys=keys,
            raw_rows=raw_rows,
            read_seconds=read_seconds,
            block_size=block,
            last_price=last_price,
            invalid_rows=invalid,
        )

    def _convert(
        self, rows: list[tuple], first_col: int
    ) -> tuple[list[TradeKey], list[tuple], int, float | None]:
        loc = self.location
        idx_time = loc.columns[FIELD_TIME] - first_col
        idx_qty = loc.columns[FIELD_QUANTITY] - first_col
        idx_broker = loc.columns[FIELD_BROKER] - first_col
        idx_side = loc.columns[FIELD_SIDE] - first_col
        idx_price = loc.columns.get(FIELD_PRICE)
        idx_price = idx_price - first_col if idx_price is not None else None

        keys: list[TradeKey] = []
        raw_rows: list[tuple] = []
        invalid = 0
        last_price: float | None = None
        empty_streak = 0

        for row in rows:
            if _is_empty(row):
                empty_streak += 1
                if empty_streak >= 2:  # duas linhas vazias encerram a tabela
                    break
                continue
            empty_streak = 0

            trade_time = normalize_time(row[idx_time]) if idx_time < len(row) else ""
            quantity = parse_quantity(row[idx_qty]) if idx_qty < len(row) else None
            broker = normalize_broker(row[idx_broker], self.aliases) if idx_broker < len(row) else ""
            side = normalize_side(row[idx_side]) if idx_side < len(row) else ""
            price = 0.0
            if idx_price is not None and idx_price < len(row):
                price = parse_number(row[idx_price]) or 0.0

            if not trade_time or quantity is None or quantity <= 0 or not broker:
                invalid += 1
                continue

            if last_price is None and price:
                last_price = price

            keys.append(TradeKey(trade_time, price, quantity, broker, side))
            raw_rows.append(tuple(row))

        return keys, raw_rows, invalid, last_price


def _as_rows(values: Any) -> list[tuple]:
    if values is None:
        return []
    if not isinstance(values, tuple):
        return [(values,)]
    if values and isinstance(values[0], tuple):
        return list(values)
    return [values]


def _is_empty(row: tuple) -> bool:
    for cell in row:
        if cell is None:
            continue
        if isinstance(cell, str) and not cell.strip():
            continue
        return False
    return True
