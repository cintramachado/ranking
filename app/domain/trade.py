from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import NamedTuple

from app.utils.normalization import SIDE_BUY, SIDE_SELL


class TradeKey(NamedTuple):
    """Chave usada na comparação multiset entre snapshots (layout com agressor).

    Timestamps repetidos NÃO são duplicatas: a multiplicidade é preservada
    pelo Counter, esta chave apenas identifica linhas idênticas.
    """

    trade_time: str
    price: float
    quantity: int
    broker: str
    aggressor_side: str


class PairKey(NamedTuple):
    """Linha do layout com corretora compradora e vendedora na mesma linha."""

    trade_time: str
    price: float
    quantity: int
    buyer: str
    seller: str


@dataclass(slots=True)
class Trade:
    capture_timestamp: float
    trade_time: str
    price: float
    quantity: int
    broker: str
    aggressor_side: str
    symbol: str = ""
    session_date: str = field(default_factory=lambda: dt.date.today().isoformat())

    @property
    def capture_datetime(self) -> dt.datetime:
        return dt.datetime.fromtimestamp(self.capture_timestamp)

    @property
    def is_buy(self) -> bool:
        return self.aggressor_side == SIDE_BUY

    @property
    def is_sell(self) -> bool:
        return self.aggressor_side == SIDE_SELL

    @property
    def key(self) -> TradeKey:
        return TradeKey(
            self.trade_time,
            self.price,
            self.quantity,
            self.broker,
            self.aggressor_side,
        )

    @classmethod
    def from_key(
        cls,
        key: TradeKey,
        capture_timestamp: float,
        symbol: str = "",
        session_date: str | None = None,
    ) -> "Trade":
        return cls(
            capture_timestamp=capture_timestamp,
            trade_time=key.trade_time,
            price=key.price,
            quantity=key.quantity,
            broker=key.broker,
            aggressor_side=key.aggressor_side,
            symbol=symbol,
            session_date=session_date or dt.date.today().isoformat(),
        )


def expand_key(
    key: TradeKey | PairKey,
    capture_timestamp: float,
    symbol: str = "",
    session_date: str | None = None,
) -> list[Trade]:
    """Converte uma linha da planilha em um ou dois trades.

    Layout com agressor: 1 trade. Layout de contraparte: 1 compra + 1 venda.
    """
    session_date = session_date or dt.date.today().isoformat()
    if isinstance(key, PairKey):
        trades = []
        if key.buyer:
            trades.append(
                Trade(
                    capture_timestamp=capture_timestamp,
                    trade_time=key.trade_time,
                    price=key.price,
                    quantity=key.quantity,
                    broker=key.buyer,
                    aggressor_side=SIDE_BUY,
                    symbol=symbol,
                    session_date=session_date,
                )
            )
        if key.seller:
            trades.append(
                Trade(
                    capture_timestamp=capture_timestamp,
                    trade_time=key.trade_time,
                    price=key.price,
                    quantity=key.quantity,
                    broker=key.seller,
                    aggressor_side=SIDE_SELL,
                    symbol=symbol,
                    session_date=session_date,
                )
            )
        return trades
    return [Trade.from_key(key, capture_timestamp, symbol, session_date)]
