---
id: 94a7d287-f17b-496b-9365-e88f6e4419a1
aliases:
tags:
  - mutuca/docs/arquitetura/query_engine
created_at: 2026-01-06
updated_at: 2026-05-21
status: aceito
description: Definição do motor de query SQL distribuída e federada
---
%%
last_modified:: `=dateformat(this.file.mtime, "dd-MM-yyyy")`
%%
___
## Context

Jornalistas de dados lidam com **fontes heterogêneas**: uma planilha vazada, uma API do governo,
um scrape de um site e um arquivo CSV gigante de log de servidor. A necessidade operacional é
cruzar essas fontes díspares rapidamente usando SQL sem precisar importar tudo para um banco de
dados tradicional ou fatiar arquivos grandes que travam o Excel.

A escolha do motor de query merece precisão terminológica, pois "processamento distribuído" é
uma categoria ampla que abrange ferramentas com modelos de execução radicalmente diferentes:

- **Spark** é um *framework de processamento distribuído*: constrói DAGs de transformações,
  gerencia shuffle entre stages, persiste estado intermediário (RDDs), suporta algoritmos
  iterativos e tolerância a falhas por linhagem. É projetado para ETL pesado e ML.
- **Trino** é um *motor de query SQL analítica distribuída e federada* (MPP — Massively
  Parallel Processing): distribui a execução de uma query entre workers via pipeline, mas
  cada query é stateless e atômica. Não há DAG de stages com shuffle, não há persistência
  entre operações, não há algoritmos iterativos. É projetado para queries interativas sobre
  grandes volumes.

O modelo de execução do Trino — pipeline dentro de uma query, sem estado entre queries — é
o correto para o caso de uso do Mutuca: interrogação analítica de dados já armazenados no
Iceberg, com transformações expressas em SQL (dbt). Não é a ferramenta certa para ETL com
múltiplos shuffles ou joins em escala de bilhões de linhas.

## Decision

Adotei o **Trino** como motor de query SQL distribuída e federada.

O Trino permite consultar dados onde eles estão (no MinIO/S3 via catálogo Iceberg) usando SQL
padrão ANSI, atuando como a camada unificada de interrogação dos dados independentemente do
formato ou volume. A capacidade de federar múltiplas fontes heterogêneas via conectores
(Iceberg, PostgreSQL, etc.) sem movimentação de dados é o diferencial central para o contexto
do projeto.

## Alternatives Considered

**Apache Spark:**

- **Pros:** Correto para ETL pesado (múltiplos stages, shuffle, joins de bilhões de linhas),
  ML distribuído, algoritmos iterativos.
- **Cons:** Modelo de execução inadequado para o caso de uso. As transformações do Mutuca são
  queries SQL (dbt Bronze→Silver→Gold), não pipelines de processamento iterativo. Além disso:
  curva de aprendizado íngreme (PySpark/Scala) para jornalistas acostumados com SQL; overhead
  de inicialização alto para queries exploratórias ad-hoc; footprint de memória incompatível
  com o hardware de 16GB.
- **Rejeitado por:** O modelo de execução do Spark (DAG, shuffle, stages) é overkill para
  transformações SQL sobre dados já armazenados em Parquet/Iceberg. Trino faz o mesmo trabalho
  com latência interativa e sem a complexidade operacional do Spark.

**PostgreSQL Local:**

- **Pros:** Familiaridade; sem infraestrutura adicional.
- **Cons:** Performance degrada rapidamente com bases na casa dos Gigabytes (comum em
  vazamentos ou dados públicos federais). Não federa fontes externas.
- **Rejeitado por:** Limitação de escala vertical; sem suporte a Iceberg/Parquet nativamente.

## Consequences

**Positivos:**

- **Democratização do acesso:** Jornalistas com conhecimento de SQL podem interrogar bases que
  não caberiam na memória local — o Trino distribui a execução entre workers sem exigir que o
  analista conheça o modelo de execução subjacente.
- **Federação sem movimentação de dados:** Trino consulta Iceberg no MinIO, PostgreSQL e outras
  fontes no mesmo `SELECT`, sem ETL intermediário.
- **SQL ANSI como lingua franca:** Facilita colaboração com analistas externos sem aprendizado
  de APIs proprietárias.
- **Latência interativa:** Respostas em segundos/minutos para queries analíticas complexas —
  adequado para o fluxo exploratório da reportagem.

**Negativos:**

- **Não é adequado para ETL com múltiplos shuffles:** Transformações que exigem múltiplos
  passes sobre os dados (ex: algoritmos iterativos, joins de bilhões de linhas com shuffle
  massivo) devem usar Spark. Forçar esse tipo de workload no Trino resulta em OOM ou timeout.
  No Mutuca, as transformações dbt são queries SQL pontuais — dentro do modelo suportado.
- **Requer ajuste de JVM:** Rodar estável em 16GB exige configuração cuidadosa do heap da JVM
  (ver `infrastructure/trino/jvm.config`). O limite de 11GB reservado para o Trino não deve
  ser excedido sem avaliação de impacto nos demais serviços.
- **Ponto único de falha para queries:** Se o Trino estiver indisponível, nenhuma transformação
  dbt nem consulta analítica pode ser executada. O dado bruto permanece acessível no MinIO, mas
  a camada de análise fica inoperante.

## Notes

O Trino atua como a "Redação Unificada" — onde dados de diferentes origens se encontram para
virar informação, com SQL como linguagem comum entre engenheiros e jornalistas.

**Nota terminológica (atualização maio de 2026):** O título original deste ADR usava "motor de
processamento distribuído", terminologia associada ao Spark (DAG, stages, shuffle). Trino é
corretamente classificado como motor de query SQL analítica distribuída e federada (MPP). A
distinção importa: Trino distribui execução de queries, não processamento de pipelines de
transformação iterativa.
