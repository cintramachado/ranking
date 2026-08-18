import time

from app.analytics.aggregator import Aggregator
from app.analytics.ranking import balance_ranking, top_buyers, top_sellers
from app.domain.trade import Trade
from app.utils.normalization import SIDE_BUY, SIDE_RLP, SIDE_SELL


def make(broker, side, qty, ts):
    return Trade(
        capture_timestamp=ts,
        trade_time="09:00:00.000",
        price=5124.0,
        quantity=qty,
        broker=broker,
        aggressor_side=side,
        symbol="DOLPRO",
        session_date="2026-08-18",
    )


def test_saldo_por_corretora():
    now = time.time()
    agg = Aggregator(windows=(5, 30))
    agg.add_trades(
        [
            make("Santander", SIDE_BUY, 22500, now),
            make("Santander", SIDE_SELL, 7000, now),
            make("XP", SIDE_SELL, 1000, now),
        ]
    )
    rows = {r.broker: r for r in agg.snapshot(now).rows}
    assert rows["Santander"].balance == 15500
    assert rows["XP"].balance == -1000


def test_rlp_nao_entra_no_saldo():
    now = time.time()
    agg = Aggregator(windows=(5,))
    agg.add_trades([make("BTG", SIDE_RLP, 500, now), make("BTG", SIDE_BUY, 100, now)])
    row = agg.snapshot(now).rows[0]
    assert row.balance == 100
    assert row.rlp_volume == 500
    assert row.trade_count == 2


def test_janela_movel_ignora_eventos_antigos():
    now = time.time()
    agg = Aggregator(windows=(5, 30))
    agg.add_trades([make("XP", SIDE_BUY, 1000, now - 60)])
    agg.add_trades([make("XP", SIDE_BUY, 300, now - 1)])
    row = agg.snapshot(now).rows[0]
    assert row.window_balance(5) == 300
    assert row.window_balance(30) == 300
    assert row.buy_volume == 1300


def test_lote_medio_e_maior_lote():
    now = time.time()
    agg = Aggregator(windows=(5,))
    agg.add_trades([make("UBS", SIDE_BUY, 10, now), make("UBS", SIDE_SELL, 30, now)])
    row = agg.snapshot(now).rows[0]
    assert row.max_lot == 30
    assert row.avg_lot == 20


def test_nova_sessao_zera_ranking():
    now = time.time()
    agg = Aggregator(windows=(5,))
    agg.add_trades([make("XP", SIDE_BUY, 100, now)])
    trade = make("XP", SIDE_BUY, 50, now)
    trade.session_date = "2026-08-19"
    agg.add_trades([trade])
    snap = agg.snapshot(now)
    assert snap.session_date == "2026-08-19"
    assert snap.rows[0].buy_volume == 50


def test_rankings():
    now = time.time()
    agg = Aggregator(windows=(5,))
    agg.add_trades(
        [
            make("A", SIDE_BUY, 100, now),
            make("B", SIDE_BUY, 300, now),
            make("B", SIDE_SELL, 50, now),
            make("C", SIDE_SELL, 500, now),
        ]
    )
    rows = agg.snapshot(now).rows
    assert [r.broker for r in top_buyers(rows, 2)] == ["B", "A"]
    assert [r.broker for r in top_sellers(rows, 2)] == ["C", "B"]
    assert balance_ranking(rows, 3)[0].broker == "B"


def test_aceleracao_de_compra():
    now = time.time()
    agg = Aggregator(windows=(10,), accel_window=10)
    agg.add_trades([make("XP", SIDE_BUY, 100, now - 15)])
    agg.add_trades([make("XP", SIDE_BUY, 5000, now - 2)])
    row = agg.snapshot(now).rows[0]
    assert row.acceleration == "ACELERANDO COMPRA"
