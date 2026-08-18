import queue
import time

from app.domain.trade import Trade
from app.persistence.database import Database
from app.persistence.export import export_csv
from app.persistence.writer import DBWriter
from app.utils.normalization import SIDE_BUY, SIDE_SELL


def make(i, broker="UBS", side=SIDE_BUY):
    return Trade(
        capture_timestamp=time.time(),
        trade_time=f"09:00:{i % 60:02d}.000",
        price=5124.0,
        quantity=10,
        broker=broker,
        aggressor_side=side,
        symbol="DOLPRO",
        session_date="2026-08-18",
    )


def test_insercao_e_consulta(tmp_path):
    db = Database(tmp_path / "flowrank.db")
    db.insert_trades([make(i) for i in range(10)] + [make(1, "XP", SIDE_SELL)])
    assert db.count("2026-08-18") == 11
    assert db.sessions() == ["2026-08-18"]
    assert set(db.brokers()) == {"UBS", "XP"}
    assert len(db.query_trades(broker="XP")) == 1
    assert len(db.query_trades(side=SIDE_BUY)) == 10
    assert len(db.query_trades(min_quantity=20)) == 0
    db.close()


def test_negocios_identicos_sao_persistidos_individualmente(tmp_path):
    db = Database(tmp_path / "flowrank.db")
    db.insert_trades([make(1), make(1), make(1)])
    assert db.count() == 3
    db.close()


def test_writer_drena_fila_no_encerramento(tmp_path):
    db = Database(tmp_path / "flowrank.db")
    q: "queue.Queue[Trade]" = queue.Queue()
    writer = DBWriter(db, q, flush_interval_ms=50, batch_size=100)
    writer.start()
    for i in range(250):
        q.put(make(i))
    writer.stop(drain_timeout=10)
    assert writer.trades_persisted == 250
    assert db.count() == 250
    db.close()


def test_export_csv_ptbr(tmp_path):
    path = tmp_path / "ranking.csv"
    export_csv([{"corretora": "XP", "saldo": -9100, "lote_medio": 12.5}], path)
    content = path.read_text(encoding="utf-8-sig")
    assert "corretora;saldo;lote_medio" in content
    assert "XP;-9100;12,50" in content
