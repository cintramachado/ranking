"""Normalização de cabeçalhos, lados de agressão, corretoras e valores."""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from typing import Any

SIDE_BUY = "COMPRA"
SIDE_SELL = "VENDA"
SIDE_RLP = "RLP"
SIDE_UNKNOWN = "INDEFINIDO"

FIELD_TIME = "trade_time"
FIELD_PRICE = "price"
FIELD_QUANTITY = "quantity"
FIELD_BROKER = "broker"
FIELD_SIDE = "aggressor_side"
FIELD_BUYER = "buyer_broker"
FIELD_SELLER = "seller_broker"

REQUIRED_FIELDS = (
    FIELD_TIME,
    FIELD_PRICE,
    FIELD_QUANTITY,
    FIELD_BROKER,
    FIELD_SIDE,
    FIELD_BUYER,
    FIELD_SELLER,
)

# Cabeçalhos aceitos (já normalizados: sem acento, minúsculo, sem separadores)
HEADER_ALIASES: dict[str, str] = {
    "data": FIELD_TIME,
    "hora": FIELD_TIME,
    "horario": FIELD_TIME,
    "datahora": FIELD_TIME,
    "time": FIELD_TIME,
    "valor": FIELD_PRICE,
    "preco": FIELD_PRICE,
    "price": FIELD_PRICE,
    "ultimo": FIELD_PRICE,
    "quantidade": FIELD_QUANTITY,
    "qtd": FIELD_QUANTITY,
    "qtde": FIELD_QUANTITY,
    "quant": FIELD_QUANTITY,
    "volume": FIELD_QUANTITY,
    "quantity": FIELD_QUANTITY,
    "agenteagressor": FIELD_BROKER,
    "agente": FIELD_BROKER,
    "corretora": FIELD_BROKER,
    "broker": FIELD_BROKER,
    "agressor": FIELD_SIDE,
    "lado": FIELD_SIDE,
    "side": FIELD_SIDE,
    "direcao": FIELD_SIDE,
    # layout "contraparte": uma coluna para a corretora compradora e outra para a vendedora
    "compradora": FIELD_BUYER,
    "agentecomprador": FIELD_BUYER,
    "agentecompradora": FIELD_BUYER,
    "corretoracompradora": FIELD_BUYER,
    "buyer": FIELD_BUYER,
    "vendedora": FIELD_SELLER,
    "agentevendedor": FIELD_SELLER,
    "agentevendedora": FIELD_SELLER,
    "corretoravendedora": FIELD_SELLER,
    "seller": FIELD_SELLER,
}

_BUY_TOKENS = {"c", "comprador", "compra", "compradora", "buy", "b", "bid"}
_SELL_TOKENS = {"v", "vendedor", "venda", "vendedora", "sell", "s", "ask", "offer"}
_RLP_TOKENS = {"rlp", "rlpr", "retaillliquidityprovider", "retailliquidityprovider"}

_DIGITS = re.compile(r"[^0-9,.\-]")


def strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def normalize_header(value: Any) -> str:
    """Normaliza um cabeçalho para comparação (sem acento, sem separadores)."""
    if value is None:
        return ""
    text = strip_accents(str(value)).strip().lower()
    return re.sub(r"[\s_\-./]+", "", text)


def header_to_field(value: Any) -> str | None:
    return HEADER_ALIASES.get(normalize_header(value))


def normalize_side(value: Any) -> str:
    """Converte a coluna Agressor em COMPRA / VENDA / RLP / INDEFINIDO.

    Nunca inventa lado: RLP sem direção explícita permanece RLP.
    """
    if value is None:
        return SIDE_UNKNOWN
    raw = strip_accents(str(value)).strip().lower()
    if not raw:
        return SIDE_UNKNOWN
    token = re.sub(r"[\s_\-./]+", "", raw)
    if token in _BUY_TOKENS:
        return SIDE_BUY
    if token in _SELL_TOKENS:
        return SIDE_SELL
    if token in _RLP_TOKENS:
        return SIDE_RLP
    # formas compostas: "rlp comprador", "agressor: venda"
    words = re.split(r"[\s_\-./:]+", raw)
    wordset = set(words)
    has_rlp = bool(wordset & _RLP_TOKENS)
    if wordset & _BUY_TOKENS:
        return SIDE_BUY
    if wordset & _SELL_TOKENS:
        return SIDE_SELL
    if has_rlp:
        return SIDE_RLP
    return SIDE_UNKNOWN


def normalize_broker(value: Any, aliases: dict[str, str] | None = None) -> str:
    if value is None:
        return ""
    name = re.sub(r"\s+", " ", str(value)).strip()
    if aliases:
        return aliases.get(name, name)
    return name


def normalize_time(value: Any) -> str:
    """Converte o campo de tempo para string estável (usada na chave do multiset)."""
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.strftime("%H:%M:%S.%f")[:-3]
    if isinstance(value, dt.time):
        return value.strftime("%H:%M:%S.%f")[:-3]
    if isinstance(value, float):
        # serial de tempo do Excel (fração do dia)
        seconds = round((value % 1) * 86400, 3)
        base = dt.datetime(1900, 1, 1) + dt.timedelta(seconds=seconds)
        return base.strftime("%H:%M:%S.%f")[:-3]
    return str(value).strip()


def parse_number(value: Any) -> float | None:
    """Aceita 5124,5 / 5.124,50 / 5124.5 / 5124."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = _DIGITS.sub("", str(value).strip())
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


_THOUSANDS = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def parse_quantity(value: Any) -> int | None:
    if isinstance(value, str):
        text = value.strip()
        if _THOUSANDS.match(text):  # "1.250" é milhar, não decimal
            return int(text.replace(".", ""))
    number = parse_number(value)
    if number is None:
        return None
    return int(round(number))


def format_int_ptbr(value: float | int) -> str:
    return f"{int(round(value)):,}".replace(",", ".")


def format_signed_ptbr(value: float | int) -> str:
    number = int(round(value))
    text = format_int_ptbr(abs(number))
    if number > 0:
        return f"+{text}"
    if number < 0:
        return f"-{text}"
    return "0"
