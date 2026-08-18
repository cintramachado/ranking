"""Worker de captura: roda em thread própria, nunca na thread da GUI."""

from __future__ import annotations

import datetime as dt
import queue
import statistics
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QThread, Signal

from app.analytics.aggregator import Aggregator
from app.capture.multiset_diff import MultisetDiff
from app.domain.trade import Trade
from app.excel.connector import ExcelConnector, ExcelUnavailable, com_initialize, com_uninitialize
from app.excel.detector import TableLocation, detect_table
from app.excel.snapshot import Snapshot, SnapshotReader
from app.utils.logger import get_logger

log = get_logger("capture.worker")

RECONNECT_INTERVAL_S = 2.0


@dataclass
class CaptureMetrics:
    connected: bool = False
    snapshots_total: int = 0
    trades_detected: int = 0
    com_errors: int = 0
    last_snapshot_ts: float = 0.0
    last_trade_ts: float = 0.0
    last_snapshot_size: int = 0
    last_new_count: int = 0
    utilization: float = 0.0
    snapshots_per_second: float = 0.0
    read_times: deque = field(default_factory=lambda: deque(maxlen=500))
    diff_times: deque = field(default_factory=lambda: deque(maxlen=500))
    agg_times: deque = field(default_factory=lambda: deque(maxlen=500))
    location: TableLocation | None = None
    last_error: str = ""

    def percentiles(self, samples: deque) -> dict[str, float]:
        data = sorted(samples)
        if not data:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "avg": 0.0}
        def pick(p: float) -> float:
            idx = min(len(data) - 1, int(p * len(data)))
            return data[idx]
        return {
            "p50": pick(0.50),
            "p95": pick(0.95),
            "p99": pick(0.99),
            "avg": statistics.fmean(data),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "snapshots_total": self.snapshots_total,
            "trades_detected": self.trades_detected,
            "com_errors": self.com_errors,
            "last_snapshot_ts": self.last_snapshot_ts,
            "last_trade_ts": self.last_trade_ts,
            "last_snapshot_size": self.last_snapshot_size,
            "last_new_count": self.last_new_count,
            "utilization": self.utilization,
            "snapshots_per_second": self.snapshots_per_second,
            "read": self.percentiles(self.read_times),
            "diff": self.percentiles(self.diff_times),
            "agg": self.percentiles(self.agg_times),
            "last_error": self.last_error,
            "workbook": self.location.workbook_name if self.location else "",
            "worksheet": self.location.worksheet_name if self.location else "",
            "header_row": self.location.header_row if self.location else 0,
            "symbol": self.location.symbol if self.location else "",
        }


