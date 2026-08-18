from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class BrokerStats:
    """Acumulado do pregão para uma corretora."""

    broker: str
    buy_volume: int = 0
    sell_volume: int = 0
    rlp_volume: int = 0
    buy_count: int = 0
    sell_count: int = 0
    rlp_count: int = 0
    max_lot: int = 0
    total_volume: int = 0

    @property
    def balance(self) -> int:
        return self.buy_volume - self.sell_volume

    @property
    def trade_count(self) -> int:
        return self.buy_count + self.sell_count + self.rlp_count

    @property
    def avg_lot(self) -> float:
        return self.total_volume / self.trade_count if self.trade_count else 0.0


@dataclass(slots=True)
class WindowStats:
    """Fluxo de uma corretora dentro de uma janela móvel."""

    buy_volume: int = 0
    sell_volume: int = 0
    buy_count: int = 0
    sell_count: int = 0
    rlp_volume: int = 0

    @property
    def balance(self) -> int:
        return self.buy_volume - self.sell_volume

    @property
    def volume(self) -> int:
        return self.buy_volume + self.sell_volume

    @property
    def trades(self) -> int:
        return self.buy_count + self.sell_count


@dataclass(slots=True)
class BrokerRow:
    """Linha pronta para exibição no ranking."""

    broker: str
    buy_volume: int
    sell_volume: int
    balance: int
    trade_count: int
    avg_lot: float
    max_lot: int
    rlp_volume: int
    windows: dict[int, WindowStats] = field(default_factory=dict)
    acceleration: str = ""

    def window_balance(self, seconds: int) -> int:
        stats = self.windows.get(seconds)
        return stats.balance if stats else 0

    def window_speed(self, seconds: int) -> float:
        stats = self.windows.get(seconds)
        if not stats or seconds <= 0:
            return 0.0
        return stats.volume / seconds
