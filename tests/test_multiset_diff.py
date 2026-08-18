"""Testes do componente mais crítico: reconciliação de snapshots."""

from app.capture.multiset_diff import MultisetDiff, diff_multiset

T = ("09:00:00.100", 5124, 10, "UBS", "VENDA")


def test_baseline_nao_conta_nada():
    diff = MultisetDiff()
    result = diff.update([T, T, T])
    assert result.is_baseline
    assert result.new_count == 0


def test_repeticao_identica_e_negocio_novo():
    diff = MultisetDiff()
    diff.update([T, T])
    result = diff.update([T, T, T])
    assert result.new_count == 1
    assert result.new_items == [T]


def test_snapshot_identico_nao_gera_novos():
    diff = MultisetDiff()
    diff.update([T, T, T])
    for _ in range(10):
        assert diff.update([T, T, T]).new_count == 0


def test_multiplicidade_por_chave():
    a, b, c = "A", "B", "C"
    diff = MultisetDiff()
    diff.update([a, a, b])
    result = diff.update([a, b, b, c])
    assert sorted(result.new_items) == ["B", "C"]


def test_ordem_das_linhas_nao_importa():
    a, b, c = "A", "B", "C"
    diff = MultisetDiff()
    diff.update([b, a, a])
    result = diff.update([c, b, b, a])
    assert sorted(result.new_items) == ["B", "C"]


def test_novos_emitidos_em_ordem_cronologica():
    # topo = mais recente; a saída deve vir do mais antigo para o mais novo
    diff = MultisetDiff()
    diff.update(["t3", "t2", "t1"])
    result = diff.update(["t5", "t4", "t3", "t2", "t1"])
    assert result.new_items == ["t4", "t5"]


def test_linhas_que_sumiram_nao_viram_negocios():
    diff = MultisetDiff()
    diff.update(["t3", "t2", "t1"])
    result = diff.update(["t5", "t4", "t3"])  # janela rolou, t1 e t2 sumiram
    assert result.new_items == ["t4", "t5"]
    assert result.disappeared == 2


def test_reconexao_reinicia_baseline():
    diff = MultisetDiff()
    diff.update([T, T])
    diff.reset()
    assert diff.update([T, T, T, T]).new_count == 0
    assert diff.update([T, T, T, T]).new_count == 0


def test_utilizacao_da_janela():
    diff = MultisetDiff()
    diff.update(["a", "b", "c", "d"])
    result = diff.update(["e", "f", "a", "b"])
    assert result.new_count == 2
    assert result.utilization == 0.5


def test_diff_multiset_funcao_pura():
    assert diff_multiset(["A", "A", "B"], ["A", "B", "B", "C"]) == ["B", "C"]


def test_timestamps_iguais_nunca_sao_deduplicados():
    rows_1 = [T] * 5
    rows_2 = [T] * 9
    diff = MultisetDiff()
    diff.update(rows_1)
    assert diff.update(rows_2).new_count == 4
