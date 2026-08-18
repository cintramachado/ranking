"""Camada SQLite do FlowRank."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.domain.trade import Trade
from app.utils.logger import get_logger

log = get_logger("persistence.database")

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capture_timestamp REAL NOT NULL,
    trade_time TEXT NOT NULL,
    symbol TEXT,
    price REAL,
    quantity INTEGER NOT NULL,
    broker TEXT NOT NULL,
    aggressor_side TEXT NOT NULL,
    session_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_session ON trades(session_date);
CREATE INDEX IF NOT EXISTS idx_trades_broker ON trades(broker);
CREATE INDEX IF NOT EXISTS idx_trades_side ON trades(aggressor_side);
CREATE INDEX IF NOT EXISTS idx_trades_capture ON trades(capture_timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_session_broker ON trades(session_date, broker);
"""


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()
            log.info("Banco aberto em %s", self.path)
        return self._conn

    @property
    def connection(self) -> sqlite3.Connection:
        return self.connect()

    def insert_trades(self, trades: Sequence[Trade]) -> int:
        if not trades:
            return 0
        conn = self.connection
        rows = [
            (
                t.capture_timestamp,
                t.trade_time,
                t.symbol,
                t.price,
                t.quantity,
                t.broker,
                t.aggressor_side,
                t.session_date,
            )
            for t in trades
        ]
        with conn:  # transação única por batch
            conn.executemany(
                "INSERT INTO trades (capture_timestamp, trade_time, symbol, price,"
                " quantity, broker, aggressor_side, session_date)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def sessions(self) -> list[str]:
        cur = self.connection.execute(
            "SELECT DISTINCT session_date FROM trades ORDER BY session_date DESC"
        )
        return [r[0] for r in cur.fetchall()]

    def brokers(self, session_date: str | None = None) -> list[str]:
        sql = "SELECT DISTINCT broker FROM trades"
        params: list[Any] = []
        if session_date:
            sql += " WHERE session_date = ?"
            params.append(session_date)
        sql += " ORDER BY broker"
        return [r[0] for r in self.connection.execute(sql, params).fetchall()]

    def count(self, session_date: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM trades"
        params: list[Any] = []
        if session_date:
            sql += " WHERE session_date = ?"
            params.append(session_date)
        return int(self.connection.execute(sql, params).fetchone()[0])

    def query_trades(
        self,
        session_date: str | None = None,
        broker: str | None = None,
        side: str | None = None,
        time_from: str | None = None,
        time_to: str | None = None,
        min_quantity: int | None = None,
        limit: int = 5000,
    ) -> list[sqlite3.Row]:
        sql = "SELECT * FROM trades WHERE 1=1"
        params: list[Any] = []
        if session_date:
            sql += " AND session_date = ?"
            params.append(session_date)
        if broker:
            sql += " AND broker LIKE ?"
            params.append(f"%{broker}%")
        if side:
            sql += " AND aggressor_side = ?"
            params.append(side)
        if time_from:
            sql += " AND trade_time >= ?"
            params.append(time_from)
        if time_to:
            sql += " AND trade_time <= ?"
            params.append(time_to)
        if min_quantity:
            sql += " AND quantity >= ?"
            params.append(int(min_quantity))
        sql += " ORDER BY capture_timestamp DESC, id DESC LIMIT ?"
        params.append(int(limit))
        return list(self.connection.execute(sql, params).fetchall())

    def iter_all(self, session_date: str | None = None) -> Iterable[sqlite3.Row]:
        sql = "SELECT * FROM trades"
        params: list[Any] = []
        if session_date:
            sql += " WHERE session_date = ?"
            params.append(session_date)
        sql += " ORDER BY id"
        yield from self.connection.execute(sql, params)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None
