"""Janelas móveis em memória (nunca consultam o SQLite)."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import replace
from typing import Iterable, Sequence

from app.domain.broker_stats import WindowStats
from app.domain.trade import Trade
from app.utils.normalization import SIDE_BUY, SIDE_RLP, SIDE_SELL

DEFAULT_WINDOWS = (5, 10, 30, 60, 300)


class RollingFlow:
    """Buffer temporal de eventos usado para calcular fluxo por janela."""

    def __init__(self, buffer_seconds: float = 330.0) -> None:
        self.buffer_seconds = buffer_seconds
        self._events: deque[tuple[float, str, str, int]] = deque()

    def __len__(self) -> int:
        return len(self._events)

    def clear(self) -> None:
        self._events.clear()

    def add(self, trade: Trade) -> None:
        self._events.append(
            (trade.capture_timestamp, trade.broker, trade.aggressor_side, trade.quantity)
        )

    def add_many(self, trades: Iterable[Trade]) -> None:
        for trade in trades:
            self.add(trade)

    def prune(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        limit = now - self.buffer_seconds
        events = self._events
        while events and events[0][0] < limit:
            events.popleft()

    def compute(
        self,
        windows: Sequence[int] = DEFAULT_WINDOWS,
        now: float | None = None,
        accel_window: int = 10,
    ) -> tuple[dict[str, dict[int, WindowStats]], dict[str, WindowStats]]:
        """Uma única passagem reversa produz todas as janelas + bucket de aceleração.

        Retorna (por_corretora[janela] -> WindowStats, bucket_anterior_por_corretora).
        """
        now = now if now is not None else time.time()
        bounds = sorted({int(w) for w in windows if w > 0})
        if not bounds:
            return {}, {}

        cumulative: dict[str, WindowStats] = {}
        previous_bucket: dict[str, WindowStats] = {}
        results: dict[int, dict[str, WindowStats]] = {}
        idx = 0

        for ts, broker, side, qty in reversed(self._events):
            age = now - ts
            while idx < len(bounds) and age > bounds[idx]:
                results[bounds[idx]] = {b: replace(s) for b, s in cumulative.items()}
                idx += 1
            if idx < len(bounds):
                _apply(cumulative.setdefault(broker, WindowStats()), side, qty)
            if accel_window < age <= 2 * accel_window:
                _apply(previous_bucket.setdefault(broker, WindowStats()), side, qty)
            if idx >= len(bounds) and age > 2 * accel_window:
                break

        while idx < len(bounds):
            results[bounds[idx]] = {b: replace(s) for b, s in cumulative.items()}
            idx += 1

        by_broker: dict[str, dict[int, WindowStats]] = {}
        for window, stats_map in results.items():
            for broker, stats in stats_map.items():
                by_broker.setdefault(broker, {})[window] = stats
        return by_broker, previous_bucket


def _apply(stats: WindowStats, side: str, qty: int) -> None:
    if side == SIDE_BUY:
        stats.buy_volume += qty
        stats.buy_count += 1
    elif side == SIDE_SELL:
        stats.sell_volume += qty
        stats.sell_count += 1
    elif side == SIDE_RLP:
        stats.rlp_volume += qty


def classify_acceleration(
    recent: WindowStats | None, previous: WindowStats | None, min_delta: int = 100
) -> str:
    """Compara os últimos N s com os N s imediatamente anteriores (métrica informativa)."""
    recent_balance = recent.balance if recent else 0
    previous_balance = previous.balance if previous else 0
    delta = recent_balance - previous_balance
    if delta >= min_delta:
        return "ACELERANDO COMPRA"
    if delta <= -min_delta:
        return "ACELERANDO VENDA"
    return ""