class CaptureWorker(QThread):
    connected = Signal(list)          # linhas descritivas da tabela detectada
    disconnected = Signal(str)
    metricsUpdated = Signal(dict)
    snapshotTaken = Signal(dict)      # dados para o snapshot inspector

    def __init__(
        self,
        aggregator: Aggregator,
        db_queue: "queue.Queue[Trade]",
        interval_ms: int = 250,
        max_rows: int = 5000,
        symbol_override: str = "",
        aliases: dict | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.aggregator = aggregator
        self.db_queue = db_queue
        self.interval_s = max(0.05, interval_ms / 1000.0)
        self.max_rows = max_rows
        self.symbol_override = symbol_override
        self.aliases = aliases or {}

        self._running = False
        self._connector = ExcelConnector()
        self._diff = MultisetDiff()
        self._reader: SnapshotReader | None = None
        self._worksheet: Any = None
        self._location: TableLocation | None = None
        self.metrics = CaptureMetrics()
        self._snapshot_marks: deque[float] = deque(maxlen=40)
        self._last_snapshot_payload: dict[str, Any] = {}

    # ------------------------------------------------------------------ API
    def set_interval_ms(self, interval_ms: int) -> None:
        self.interval_s = max(0.05, interval_ms / 1000.0)

    def set_symbol(self, symbol: str) -> None:
        self.symbol_override = symbol

    def stop(self) -> None:
        self._running = False

    def last_snapshot(self) -> dict[str, Any]:
        return self._last_snapshot_payload

    # ---------------------------------------------------------------- thread
    def run(self) -> None:  # noqa: C901 - laço principal
        com_initialize()
        self._running = True
        log.info("Captura iniciada (intervalo=%.0f ms)", self.interval_s * 1000)
        next_reconnect = 0.0
        try:
            while self._running:
                loop_start = time.perf_counter()
                if not self.metrics.connected:
                    if time.time() >= next_reconnect:
                        if not self._try_connect():
                            next_reconnect = time.time() + RECONNECT_INTERVAL_S
                    self.metricsUpdated.emit(self.metrics.as_dict())
                    self._sleep_remaining(loop_start)
                    continue

                try:
                    self._capture_once()
                except Exception as exc:  # noqa: BLE001
                    self._handle_com_error(exc)
                    next_reconnect = time.time() + RECONNECT_INTERVAL_S

                self.metricsUpdated.emit(self.metrics.as_dict())
                self._sleep_remaining(loop_start)
        finally:
            com_uninitialize()
            log.info("Captura encerrada")

    # ------------------------------------------------------------- internals
    def _sleep_remaining(self, loop_start: float) -> None:
        elapsed = time.perf_counter() - loop_start
        remaining = self.interval_s - elapsed
        if remaining > 0:
            self.msleep(int(remaining * 1000))

    def _try_connect(self) -> bool:
        try:
            app = self._connector.connect()
            location = detect_table(app)
            if location is None:
                self.metrics.last_error = "Tabela de Times & Trades não encontrada"
                self.disconnected.emit(self.metrics.last_error)
                return False
            wb = app.Workbooks(location.workbook_name)
            self._worksheet = wb.Worksheets(location.worksheet_name)
            self._location = location
            self.metrics.location = location
            self._reader = SnapshotReader(location, self.max_rows, self.aliases)
            self._diff.reset()  # primeiro snapshot após (re)conexão é apenas baseline
            self.metrics.connected = True
            self.metrics.last_error = ""
            self.connected.emit(location.describe())
            return True
        except ExcelUnavailable as exc:
            self.metrics.last_error = str(exc)
            self.disconnected.emit(str(exc))
            return False
        except Exception as exc:  # noqa: BLE001
            self.metrics.com_errors += 1
            self.metrics.last_error = str(exc)
            log.warning("Falha ao conectar/detectar: %s", exc)
            self.disconnected.emit(str(exc))
            return False

    def _handle_com_error(self, exc: Exception) -> None:
        self.metrics.com_errors += 1
        self.metrics.connected = False
        self.metrics.last_error = str(exc)
        self._worksheet = None
        self._reader = None
        self._connector.disconnect()
        self._diff.reset()
        log.warning("Erro COM durante captura: %s", exc)
        self.disconnected.emit(str(exc))

    def _capture_once(self) -> None:
        assert self._reader is not None
        snapshot: Snapshot = self._reader.read(self._worksheet)

        t0 = time.perf_counter()
        result = self._diff.update(snapshot.keys)
        diff_seconds = time.perf_counter() - t0

        now = time.time()
        symbol = self.symbol_override or (self._location.symbol if self._location else "")
        session_date = dt.date.today().isoformat()

        agg_seconds = 0.0
        if result.new_items:
            trades = [
                Trade.from_key(key, now, symbol=symbol, session_date=session_date)
                for key in result.new_items
            ]
            t1 = time.perf_counter()
            self.aggregator.add_trades(trades)
            agg_seconds = time.perf_counter() - t1
            for trade in trades:
                try:
                    self.db_queue.put_nowait(trade)
                except queue.Full:  # nunca bloqueia o coletor
                    log.warning("Fila de persistência cheia; trade descartado do DB")
            self.metrics.trades_detected += len(trades)
            self.metrics.last_trade_ts = now

        self._snapshot_marks.append(now)
        self.metrics.snapshots_total += 1
        self.metrics.last_snapshot_ts = now
        self.metrics.last_snapshot_size = result.snapshot_size
        self.metrics.last_new_count = result.new_count
        self.metrics.utilization = result.utilization
        self.metrics.read_times.append(snapshot.read_seconds)
        self.metrics.diff_times.append(diff_seconds)
        self.metrics.agg_times.append(agg_seconds)
        self.metrics.snapshots_per_second = self._snapshot_rate()
        if snapshot.last_price:
            self.aggregator.set_last_price(snapshot.last_price)

        self._last_snapshot_payload = {
            "rows": snapshot.raw_rows[:200],
            "size": snapshot.size,
            "new": result.new_count,
            "disappeared": result.disappeared,
            "baseline": result.is_baseline,
            "invalid": snapshot.invalid_rows,
            "read_ms": snapshot.read_seconds * 1000,
            "diff_ms": diff_seconds * 1000,
            "agg_ms": agg_seconds * 1000,
            "block": snapshot.block_size,
            "utilization": result.utilization,
        }
        self.snapshotTaken.emit(self._last_snapshot_payload)

    def _snapshot_rate(self) -> float:
        if len(self._snapshot_marks) < 2:
            return 0.0
        span = self._snapshot_marks[-1] - self._snapshot_marks[0]
        if span <= 0:
            return 0.0
        return (len(self._snapshot_marks) - 1) / span
