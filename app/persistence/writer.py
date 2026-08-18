"""Thread consumidora da fila: grava trades em batch, sem bloquear a captura."""

from __future__ import annotations

import queue
import threading
import time

from app.domain.trade import Trade
from app.persistence.database import Database
from app.utils.logger import get_logger

log = get_logger("persistence.writer")


class DBWriter(threading.Thread):
    def __init__(
        self,
        database: Database,
        trade_queue: "queue.Queue[Trade]",
        flush_interval_ms: int = 1000,
        batch_size: int = 500,
    ) -> None:
        super().__init__(name="flowrank-dbwriter", daemon=True)
        self.database = database
        self.queue = trade_queue
        self.flush_interval = max(0.05, flush_interval_ms / 1000.0)
        self.batch_size = batch_size
        self.trades_persisted = 0
        self.db_errors = 0
        self._running = threading.Event()

    def run(self) -> None:
        self._running.set()
        self.database.connect()
        buffer: list[Trade] = []
        last_flush = time.perf_counter()
        while self._running.is_set() or not self.queue.empty() or buffer:
            timeout = max(0.01, self.flush_interval - (time.perf_counter() - last_flush))
            try:
                buffer.append(self.queue.get(timeout=timeout))
                while len(buffer) < self.batch_size:
                    buffer.append(self.queue.get_nowait())
            except queue.Empty:
                pass

            due = (time.perf_counter() - last_flush) >= self.flush_interval
            if buffer and (due or len(buffer) >= self.batch_size):
                self._flush(buffer)
                buffer = []
                last_flush = time.perf_counter()

            if not self._running.is_set() and self.queue.empty() and not buffer:
                break

        if buffer:
            self._flush(buffer)
        log.info("DBWriter finalizado (%d trades persistidos)", self.trades_persisted)

    def _flush(self, buffer: list[Trade]) -> None:
        try:
            self.trades_persisted += self.database.insert_trades(buffer)
        except Exception as exc:  # noqa: BLE001
            self.db_errors += 1
            log.error("Erro ao gravar batch de %d trades: %s", len(buffer), exc)

    def stop(self, drain_timeout: float = 5.0) -> None:
        """Encerra processando o que restou na fila."""
        self._running.clear()
        self.join(timeout=drain_timeout)
