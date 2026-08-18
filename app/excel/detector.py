"""Detecção automática da tabela de Times & Trades em qualquer planilha aberta."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.utils.logger import get_logger
from app.utils.normalization import (
    FIELD_BROKER,
    FIELD_BUYER,
    FIELD_PRICE,
    FIELD_QUANTITY,
    FIELD_SELLER,
    FIELD_SIDE,
    FIELD_TIME,
    REQUIRED_FIELDS,
    header_to_field,
)

log = get_logger("excel.detector")

MODE_AGGRESSOR = "aggressor"
MODE_COUNTERPARTY = "counterparty"

# Layout A: Data | Valor | Quantidade | Agente Agressor | Agressor
MANDATORY_AGGRESSOR = (FIELD_TIME, FIELD_QUANTITY, FIELD_BROKER, FIELD_SIDE)
# Layout B: Data | Compradora | Valor | Quantidade | Vendedora
MANDATORY_COUNTERPARTY = (FIELD_TIME, FIELD_QUANTITY, FIELD_BUYER, FIELD_SELLER)
MAX_HEADER_SCAN_ROWS = 200


def column_letter(index: int) -> str:
    letters = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


@dataclass(slots=True)
class TableLocation:
    workbook_name: str
    worksheet_name: str
    header_row: int
    columns: dict[str, int]
    mode: str = MODE_AGGRESSOR
    symbol: str = ""
    header_labels: dict[str, str] = field(default_factory=dict)

    @property
    def first_column(self) -> int:
        return min(self.columns.values())

    @property
    def last_column(self) -> int:
        return max(self.columns.values())

    def describe(self) -> list[str]:
        lines = [
            "Excel conectado",
            f"Workbook: {self.workbook_name}",
            f"Planilha: {self.worksheet_name}",
            f"Cabeçalho encontrado: linha {self.header_row}",
            "Layout: "
            + (
                "agressor (Agente Agressor + Agressor)"
                if self.mode == MODE_AGGRESSOR
                else "contraparte (Compradora + Vendedora)"
            ),
        ]
        for f in REQUIRED_FIELDS:
            if f in self.columns:
                label = self.header_labels.get(f, f)
                lines.append(f"{label}: {column_letter(self.columns[f])}")
        if self.symbol:
            lines.append(f"Ativo detectado: {self.symbol}")
        return lines


def _match_header_row(values: list[Any]) -> tuple[dict[str, int], dict[str, str], str] | None:
    """Retorna (campo -> índice de coluna relativo 1-based, campo -> rótulo, modo)."""
    columns: dict[str, int] = {}
    labels: dict[str, str] = {}
    for idx, cell in enumerate(values, start=1):
        field_name = header_to_field(cell)
        if field_name and field_name not in columns:
            columns[field_name] = idx
            labels[field_name] = str(cell).strip()
    if all(f in columns for f in MANDATORY_AGGRESSOR):
        return columns, labels, MODE_AGGRESSOR
    if all(f in columns for f in MANDATORY_COUNTERPARTY):
        return columns, labels, MODE_COUNTERPARTY
    return None


def detect_table(
    app: Any,
    workbook_pref: str | None = None,
    worksheet_pref: str | None = None,
) -> TableLocation | None:
    """Varre todos os workbooks/planilhas abertos procurando o cabeçalho do T&T."""
    for wb_index in range(1, int(app.Workbooks.Count) + 1):
        wb = app.Workbooks(wb_index)
        wb_name = str(wb.Name)
        if workbook_pref and workbook_pref not in ("auto", "", None):
            if workbook_pref.lower() not in wb_name.lower():
                continue
        for ws_index in range(1, int(wb.Worksheets.Count) + 1):
            ws = wb.Worksheets(ws_index)
            ws_name = str(ws.Name)
            if worksheet_pref and worksheet_pref not in ("auto", "", None):
                if worksheet_pref.lower() != ws_name.lower():
                    continue
            location = _scan_worksheet(ws, wb_name, ws_name)
            if location:
                return location
    return None


def _scan_worksheet(ws: Any, wb_name: str, ws_name: str) -> TableLocation | None:
    try:
        used = ws.UsedRange
        first_row = int(used.Row)
        first_col = int(used.Column)
        data = used.Value
    except Exception as exc:  # noqa: BLE001
        log.debug("Falha lendo UsedRange de %s!%s: %s", wb_name, ws_name, exc)
        return None

    if data is None:
        return None
    if not isinstance(data, tuple):
        return None
    rows = data if isinstance(data[0], tuple) else (data,)

    for offset, row_values in enumerate(rows[:MAX_HEADER_SCAN_ROWS]):
        match = _match_header_row(list(row_values))
        if not match:
            continue
        rel_columns, labels, mode = match
        header_row = first_row + offset
        columns = {f: first_col + rel - 1 for f, rel in rel_columns.items()}
        symbol = _detect_symbol(rows, offset, rel_columns)
        location = TableLocation(
            workbook_name=wb_name,
            worksheet_name=ws_name,
            header_row=header_row,
            columns=columns,
            mode=mode,
            symbol=symbol,
            header_labels=labels,
        )
        for line in location.describe():
            log.info(line)
        return location
    return None


def _detect_symbol(rows: tuple, header_offset: int, rel_columns: dict[str, int]) -> str:
    """Procura o ativo na célula imediatamente acima da primeira coluna do cabeçalho."""
    if header_offset == 0:
        return ""
    above = rows[header_offset - 1]
    first_rel = min(rel_columns.values())
    candidates = [above[i] for i in range(first_rel - 1, len(above)) if above[i]]
    if not candidates:
        return ""
    text = str(candidates[0]).strip()
    if header_to_field(text) or len(text) > 20:
        return ""
    return text


def price_column(location: TableLocation) -> int | None:
    return location.columns.get(FIELD_PRICE)
