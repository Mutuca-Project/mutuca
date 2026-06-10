# Pipeline: Emendas Parlamentares (CGU)

Pipeline responsável pela coleta, validação e ingestão incremental das emendas parlamentares publicadas no Portal da Transparência da Controladoria-Geral da União (CGU). É o **gatilho principal** da investigação Teopolítica, pois fornece os dados de execução orçamentária que permitem rastrear o fluxo de recursos públicos até beneficiários finais.

---

## Hipótese investigativa

Este pipeline alimenta a **Hipótese 2** da investigação:

> Existe um circuito integrado conectando **Emendas Pix → organizações religiosas → prefeituras**, configurando o que a investigação chama de "teopolítica financiada".

O campo `favorecido` de cada documento de pagamento (OB) é a peça central: ao cruzar o CNPJ do favorecido com o QSA da Receita Federal e com os dados da ANATEL, é possível identificar se o beneficiário final é uma organização religiosa, uma rádio comunitária ou uma entidade vinculada a lideranças políticas locais.

---

## Fonte dos dados

| Atributo | Detalhe |
|---|---|
| **Origem** | Portal da Transparência — CGU |
| **Endpoint A1** | `https://portaldatransparencia.gov.br/emendas/consulta/resultado` |
| **Endpoint A2** | `https://portaldatransparencia.gov.br/emendas/documentos-relacionados/resultado` |
| **Cobertura** | 2018 até o presente (incremental mensal) |
| **Tipos de emenda** | Individual (sk=2), Bancada (sk=3), Comissão (sk=4), Relator (sk=5) |
| **Granularidade** | Um registro por documento (OB/NE/NS) por emenda |

---

## Arquitetura da coleta

A coleta opera em dois níveis de API, encadeados por `codigoEmenda`:

```
[A1] /emendas/consulta/resultado
     Paginação: blocos de 1.000 emendas (offset incremental)
     ↓  codigoEmenda (chave primária — somente códigos numéricos)
     ↓  filtro: S/I e REL. GERAL descartados antes de consultar A2

[A2] /emendas/documentos-relacionados/resultado
     Paginação: blocos de 1.000 documentos por emenda (offset incremental)
     ↓  documentos: Empenho (NE), Liquidação (NS), Pagamento (OB)

[MinIO] s3://bronze/emendas_parlamentares/lote_<timestamp>.jsonl
     Arquivo JSONL — um objeto por linha
     ↓

[Iceberg] bronze.cgu_emendas_parlamentares
     Carregado pelo iceberg_loader via PyIceberg na branch Nessie
```

---

## Componentes

### `EmendasParlamentaresSpider`

Localização: `scrapy/mutuca/spiders/cgu/emendas_parlamentares.py`

Responsável exclusivamente pela **orquestração HTTP**:

- Dispara requisições paginadas ao A1 com os parâmetros `de` e `ate` (anos)
- Valida `codigoEmenda` antes de cada requisição A2 via `CguEmendasCollector.codigo_emenda_valido()`
- Pagina o A2 enquanto `offset + PAGE_SIZE < recordsTotal`
- Delega todo o mapeamento e construção de itens ao `CguEmendasCollector`

Argumentos do spider (passados pelo Airflow via `scrapy.args` no YAML):

| Argumento | Descrição | Padrão |
|---|---|---|
| `de` | Ano inicial da raspagem | Ano corrente |
| `ate` | Ano final da raspagem | Ano corrente |

### `CguEmendasCollector`

Localização: `scrapy/mutuca/core/cgu_emendas_collector.py`

Responsável pela **transformação de dados** — funções puras (stateless):

| Método | Entrada | Saída | Descrição |
|---|---|---|---|
| `codigo_emenda_valido(codigo)` | `str` | `bool` | Valida se o código é numérico (10–14 dígitos) |
| `extrair_dados_a1(emenda)` | `dict` camelCase | `dict` snake_case | Mapeia 21 campos do payload A1 |
| `montar_params_a2(dados_a1, page_size, offset)` | `dict` | `dict` | Constrói parâmetros da query A2 |
| `construir_item(dados_a1, doc)` | dois `dict` | `EmendaParlamentarItem` | Consolida A1 + A2 em um item Scrapy |

### `EmendaParlamentarItem`

Localização: `scrapy/mutuca/items/cgu_emendas_item.py`

Define o contrato de schema de saída do spider — 26 campos declarados explicitamente via `scrapy.Field()`. O campo `data_extracao` **não está no item**: é adicionado pelo `iceberg_loader` como `TIMESTAMP WITH TIME ZONE` no momento da carga, seguindo o padrão uniforme de todos os pipelines.

---

## Decisões de design

