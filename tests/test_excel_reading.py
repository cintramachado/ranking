"""Detector e leitor de snapshot validados com um Excel simulado (sem COM)."""

from app.excel.detector import column_letter, detect_table
from app.excel.snapshot import SnapshotReader

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


def test_snapshot_ignora_linhas_invalidas():
    grid = [row[:] for row in GRID] + [["", None, None, None, None]]
    grid[2] = ["09:27:36.791", 5125, None, "XP", "RLP"]
    ws = FakeWorksheet(grid=grid)
    location = detect_table(FakeApp([FakeWorkbook(sheets=[ws])]))
    snapshot = SnapshotReader(location).read(ws)
    assert snapshot.size == 3
    assert snapshot.invalid_rows == 1
