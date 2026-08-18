"""Construção dos rankings a partir do snapshot agregado."""

from __future__ import annotations

from typing import Sequence

from app.analytics.aggregator import AggregateSnapshot
from app.domain.broker_stats import BrokerRow

FILTER_ALL = "Todos"
FILTER_BUY = "COMPRA"
FILTER_SELL = "VENDA"
FILTER_RLP = "RLP"


def filter_rows(
    rows: Sequence[BrokerRow], side_filter: str = FILTER_ALL, search: str = ""
) -> list[BrokerRow]:
    term = search.strip().lower()
    result = []
    for row in rows:
        if term and term not in row.broker.lower():
            continue
        if side_filter == FILTER_BUY and row.buy_volume <= 0:
            continue
        if side_filter == FILTER_SELL and row.sell_volume <= 0:
            continue
        if side_filter == FILTER_RLP and row.rlp_volume <= 0:
            continue
        result.append(row)
    return result


def top_buyers(rows: Sequence[BrokerRow], top_n: int = 15) -> list[BrokerRow]:
    ranked = [r for r in rows if r.buy_volume > 0]
    ranked.sort(key=lambda r: r.buy_volume, reverse=True)
    return ranked[:top_n]


def top_sellers(rows: Sequence[BrokerRow], top_n: int = 15) -> list[BrokerRow]:
    ranked = [r for r in rows if r.sell_volume > 0]
    ranked.sort(key=lambda r: r.sell_volume, reverse=True)
    return ranked[:top_n]


def balance_ranking(rows: Sequence[BrokerRow], top_n: int = 15) -> list[BrokerRow]:
    ranked = list(rows)
    ranked.sort(key=lambda r: r.balance, reverse=True)
    if len(ranked) <= top_n:
        return ranked
    half = max(1, top_n // 2)
    return ranked[:half] + ranked[-(top_n - half):]


def ranking_export_rows(snapshot: AggregateSnapshot) -> list[dict]:
    export = []
    for row in sorted(snapshot.rows, key=lambda r: r.balance, reverse=True):
        item = {
            "corretora": row.broker,
            "compra": row.buy_volume,
            "venda": row.sell_volume,
            "saldo": row.balance,
            "negocios": row.trade_count,
            "lote_medio": round(row.avg_lot, 2),
            "maior_lote": row.max_lot,
            "rlp": row.rlp_volume,
        }
        for window in snapshot.windows:
            item[f"saldo_{window}s"] = row.window_balance(window)
        item["aceleracao"] = row.acceleration
        export.append(item)
    return export
