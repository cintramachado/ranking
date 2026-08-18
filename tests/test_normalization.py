from app.utils.normalization import (
    SIDE_BUY,
    SIDE_RLP,
    SIDE_SELL,
    SIDE_UNKNOWN,
    header_to_field,
    normalize_broker,
    normalize_side,
    normalize_time,
    parse_number,
    parse_quantity,
)


def test_headers_com_variacoes():
    assert header_to_field("Data") == "trade_time"
    assert header_to_field("Hora") == "trade_time"
    assert header_to_field("Preço") == "price"
    assert header_to_field("Preco") == "price"
    assert header_to_field("Valor") == "price"
    assert header_to_field("Qtd") == "quantity"
    assert header_to_field("Agente_Agressor") == "broker"
    assert header_to_field("Agente Agressor") == "broker"
    assert header_to_field("Agressor") == "aggressor_side"
    assert header_to_field("qualquer coisa") is None


def test_lados():
    for value in ("C", "Comprador", "compra", "BUY"):
        assert normalize_side(value) == SIDE_BUY
    for value in ("V", "Vendedor", "venda", "SELL"):
        assert normalize_side(value) == SIDE_SELL


def test_rlp_nao_vira_compra_nem_venda():
    assert normalize_side("RLP") == SIDE_RLP
    assert normalize_side("") == SIDE_UNKNOWN
    assert normalize_side(None) == SIDE_UNKNOWN


def test_rlp_com_direcao_explicita():
    assert normalize_side("RLP Comprador") == SIDE_BUY
    assert normalize_side("RLP Vendedor") == SIDE_SELL


def test_broker_apenas_remove_espacos():
    assert normalize_broker("  UBS  ") == "UBS"
    assert normalize_broker("Santander  Institucional") == "Santander Institucional"
    assert normalize_broker("Santander Institucional", {"Santander Institucional": "Santander"}) == "Santander"


def test_numeros_ptbr_e_en():
    assert parse_number("5124,5") == 5124.5
    assert parse_number("5.124,50") == 5124.5
    assert parse_number("5124.5") == 5124.5
    assert parse_quantity("1.250") == 1250
    assert parse_number("") is None


def test_tempo_como_texto_permanece_estavel():
    assert normalize_time("09:07:13.368") == "09:07:13.368"
    assert normalize_time(" 09:07:13.368 ") == "09:07:13.368"