### Filtro de `codigoEmenda` inválido

A API da CGU retorna valores não-numéricos como `S/I` e `REL. GERAL` no campo `codigoEmenda` para emendas de comissão sem código individual. Esses valores fazem o endpoint A2 ignorar o filtro de código e retornar todos os documentos que casam com os demais parâmetros, produzindo até **403.000 documentos por "emenda"**. O filtro `codigo_emenda_valido()` descarta esses registros antes de qualquer requisição ao A2.

Validado empiricamente: dump 2018–2026 identificou `S/I` (403.000 docs) e `REL. GERAL` (124.000 docs). Após correção: 0 registros com código inválido.

### Paginação do A2

O spider original assumia que todas as emendas teriam no máximo 1.000 documentos. Emendas de Relator (`sk_tipo_emenda=5`) — categoria do "orçamento secreto" — podem ter centenas de beneficiários municipais, superando esse limite silenciosamente. Após a implementação da paginação do A2, emendas como `202181000792` passaram de 1.000 para **6.034 documentos** e `202081000291` de 1.000 para **4.487 documentos**.

---

## Pipeline Airflow

Arquivo: `airflow/dags/pipelines/cgu.yaml`

```
create_nessie_branch
  → setup_docker_env + build_dbt_validator
  → crawl_emendas_parlamentares    (DockerOperator — EmendasParlamentaresSpider)
  → load_to_iceberg                (PyIceberg na branch Nessie isolada)
  → dbt_test_branch                (gate de qualidade — bloqueia merge em falha)
  → merge_to_main
  → delete_branch
```

**Schedule:** `0 6 1 * *` (primeiro dia de cada mês às 06:00)

**Airflow Variables necessárias:**

| Variável | Descrição | Exemplo |
|---|---|---|
| `cgu_emendas_ano_inicio` | Ano inicial da janela de coleta | `"2026"` |
| `cgu_emendas_ano_fim` | Ano final da janela de coleta | `"2026"` |

Para a carga histórica completa, use `"2018"` e `"2026"`. Para execuções mensais incrementais, ambas as variáveis apontam para o ano corrente.

---

## Schema Bronze

Tabela: `iceberg.bronze.cgu_emendas_parlamentares`
Localização: `s3://warehouse/bronze/cgu_emendas_parlamentares/`
DDL: `sql/create_tables_cgu_emendas.sql`

Ver [Dicionário de Dados](../modelos/dicionarios.md) para descrição completa de cada campo.

---

## Gate de validação dbt

Configurado em `dbt/branch_validator/models/bronze/sources.yml`. Executado na branch Nessie antes do merge para main — falha bloqueia a ingestão e a branch é descartada sem contaminar `main`.

| Campo | Teste | Severity | Justificativa |
|---|---|---|---|
| `data_extracao` | `not_null` | error | Adicionado pelo loader — ausência indica falha na carga |
| `codigo_emenda` | `not_null` | error | Chave do relacionamento A1→A2 |
| `codigo_documento` | `not_null` | error | Identificador do documento de execução |
| `fase_documento` | `not_null` | error | OB/NE/NS obrigatório para análise de execução |
| `favorecido` | `not_null` | warn | ~9,4% dos registros históricos sem padrão CNPJ/CPF |

---

## Como executar

### Pré-requisito: criar a tabela no Trino

```bash
docker exec -it lakehouse-trino trino \
  --execute "$(cat sql/create_tables_cgu_emendas.sql)"
```

### Configurar Airflow Variables

No Airflow UI (`http://localhost:8081`): Admin → Variables → criar:

- `cgu_emendas_ano_inicio` = `"2026"`
- `cgu_emendas_ano_fim` = `"2026"`

### Disparar o DAG

```bash
# Via CLI
docker exec lakehouse-airflow airflow dags trigger ingestao_cgu_emendas

# Ou via Airflow UI: DAGs → ingestao_cgu_emendas → Trigger DAG
```

### Execução local do spider (desenvolvimento)

```bash
cd scrapy/
source .venv/bin/activate
scrapy crawl emendas_parlamentares -a de=2026 -a ate=2026 -L INFO
```

O arquivo de saída será gerado em `scrapy/emendas_parlamentares_2026_2026.jsonl`.

---

## Testes

```bash
cd scrapy/
source .venv/bin/activate

# Suite completa (unitários + integração)
pytest tests/ -v

# Apenas testes do pipeline CGU
pytest tests/core/test_cgu_emendas_collector.py tests/spiders/cgu/test_emendas_parlamentares.py -v
```

**Cobertura:** 29 testes unitários (`CguEmendasCollector`) + 21 testes de integração (`EmendasParlamentaresSpider`).
