# Emendas Parlamentares (CGU)

Este pipeline coleta os dados de execução orçamentária das emendas parlamentares publicados pelo Portal da Transparência da Controladoria-Geral da União (CGU). É o **ponto de entrada principal** da investigação Teopolítica: sem saber quem recebeu recursos de emendas e quando, não é possível rastrear o circuito de financiamento que conecta parlamentares, prefeituras e organizações civis.

---

## O que são emendas parlamentares e por que rastreá-las

Emendas parlamentares são recursos que deputados e senadores têm o direito de destinar diretamente a municípios, estados ou entidades, sem passar pelos critérios de distribuição do orçamento federal regular. Nos últimos anos, uma modalidade específica — as chamadas **Transferências Especiais**, ou "Emendas Pix" — passou a transferir bilhões de reais a prefeituras sem qualquer exigência de prestação de contas sobre o uso final dos recursos.

Esse é o "ponto cego" que a investigação Teopolítica tenta iluminar: o dinheiro chega à prefeitura, e depois? Quem recebe as licitações contratadas com esses recursos? Há conexão entre os contratados e lideranças religiosas ou políticas locais?

O Portal da Transparência da CGU publica os dados de execução — o que foi empenhado, liquidado e pago, e para quem. É desse portal que este pipeline extrai as informações.

---

## Como a coleta funciona

A API do portal opera em dois níveis:

**Nível 1 — Lista de emendas (endpoint A1)**

O spider consulta o endpoint de consulta de emendas, que retorna uma lista paginada com todas as emendas de um período. Para cada emenda, traz informações como o parlamentar autor, a função orçamentária (saúde, educação, assistência social), o município de destino e os valores totais empenhados, liquidados e pagos.

**Nível 2 — Documentos de execução (endpoint A2)**

Para cada emenda listada no A1, o spider consulta o endpoint de documentos relacionados. Aqui estão os registros individuais de cada transferência: a Nota de Empenho (NE), a Nota de Liquidação (NS) e, o mais importante para o rastreamento, a **Ordem Bancária (OB)** — o documento que comprova que o dinheiro saiu do Tesouro e chegou ao destino. Cada OB traz o CNPJ do favorecido final.

```
[A1] Consulta de emendas
     → lista paginada de emendas com parlamentar, destino e valores

[A2] Documentos por emenda
     → NE (Empenho) + NS (Liquidação) + OB (Pagamento com CNPJ do favorecido)
```

O campo `favorecido` da OB é a peça central da investigação: cruzando esse CNPJ com o Quadro de Sócios da Receita Federal, é possível identificar se o beneficiário final é uma organização religiosa, uma rádio comunitária ou uma entidade vinculada a lideranças políticas locais.

---

## Desafios técnicos identificados e resolvidos

### Emendas sem código válido

A API retorna valores como `S/I` ("Sem Informação") e `REL. GERAL` no campo de código da emenda para certos tipos de emenda de comissão. Quando esses valores são usados para consultar os documentos, a API ignora o filtro e devolve todos os documentos que casam com os demais parâmetros — chegando a **403.000 documentos por "emenda"**. O spider detecta e descarta esses casos antes de qualquer consulta ao A2.

### Truncamento de emendas com muitos beneficiários

A API pagina os documentos em blocos de 1.000. As **Emendas de Relator** — categoria associada ao chamado "orçamento secreto" por sua baixa rastreabilidade — podem ter centenas de beneficiários municipais, gerando mais de 1.000 documentos por emenda. Sem paginação, os documentos excedentes seriam descartados silenciosamente.

Após validação empírica com o dump histórico 2018–2026, confirmamos o truncamento: a emenda `202181000792`, por exemplo, aparecia com exatamente 1.000 documentos no dump original. Com a paginação implementada, passou a ter **6.034 documentos**.

!!! warning "Nota investigativa"
    As Emendas de Relator (tipo 5) são exatamente as de menor rastreabilidade e maior suspeita de uso político. Não paginar o A2 para esse tipo de emenda significaria perder os dados mais relevantes para a investigação.

---

## Fluxo no Airflow

O pipeline é orquestrado pelo Airflow via `airflow/dags/pipelines/cgu.yaml` e executa no primeiro dia de cada mês às 06:00.

```
create_nessie_branch          ← cria branch isolada de ingestão
  → crawl_emendas_parlamentares   ← spider coleta e grava JSONL no MinIO
  → load_to_iceberg               ← loader carrega JSONL na tabela Bronze (branch)
  → dbt_test_branch               ← valida qualidade antes de consolidar
  → merge_to_main                 ← aprovado: dados chegam ao main
  → delete_branch                 ← limpeza
```

Se o teste dbt falhar, a branch é descartada e o `main` não é alterado.

**Controle incremental:** antes de cada execução, ajuste as variáveis no Airflow UI:

- `cgu_emendas_ano_inicio` — ano inicial da janela de coleta (ex: `"2026"`)
- `cgu_emendas_ano_fim` — ano final (ex: `"2026"`)

---

## Qualidade dos dados

Os dados são validados automaticamente antes de chegar à camada consolidada. Os campos críticos para a investigação têm testes configurados com `severity: error` — uma falha nesses campos bloqueia a ingestão completamente.

| Campo | Regra | Severidade |
|---|---|---|
| `data_extracao` | Não pode ser nulo | Erro (bloqueia) |
| `codigo_emenda` | Não pode ser nulo | Erro (bloqueia) |
| `codigo_documento` | Não pode ser nulo | Erro (bloqueia) |
| `fase_documento` | Não pode ser nulo | Erro (bloqueia) |
| `favorecido` | Não pode ser nulo | Aviso (não bloqueia) |

O `favorecido` tem severidade de aviso porque a análise do dump histórico mostrou que ~9,4% dos registros não seguem o padrão `CNPJ - NOME` — um comportamento presente na própria fonte, não um erro do pipeline.

---

## Referência técnica

- **Dicionário de dados:** [Dicionário de dados — CGU Emendas](../referencia/dicionario-cgu-emendas.md)
- **Código do spider:** `scrapy/mutuca/spiders/cgu/emendas_parlamentares.py`
- **Collector:** `scrapy/mutuca/core/cgu_emendas_collector.py`
- **Pipeline YAML:** `airflow/dags/pipelines/cgu.yaml`
- **DDL da tabela:** `sql/create_tables_cgu_emendas.sql`
- **Testes dbt:** `dbt/branch_validator/models/bronze/sources.yml`
