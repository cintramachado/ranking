# FlowRank

Captura contínua do Times & Trades do Profit/Nelogica **já exportado para o Excel via RTD**,
com ranking em tempo real das corretoras compradoras e vendedoras, saldo por corretora,
janelas móveis e persistência em SQLite.

O acesso aos dados é feito **exclusivamente por COM (`pywin32`)** sobre a instância do Excel
já aberta. Não usa ProfitDLL, OCR, captura de tela, automação de mouse nem leitura de arquivo salvo.

```
Profit/Nelogica → RTD → Excel aberto → COM/pywin32 → FlowRank
                                                      ├── captura (thread própria)
                                                      ├── multiset diff
                                                      ├── agregação em memória
                                                      ├── SQLite (fila + batch)
                                                      └── GUI PySide6
```

## Árvore do projeto

```
ranking/
├── main.py                     # ponto de entrada da GUI
├── config.yaml                 # configuração
├── requirements.txt
├── pytest.ini
├── times.xlsx                  # planilha alimentada pelo RTD
│
├── app/
│   ├── config.py               # load/save/merge de configuração
│   ├── gui/
│   │   ├── main_window.py      # janela principal, timers, exportação, encerramento
│   │   ├── ranking_table.py    # tabela com ordenação numérica por qualquer coluna
│   │   ├── status_bar.py       # health bar (verde/amarelo/vermelho, capture risk)
│   │   ├── diagnostics.py      # snapshot inspector + benchmark p50/p95/p99
│   │   └── history_dialog.py   # tela de histórico com filtros
│   ├── excel/
│   │   ├── connector.py        # GetActiveObject("Excel.Application"), reconexão
│   │   ├── detector.py         # detecção automática de workbook/planilha/colunas
│   │   └── snapshot.py         # leitura do bloco de dados em 1 chamada COM
│   ├── capture/
│   │   ├── worker.py           # QThread de captura (CoInitialize/CoUninitialize)
│   │   └── multiset_diff.py    # reconciliação de snapshots (componente crítico)
│   ├── domain/
│   │   ├── trade.py            # Trade, TradeKey, PairKey, expand_key
│   │   └── broker_stats.py     # BrokerStats, WindowStats, BrokerRow
│   ├── analytics/
│   │   ├── aggregator.py       # totais do pregão, sessão, thread-safe
│   │   ├── rolling_windows.py  # janelas 5/10/30/60/300 s + aceleração
│   │   └── ranking.py          # top compradores/vendedores/saldo, filtros
│   ├── persistence/
│   │   ├── database.py         # esquema, índices, consultas
│   │   ├── writer.py           # thread consumidora da fila, batch + transação
│   │   └── export.py           # CSV pt-BR (; e ,) e Parquet
│   └── utils/
│       ├── logger.py           # arquivo rotativo logs/flowrank.log
│       └── normalization.py    # cabeçalhos, lados, corretoras, números
│
├── tools/check_excel.py        # diagnóstico via linha de comando
├── tests/                      # 36 testes (foco em deduplicação)
├── data/flowrank.db            # banco (criado na primeira execução)
└── logs/flowrank.log
```

## Dependências

`PySide6`, `pywin32`, `PyYAML`, `pandas`, `pyarrow`, `pytest`.

O ambiente foi criado com **CPython 3.12** (`py -3.12`). O `python` do PATH desta máquina é o do
MSYS2, que não possui wheels de PySide6/pywin32 — use sempre o interpretador do `.venv`.

## Instalação e execução

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

Testes:

```powershell
pytest
```

Diagnóstico rápido sem GUI (mostra a tabela detectada e os negócios novos por snapshot):

```powershell
python -m tools.check_excel 5
```

O VS Code já está configurado para ativar o `.venv` automaticamente em terminais novos
(`.vscode/settings.json`) e há uma configuração de debug "FlowRank" (`.vscode/launch.json`).

## Banco de dados

`data/flowrank.db` (SQLite, WAL). Tabela `trades`:

| campo | descrição |
|---|---|
| `id` | autoincremento |
| `capture_timestamp` | epoch da captura |
| `trade_time` | hora exibida no T&T |
| `symbol` | ativo |
| `price`, `quantity` | preço e lote |
| `broker` | corretora |
| `aggressor_side` | `COMPRA`, `VENDA`, `RLP` ou `INDEFINIDO` |
| `session_date` | pregão |

Índices em `session_date`, `broker`, `aggressor_side`, `capture_timestamp` e `(session_date, broker)`.

Consulta rápida:

```powershell
python -c "import sqlite3;c=sqlite3.connect('data/flowrank.db');print(c.execute('select broker,aggressor_side,sum(quantity) from trades group by 1,2 order by 3 desc').fetchall())"
```

## Configurações importantes (`config.yaml`)

- `capture.interval_ms` — intervalo entre snapshots (250 ms = 4/s). Também alterável na GUI.
- `capture.max_rows` — teto de linhas lidas por snapshot; o leitor cresce/encolhe o bloco sozinho.
- `capture.risk_warn` / `risk_critical` — limiares de `capture_utilization` (amarelo/vermelho).
- `gui.refresh_ms` — atualização visual (500 ms), independente da captura.
- `gui.top_n` — linhas por ranking.
- `database.flush_interval_ms` / `batch_size` — persistência em lote (1 transação por batch).
- `analytics.windows_s` — janelas móveis calculadas.
- `excel.workbook` / `worksheet` / `header_row` / `symbol` — `auto` por padrão.
- `broker_aliases` — mapa opcional (`"Santander Institucional": "Santander"`); vazio por padrão.

