"""Janela principal do FlowRank."""

from __future__ import annotations

import queue
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.analytics.aggregator import Aggregator
from app.analytics.ranking import (
    FILTER_ALL,
    FILTER_BUY,
    FILTER_RLP,
    FILTER_SELL,
    balance_ranking,
    filter_rows,
    ranking_export_rows,
    top_buyers,
    top_sellers,
)
from app.capture.worker import CaptureWorker
from app.config import resolve_path, save_config
from app.domain.trade import Trade
from app.gui.diagnostics import DiagnosticsPanel
from app.gui.history_dialog import HistoryDialog
from app.gui.ranking_table import Cell, RankingTable, balance_color
from app.gui.status_bar import GREEN, GREY, RED, YELLOW, HealthBar
from app.persistence.database import Database
from app.persistence.export import export_csv, export_parquet
from app.persistence.writer import DBWriter
from app.utils.logger import get_logger
from app.utils.normalization import format_int_ptbr, format_signed_ptbr

log = get_logger("gui")

INTERVAL_OPTIONS = [100, 200, 250, 500, 1000]


class MainWindow(QMainWindow):
    def __init__(self, config: dict) -> None:
        super().__init__()
        self.config = config
        self.setWindowTitle("FlowRank")
        self.resize(1360, 860)

        analytics_cfg = config["analytics"]
        capture_cfg = config["capture"]
        db_cfg = config["database"]

        self.aggregator = Aggregator(
            windows=analytics_cfg["windows_s"],
            buffer_seconds=analytics_cfg["buffer_seconds"],
        )
        self.trade_queue: "queue.Queue[Trade]" = queue.Queue(maxsize=200_000)
        self.database = Database(resolve_path(db_cfg["path"]))
        self.db_writer = DBWriter(
            self.database,
            self.trade_queue,
            flush_interval_ms=db_cfg["flush_interval_ms"],
            batch_size=db_cfg["batch_size"],
        )
        self.db_writer.start()

        self.worker: CaptureWorker | None = None
        self._windows = tuple(self.aggregator.windows)
        self._short_window = 30 if 30 in self._windows else self._windows[0]
        self._last_metrics: dict = {}

        self._build_ui()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_view)
        self.refresh_timer.start(int(config["gui"]["refresh_ms"]))

    # ------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)

        root.addLayout(self._build_header())
        root.addLayout(self._build_controls())

        tabs = QTabWidget()
        tabs.addTab(self._build_ranking_tab(), "Ranking")
        self.diagnostics = DiagnosticsPanel()
        tabs.addTab(self.diagnostics, "Diagnóstico")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        tabs.addTab(self.log_view, "Log")
        root.addWidget(tabs, 1)

        self.health = HealthBar()
        root.addWidget(self.health)
        self.health.update_state(GREY, "PARADO")

        self.setCentralWidget(central)
        self._build_menu()

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.title = QLabel("FLOWRANK")
        self.title.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.symbol_label = QLabel("-")
        self.symbol_label.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.metrics_label = QLabel("Aguardando captura")
        self.metrics_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.title)
        layout.addWidget(self.symbol_label)
        layout.addStretch(1)
        layout.addWidget(self.metrics_label)
        return layout

    def _build_controls(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_capture)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_capture)
        self.stop_btn.setEnabled(False)

        self.interval_combo = QComboBox()
        for ms in INTERVAL_OPTIONS:
            self.interval_combo.addItem(f"{ms} ms", ms)
        current = int(self.config["capture"]["interval_ms"])
        if current not in INTERVAL_OPTIONS:
            self.interval_combo.addItem(f"{current} ms", current)
        self.interval_combo.setCurrentIndex(self.interval_combo.findData(current))
        self.interval_combo.currentIndexChanged.connect(self._interval_changed)

        self.symbol_edit = QLineEdit()
        self.symbol_edit.setPlaceholderText("Ativo (auto)")
        self.symbol_edit.setMaximumWidth(140)
        self.symbol_edit.editingFinished.connect(self._symbol_changed)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems([FILTER_ALL, FILTER_BUY, FILTER_SELL, FILTER_RLP])
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar corretora")
        self.search_edit.setMaximumWidth(200)

        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)
        layout.addWidget(QLabel("Intervalo:"))
        layout.addWidget(self.interval_combo)
        layout.addWidget(QLabel("Ativo:"))
        layout.addWidget(self.symbol_edit)
        layout.addWidget(QLabel("Filtro:"))
        layout.addWidget(self.filter_combo)
        layout.addWidget(self.search_edit)
        layout.addStretch(1)
        return layout

    def _build_ranking_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QSplitter(Qt.Horizontal)
        self.buyers_table = RankingTable(("Corretora", "Qtd comprada", f"{self._short_window}s"))
        self.sellers_table = RankingTable(("Corretora", "Qtd vendida", f"{self._short_window}s"))
        top.addWidget(_group("MAIORES COMPRADORES", self.buyers_table))
        top.addWidget(_group("MAIORES VENDEDORES", self.sellers_table))
        top.setSizes([500, 500])

        headers = ["Corretora", "Compra", "Venda", "Saldo", "Negócios", "Lote médio", "Maior lote"]
        headers += [f"Saldo {w}s" if w < 60 else f"Saldo {w // 60}min" for w in self._windows]
        headers += ["Contratos/s", "Aceleração"]
        self.balance_table = RankingTable(headers)

        layout.addWidget(top, 1)
        layout.addWidget(_group("RANKING POR SALDO", self.balance_table), 2)
        return widget

    def _build_menu(self) -> None:
        menu = self.menuBar()
        file_menu = menu.addMenu("Arquivo")

        history = QAction("Histórico...", self)
        history.triggered.connect(self.open_history)
        file_menu.addAction(history)
        file_menu.addSeparator()

        export_ranking = QAction("Exportar ranking (CSV)", self)
        export_ranking.triggered.connect(self.export_ranking_csv)
        file_menu.addAction(export_ranking)

        export_trades = QAction("Exportar negócios da sessão (CSV)", self)
        export_trades.triggered.connect(lambda: self.export_trades("csv"))
        file_menu.addAction(export_trades)

        export_pq = QAction("Exportar negócios da sessão (Parquet)", self)
        export_pq.triggered.connect(lambda: self.export_trades("parquet"))
        file_menu.addAction(export_pq)

        file_menu.addSeparator()
        quit_action = QAction("Sair", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

    # -------------------------------------------------------------- captura
    def start_capture(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.worker = CaptureWorker(
            aggregator=self.aggregator,
            db_queue=self.trade_queue,
            interval_ms=int(self.interval_combo.currentData()),
            max_rows=int(self.config["capture"]["max_rows"]),
            symbol_override=self.symbol_edit.text().strip(),
            aliases=self.config.get("broker_aliases") or {},
        )
        self.worker.connected.connect(self._on_connected)
        self.worker.disconnected.connect(self._on_disconnected)
        self.worker.metricsUpdated.connect(self._on_metrics)
        self.worker.snapshotTaken.connect(self.diagnostics.update_snapshot)
        self.worker.start()
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._log("Captura iniciada")

    def stop_capture(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(3000)
            self.worker = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.health.update_state(GREY, "PARADO")
        self._log("Captura parada")

    def _interval_changed(self) -> None:
        ms = int(self.interval_combo.currentData())
        self.config["capture"]["interval_ms"] = ms
        if self.worker is not None:
            self.worker.set_interval_ms(ms)
        self._log(f"Intervalo de snapshot: {ms} ms")

    def _symbol_changed(self) -> None:
        symbol = self.symbol_edit.text().strip()
        if self.worker is not None:
            self.worker.set_symbol(symbol)
        if symbol:
            self.aggregator.set_symbol(symbol)

    def _on_connected(self, lines: list) -> None:
        for line in lines:
            self._log(line)
        self.health.update_state(GREEN, "CAPTURANDO")

    def _on_disconnected(self, message: str) -> None:
        self.health.update_state(RED, "DESCONECTADO")
        self._log(f"Desconectado: {message}")

    def _on_metrics(self, metrics: dict) -> None:
        self._last_metrics = metrics

    # ---------------------------------------------------------------- render
    def _refresh_view(self) -> None:
        snap = self.aggregator.snapshot()
        rows = filter_rows(snap.rows, self.filter_combo.currentText(), self.search_edit.text())
        top_n = int(self.config["gui"]["top_n"])

        self.buyers_table.set_rows(
            [
                [
                    Cell(r.broker, r.broker, align=Qt.AlignLeft | Qt.AlignVCenter),
                    Cell(format_int_ptbr(r.buy_volume), r.buy_volume),
                    Cell(
                        format_signed_ptbr(r.window_balance(self._short_window)),
                        r.window_balance(self._short_window),
                        balance_color(r.window_balance(self._short_window)),
                    ),
                ]
                for r in top_buyers(rows, top_n)
            ]
        )
        self.sellers_table.set_rows(
            [
                [
                    Cell(r.broker, r.broker, align=Qt.AlignLeft | Qt.AlignVCenter),
                    Cell(format_int_ptbr(r.sell_volume), r.sell_volume),
                    Cell(
                        format_signed_ptbr(r.window_balance(self._short_window)),
                        r.window_balance(self._short_window),
                        balance_color(r.window_balance(self._short_window)),
                    ),
                ]
                for r in top_sellers(rows, top_n)
            ]
        )

        balance_rows = []
        for r in balance_ranking(rows, top_n):
            cells = [
                Cell(r.broker, r.broker, align=Qt.AlignLeft | Qt.AlignVCenter),
                Cell(format_int_ptbr(r.buy_volume), r.buy_volume),
                Cell(format_int_ptbr(r.sell_volume), r.sell_volume),
                Cell(format_signed_ptbr(r.balance), r.balance, balance_color(r.balance)),
                Cell(format_int_ptbr(r.trade_count), r.trade_count),
                Cell(f"{r.avg_lot:.1f}".replace(".", ","), r.avg_lot),
                Cell(format_int_ptbr(r.max_lot), r.max_lot),
            ]
            for w in self._windows:
                value = r.window_balance(w)
                cells.append(Cell(format_signed_ptbr(value), value, balance_color(value)))
            speed = r.window_speed(self._short_window)
            cells.append(Cell(f"{speed:.1f}".replace(".", ","), speed))
            arrow = ""
            if r.acceleration.endswith("COMPRA"):
                arrow = "↑ ACELERANDO COMPRA"
            elif r.acceleration.endswith("VENDA"):
                arrow = "↓ ACELERANDO VENDA"
            cells.append(
                Cell(arrow, arrow, balance_color(1 if "COMPRA" in arrow else -1 if arrow else 0),
                     align=Qt.AlignLeft | Qt.AlignVCenter)
            )
            balance_rows.append(cells)
        self.balance_table.set_rows(balance_rows)

        self._update_header(snap)
        self._update_health(snap)

    def _update_header(self, snap) -> None:
        symbol = self.symbol_edit.text().strip() or snap.symbol or self._last_metrics.get("symbol", "")
        self.symbol_label.setText(symbol or "-")
        price = f"{snap.last_price:.2f}".replace(".", ",") if snap.last_price else "-"
        self.metrics_label.setText(
            f"Preço {price} | Negócios {format_int_ptbr(snap.total_trades)} | "
            f"Contratos {format_int_ptbr(snap.total_volume)} | "
            f"Compra {format_int_ptbr(snap.buy_volume)} | Venda {format_int_ptbr(snap.sell_volume)} | "
            f"RLP {format_int_ptbr(snap.rlp_volume)} | Saldo {format_signed_ptbr(snap.balance)} | "
            f"{snap.trades_per_second:.1f} neg/s | {snap.contracts_per_second:.0f} ctr/s"
        )

    def _update_health(self, snap) -> None:
        m = self._last_metrics
        now = time.time()
        connected = bool(m.get("connected"))
        running = self.worker is not None and self.worker.isRunning()

        self.health.excel.setText(
            f"Excel: {'conectado' if connected else 'desconectado'}"
            + (f" ({m.get('workbook','')}!{m.get('worksheet','')})" if connected else "")
        )
        last_trade = m.get("last_trade_ts", 0.0)
        gap = now - last_trade if last_trade else None
        self.health.rtd.setText(
            f"Último negócio: {gap:.2f} s" if gap is not None else "Último negócio: -"
        )
        self.health.snapshots.setText(
            f"Snapshots: {m.get('snapshots_total', 0)} ({m.get('snapshots_per_second', 0):.1f}/s)"
        )
        self.health.queue.setText(f"Fila: {self.trade_queue.qsize()}")
        detected = m.get("trades_detected", 0)
        persisted = self.db_writer.trades_persisted
        pending = detected - persisted
        text = f"Banco: {persisted}"
        if pending > 0:
            text += f" (pendentes {pending})"
        self.health.db.setText(text)
        self.health.errors.setText(
            f"Erros COM: {m.get('com_errors', 0)} | DB: {self.db_writer.db_errors}"
        )
        self.health.update_risk(
            m.get("utilization", 0.0),
            float(self.config["capture"]["risk_warn"]),
            float(self.config["capture"]["risk_critical"]),
        )

        if not running:
            self.health.update_state(GREY, "PARADO")
        elif not connected:
            self.health.update_state(RED, "DESCONECTADO")
        elif gap is None or gap > 5:
            self.health.update_state(YELLOW, "SEM NEGÓCIOS RECENTES")
        else:
            self.health.update_state(GREEN, "CAPTURANDO")

        self.diagnostics.update_benchmark(m)

    # ------------------------------------------------------------- ações
    def open_history(self) -> None:
        HistoryDialog(self.database, self).exec()

    def export_ranking_csv(self) -> None:
        snap = self.aggregator.snapshot()
        rows = ranking_export_rows(snap)
        if not rows:
            QMessageBox.information(self, "FlowRank", "Sem dados para exportar.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar ranking", "ranking.csv", "CSV (*.csv)")
        if path:
            export_csv(rows, path)
            self._log(f"Ranking exportado: {path}")

    def export_trades(self, fmt: str) -> None:
        session = self.aggregator.snapshot().session_date
        rows = [dict(r) for r in self.database.iter_all(session)]
        if not rows:
            QMessageBox.information(self, "FlowRank", "Sem negócios persistidos nesta sessão.")
            return
        if fmt == "parquet":
            path, _ = QFileDialog.getSaveFileName(
                self, "Exportar negócios", f"negocios_{session}.parquet", "Parquet (*.parquet)"
            )
            if path:
                export_parquet(rows, path)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Exportar negócios", f"negocios_{session}.csv", "CSV (*.csv)"
            )
            if path:
                export_csv(rows, path)
        if path:
            self._log(f"Negócios exportados: {path}")

    def _log(self, message: str) -> None:
        self.log_view.appendPlainText(message)
        log.info(message)

    # --------------------------------------------------------- encerramento
    def closeEvent(self, event) -> None:  # noqa: N802
        self.refresh_timer.stop()
        self.stop_capture()
        self.db_writer.stop()
        self.database.close()
        try:
            save_config(self.config)
        except Exception as exc:  # noqa: BLE001
            log.warning("Falha ao salvar configuração: %s", exc)
        log.info("FlowRank encerrado")
        super().closeEvent(event)


def _group(title: str, widget: QWidget) -> QGroupBox:
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.addWidget(widget)
    return box
