"""Detector e leitor de snapshot validados com um Excel simulado (sem COM)."""

from app.domain.trade import PairKey, TradeKey, expand_key
from app.excel.detector import MODE_COUNTERPARTY, column_letter, detect_table
from app.excel.snapshot import SnapshotReader
from app.utils.normalization import SIDE_BUY, SIDE_SELL

HEADER_ROW = 14
FIRST_COL = 8  # coluna H

GRID = [
    ["DOLPRO", "Negócios", None, None, None],
    ["Data", "Valor", "Quantidade", "Agente Agressor", "Agressor"],
    ["09:27:36.791", 5125, 10, "XP", "RLP"],
    ["09:27:33.870", 5125.5, 12, "BTG", "Vendedor"],
    ["09:27:31.362", 5125, 25, "Santander Institucional", "Comprador"],
    ["09:27:31.362", 5125, 25, "Santander Institucional", "Comprador"],
]


class FakeRange:
    def __init__(self, value, row=1, column=1):
        self.Value = value
        self.Row = row
        self.Column = column


class FakeWorksheet:
    def __init__(self, name="Planilha1", grid=None, first_row=13, first_col=FIRST_COL):
        self.Name = name
        self.grid = grid if grid is not None else GRID
        self.first_row = first_row
        self.first_col = first_col

    @property
    def UsedRange(self):
        return FakeRange(
            tuple(tuple(row) for row in self.grid), row=self.first_row, column=self.first_col
        )

    def Cells(self, row, col):
        return (row, col)

    def Range(self, start, end):
        r1, c1 = start
        r2, c2 = end
        rows = []
        for r in range(r1, r2 + 1):
            grid_row = r - self.first_row
            if 0 <= grid_row < len(self.grid):
                source = self.grid[grid_row]
            else:
                source = []
            rows.append(
                tuple(
                    source[c - self.first_col] if 0 <= c - self.first_col < len(source) else None
                    for c in range(c1, c2 + 1)
                )
            )
        return FakeRange(tuple(rows))


class FakeCollection:
    def __init__(self, items):
        self._items = items
        self.Count = len(items)

    def __call__(self, key):
        if isinstance(key, int):
            return self._items[key - 1]
        for item in self._items:
            if item.Name == key:
                return item
        raise KeyError(key)


class FakeWorkbook:
    def __init__(self, name="times.xlsx", sheets=None):
        self.Name = name
        self.Worksheets = FakeCollection(sheets or [FakeWorksheet()])


class FakeApp:
    def __init__(self, workbooks=None):
        self.Workbooks = FakeCollection(workbooks or [FakeWorkbook()])


def test_column_letter():
    assert column_letter(8) == "H"
    assert column_letter(12) == "L"
    assert column_letter(27) == "AA"


def test_detecta_tabela_e_colunas():
    location = detect_table(FakeApp())
    assert location is not None
    assert location.header_row == HEADER_ROW
    assert location.workbook_name == "times.xlsx"
    assert location.worksheet_name == "Planilha1"
    assert column_letter(location.columns["trade_time"]) == "H"
    assert column_letter(location.columns["price"]) == "I"
    assert column_letter(location.columns["quantity"]) == "J"
    assert column_letter(location.columns["broker"]) == "K"
    assert column_letter(location.columns["aggressor_side"]) == "L"
    assert location.symbol == "DOLPRO"


def test_leitura_de_snapshot():
    ws = FakeWorksheet()
    location = detect_table(FakeApp([FakeWorkbook(sheets=[ws])]))
    reader = SnapshotReader(location, max_rows=1000)
    snapshot = reader.read(ws)

    assert snapshot.size == 4
    assert snapshot.last_price == 5125
    first = snapshot.keys[0]
    assert first.trade_time == "09:27:36.791"
    assert first.quantity == 10
    assert first.broker == "XP"
    assert first.aggressor_side == "RLP"
    # negócios idênticos consecutivos permanecem duplicados na lista
    assert snapshot.keys[2] == snapshot.keys[3]


COUNTERPARTY_GRID = [
    ["DOLPRO", "Negócios", None, None, None],
    ["Data", "Compradora", "Valor", "Quantidade", "Vendedora"],
    ["10:03:18.884", "Santander", 5118.5, 44, "UBS"],
    ["10:03:18.884", "Santander", 5118.5, 44, "UBS"],
    ["10:03:18.882", "UBS", 5118.5, 50, "BTG"],
]


def test_detecta_layout_contraparte():
    ws = FakeWorksheet(grid=COUNTERPARTY_GRID)
    location = detect_table(FakeApp([FakeWorkbook(sheets=[ws])]))
    assert location.mode == MODE_COUNTERPARTY
    assert column_letter(location.columns["buyer_broker"]) == "I"
    assert column_letter(location.columns["seller_broker"]) == "L"

    snapshot = SnapshotReader(location).read(ws)
    assert snapshot.size == 3
    assert isinstance(snapshot.keys[0], PairKey)
    assert snapshot.keys[0] == snapshot.keys[1]  # linhas idênticas continuam duplicadas


def test_expansao_de_linha_contraparte_gera_compra_e_venda():
    key = PairKey("10:03:18.884", 5118.5, 44, "Santander", "UBS")
    trades = expand_key(key, capture_timestamp=1.0, symbol="DOLPRO")
    assert len(trades) == 2
    assert (trades[0].broker, trades[0].aggressor_side) == ("Santander", SIDE_BUY)
    assert (trades[1].broker, trades[1].aggressor_side) == ("UBS", SIDE_SELL)
    assert all(t.quantity == 44 for t in trades)


def test_expansao_layout_agressor_gera_um_trade():
    key = TradeKey("09:27:31.362", 5125.0, 25, "BTG", SIDE_SELL)
    trades = expand_key(key, capture_timestamp=1.0)
    assert len(trades) == 1
    assert trades[0].broker == "BTG"


def test_snapshot_ignora_linhas_invalidas():
    grid = [row[:] for row in GRID] + [["", None, None, None, None]]
    grid[2] = ["09:27:36.791", 5125, None, "XP", "RLP"]
    ws = FakeWorksheet(grid=grid)
    location = detect_table(FakeApp([FakeWorkbook(sheets=[ws])]))
    snapshot = SnapshotReader(location).read(ws)
    assert snapshot.size == 3
    assert snapshot.invalid_rows == 1