## Detecção automática da tabela

O FlowRank varre todos os workbooks e planilhas abertos e reconhece dois layouts, aceitando
variações de nome (`Hora`, `Preço`, `Preco`, `Qtd`, `Agente_Agressor`, ...):

- **Layout agressor**: `Data | Valor | Quantidade | Agente Agressor | Agressor`
- **Layout contraparte**: `Data | Compradora | Valor | Quantidade | Vendedora`
  (cada linha vira 1 compra + 1 venda; é o layout atual da `times.xlsx` aberta)

O ativo é lido da célula acima do cabeçalho (`DOLPRO`) e pode ser sobrescrito na GUI.

## Deduplicação (prioridade máxima)

A comparação entre snapshots usa **`collections.Counter` (multiset)**:

- linhas idênticas repetidas são negócios legítimos e **contam individualmente**;
- timestamps repetidos **nunca** são tratados como duplicata;
- linhas que permanecem visíveis entre snapshots **não** são recontadas;
- a ordem das linhas é irrelevante (o T&T insere no topo);
- o primeiro snapshot após start ou reconexão é apenas **baseline**;
- `drop_duplicates()` e `set()` não são usados em lugar nenhum.

Os novos negócios são emitidos em ordem cronológica (do mais antigo para o mais recente).
Isso é coberto por 11 testes em `tests/test_multiset_diff.py`.

## O que já funciona

1. Conexão à instância aberta do Excel via COM, sem salvar nem substituir o RTD.
2. Detecção automática de workbook, planilha, linha do cabeçalho, colunas e ativo (2 layouts).
3. Captura contínua em thread própria com intervalo configurável (100 ms a 1 s).
4. Multiset diff com baseline, preservação de multiplicidade e métrica de `capture_utilization`.
5. Ranking de maiores compradores, maiores vendedores e saldo por corretora, com ordenação por clique.
6. Estatísticas por corretora: compra, venda, saldo, nº de negócios, lote médio, maior lote, RLP.
7. Janelas móveis 5/10/30/60/300 s em memória (`deque`, uma passagem por refresh) e contratos/s.
8. Detecção de aceleração (últimos 10 s vs 10–20 s atrás) como métrica informativa.
9. RLP preservado sem inventar lado (`RLP` só vira COMPRA/VENDA se a direção estiver explícita).
10. Sessão por pregão com reinício automático na virada do dia.
11. SQLite com fila `queue.Queue` não bloqueante, escrita em batch e drenagem no encerramento.
12. Health check completo: estado verde/amarelo/vermelho, último negócio, snapshots/s, fila,
    persistidos, erros COM/DB e `CAPTURE RISK`.
13. Reconexão automática a cada 2 s com redetecção completa e novo baseline.
14. Snapshot inspector e benchmark (avg/p50/p95/p99 de leitura COM, diff e agregação).
15. Tela de histórico com filtros (sessão, corretora, lado, hora inicial/final, quantidade mínima).
16. Exportação de ranking e negócios em CSV pt-BR e Parquet.
17. Filtros na GUI (Todos/COMPRA/VENDA/RLP) e busca por corretora.
18. Log rotativo em `logs/flowrank.log` (sem registrar trade a trade).
19. Encerramento seguro: para captura, drena fila, faz flush, fecha banco e salva configuração.

## Limitações técnicas reais

- **Janela do T&T**: o Excel mostra apenas N linhas (29 na planilha atual). Se entrarem mais de N
  negócios entre dois snapshots, os que saírem da janela são perdidos — limitação estrutural do RTD,
  não do FlowRank. O indicador `CAPTURE RISK` sinaliza a aproximação desse limite (amarelo ≥70%,
  vermelho ≥90%); a mitigação é reduzir o intervalo de captura ou ampliar a faixa do RTD.
- **Reaparecimento tardio**: se uma linha idêntica sair da janela e voltar a aparecer depois
  (por exemplo, após reconfiguração do RTD), ela é contada de novo. Não há ID de negócio no T&T.
- **Reconexão**: ao reconectar, o baseline é refeito; os negócios ocorridos durante a queda não
  são recuperados.
- **Layout contraparte**: sem coluna de agressor, "compra"/"venda" significam corretora
  compradora/vendedora do negócio, não agressão real. Cada linha gera 2 registros no banco
  (um por lado); os totais de "Negócios" e "Contratos" no topo continuam contando linhas.
- **Preço atual**: é o preço do negócio mais recente visível; nenhum dado ausente é inventado.
- **COM**: leitura síncrona; cada snapshot custa ~5–10 ms nesta máquina. Intervalos abaixo de
  100 ms tendem a saturar o Excel sem ganho real.
- Requer Windows com Excel aberto; sem Excel a aplicação fica em estado vermelho e tenta reconectar.

## Versões futuras

- Seleção de sessões anteriores na tela principal (hoje só no histórico).
- Múltiplos ativos simultâneos (o esquema já guarda `symbol`).
- Gráficos de fluxo acumulado e heatmap por corretora.
- Aliases de corretora editáveis pela GUI.
- Alertas configuráveis a partir da métrica de aceleração.
