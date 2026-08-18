"""Reconciliação de snapshots preservando multiplicidade (multiset diff).

Regra central do FlowRank: um negócio que permanece visível em vários
snapshots NÃO pode ser contado duas vezes, mas negócios legítimos repetidos
(mesmo horário, preço, quantidade, corretora e lado) DEVEM ser contados
individualmente. Por isso a comparação usa Counter (multiset) e nunca
drop_duplicates() ou set().
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Hashable, Iterable, Sequence


@dataclass(slots=True)
class DiffResult:
    new_items: list
    snapshot_size: int
    disappeared: int
    is_baseline: bool

    @property
    def new_count(self) -> int:
        return len(self.new_items)

    @property
    def utilization(self) -> float:
        """Fração da janela visível ocupada por linhas novas."""
        if self.snapshot_size <= 0:
            return 0.0
        return min(self.new_count / self.snapshot_size, 1.0)


class MultisetDiff:
    """Compara snapshots consecutivos mantendo a contagem de cada linha."""

    def __init__(self, oldest_first: bool = False) -> None:
        # oldest_first=False => a linha mais recente está no topo (padrão do T&T)
        self.oldest_first = oldest_first
        self._previous: Counter = Counter()
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def reset(self) -> None:
        """Descarta o baseline; o próximo snapshot volta a ser baseline."""
        self._previous = Counter()
        self._initialized = False

    def update(self, rows: Sequence[Hashable]) -> DiffResult:
        current = Counter(rows)
        if not self._initialized:
            self._previous = current
            self._initialized = True
            return DiffResult([], len(rows), 0, True)

        delta = current - self._previous
        removed = self._previous - current
        self._previous = current

        new_items: list = []
        if delta:
            pending = Counter(delta)
            ordered = rows if self.oldest_first else tuple(reversed(rows))
            for row in ordered:  # emite em ordem cronológica (mais antigo primeiro)
                if pending.get(row, 0) > 0:
                    pending[row] -= 1
                    new_items.append(row)

        return DiffResult(
            new_items=new_items,
            snapshot_size=len(rows),
            disappeared=sum(removed.values()),
            is_baseline=False,
        )


def diff_multiset(previous: Iterable[Hashable], current: Iterable[Hashable]) -> list:
    """Diferença simples entre dois multisets, em ordem de aparição em `current`."""
    pending = Counter(current) - Counter(previous)
    result: list = []
    for row in current:
        if pending.get(row, 0) > 0:
            pending[row] -= 1
            result.append(row)
    return result
