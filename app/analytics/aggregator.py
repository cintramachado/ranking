"""Agregação em memória: totais do pregão + janelas móveis. Thread-safe."""

from __future__ import annotations

import datetime as dt
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from app.analytics.rolling_windows import DEFAULT_WINDOWS, RollingFlow, classify_acceleration
from app.domain.broker_stats import BrokerRow, BrokerStats
from app.domain.trade import Trade
from app.utils.logger import get_logger
from app.utils.normalization import SIDE_BUY, SIDE_RLP, SIDE_SELL

log = get_logger("analytics.aggregator")


@dataclass
class AggregateSnapshot:
    session_date: str
    symbol: str
    last_price: float | None
    total_trades: int
    total_volume: int
    buy_volume: int
    sell_volume: int
    rlp_volume: int
    trades_per_second: float
    contracts_per_second: float
    rows: list[BrokerRow] = field(default_factory=list)
    windows: tuple[int, ...] = DEFAULT_WINDOWS

    @property
    def balance(self) -> int:
        return self.buy_volume - self.sell_volume


class Aggregator:
    def __init__(
        self,
        windows: Sequence[int] = DEFAULT_WINDOWS,
        buffer_seconds: float = 330.0,
        accel_window: int = 10,
    ) -> None:
        self.windows = tuple(sorted({int(w) for w in windows}))
        self.accel_window = accel_window
        self._lock = threading.Lock()
        self._flow = RollingFlow(buffer_seconds)
        self._stats: dict[str, BrokerStats] = {}
        self._session_date = dt.date.today().isoformat()
        self._symbol = ""
        self._last_price: float | None = None
        self._total_trades = 0
        self._total_volume = 0
        self._buy_volume = 0
        self._sell_volume = 0
        self._rlp_volume = 0
        self._rate_marks: list[tuple[float, int]] = []

    # ---------------------------------------------------------------- escrita
    def add_trades(
        self,
        trades: Iterable[Trade],
        row_count: int | None = None,
        row_volume: int | None = None,
    ) -> None:
        """row_count/row_volume descrevem as linhas originais da planilha.

        No layout de contraparte cada linha vira 2 trades (compra + venda); os
        totais globais devem continuar refletindo o número real de negócios.
        """
        trades = list(trades)
        if not trades:
            return
        with self._lock:
            session = trades[0].session_date
            if session != self._session_date:
                log.info("Nova sessão detectada: %s -> %s", self._session_date, session)
                self._reset_locked(session)
            for trade in trades:
                self._apply_locked(trade)
            self._total_trades += row_count if row_count is not None else len(trades)
            self._total_volume += (
                row_volume if row_volume is not None else sum(t.quantity for t in trades)
            )
            self._flow.add_many(trades)
            self._flow.prune(trades[-1].capture_timestamp)
            self._rate_marks.append(
                (trades[-1].capture_timestamp, sum(t.quantity for t in trades))
            )
            self._trim_rate_marks(trades[-1].capture_timestamp)
            if trades[0].symbol and not self._symbol:
                self._symbol = trades[0].symbol

    def _apply_locked(self, trade: Trade) -> None:
        stats = self._stats.get(trade.broker)
        if stats is None:
            stats = BrokerStats(broker=trade.broker)
            self._stats[trade.broker] = stats
        qty = trade.quantity
        stats.total_volume += qty
        stats.max_lot = max(stats.max_lot, qty)
        if trade.aggressor_side == SIDE_BUY:
            stats.buy_volume += qty
            stats.buy_count += 1
            self._buy_volume += qty
        elif trade.aggressor_side == SIDE_SELL:
            stats.sell_volume += qty
            stats.sell_count += 1
            self._sell_volume += qty
        elif trade.aggressor_side == SIDE_RLP:
            stats.rlp_volume += qty
            stats.rlp_count += 1
            self._rlp_volume += qty
        else:
            stats.rlp_count += 1

    def _trim_rate_marks(self, now: float) -> None:
        limit = now - 60.0
        self._rate_marks = [m for m in self._rate_marks if m[0] >= limit]

    def _reset_locked(self, session_date: str) -> None:
        self._stats.clear()
        self._flow.clear()
        self._session_date = session_date
        self._total_trades = 0
        self._total_volume = 0
        self._buy_volume = 0
        self._sell_volume = 0
        self._rlp_volume = 0
        self._rate_marks.clear()

    def set_last_price(self, price: float) -> None:
        with self._lock:
            self._last_price = price

    def set_symbol(self, symbol: str) -> None:
        with self._lock:
            self._symbol = symbol

    def reset(self) -> None:
        with self._lock:
            self._reset_locked(dt.date.today().isoformat())

    # ---------------------------------------------------------------- leitura
    def snapshot(self, now: float | None = None) -> AggregateSnapshot:
        now = now if now is not None else time.time()
        with self._lock:
            self._flow.prune(now)
            window_map, previous_bucket = self._flow.compute(
                self.windows, now=now, accel_window=self.accel_window
            )
            rows = []
            for broker, stats in self._stats.items():
                windows = window_map.get(broker, {})
                rows.append(
                    BrokerRow(
                        broker=broker,
                        buy_volume=stats.buy_volume,
                        sell_volume=stats.sell_volume,
                        balance=stats.balance,
                        trade_count=stats.trade_count,
                        avg_lot=stats.avg_lot,
                        max_lot=stats.max_lot,
                        rlp_volume=stats.rlp_volume,
                        windows=windows,
                        acceleration=classify_acceleration(
                            windows.get(self.accel_window), previous_bucket.get(broker)
                        ),
                    )
                )
            trades_ps, contracts_ps = self._rates_locked(now)
            return AggregateSnapshot(
                session_date=self._session_date,
                symbol=self._symbol,
                last_price=self._last_price,
                total_trades=self._total_trades,
                total_volume=self._total_volume,
                buy_volume=self._buy_volume,
                sell_volume=self._sell_volume,
                rlp_volume=self._rlp_volume,
                trades_per_second=trades_ps,
                contracts_per_second=contracts_ps,
                rows=rows,
                windows=self.windows,
            )

    def _rates_locked(self, now: float) -> tuple[float, float]:
        window = 10.0
        limit = now - window
        events = [e for e in self._flow._events if e[0] >= limit]  # noqa: SLF001
        if not events:
            return 0.0, 0.0
        return len(events) / window, sum(e[3] for e in events) / window
