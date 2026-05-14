---
id: 94a7d287-f17b-496b-9365-e88f6e4419a1
aliases:
tags:
  - mutuca/docs/arquitetura/processamento_distribuído
created_at: 2026-01-06
status: aceito
description: Definição do motor de processamento SQL
---
%%
last_modified:: `=dateformat(this.file.mtime, "dd-MM-yyyy")`
%%
___
## Context

Jornalistas de dados lidam com **fontes heterogêneas**: uma planilha vazada, uma API do governo, um scrape de um site e um arquivo CSV gigante de log de servidor. A necessidade operacional é cruzar essas fontes díspares rapidamente usando uma linguagem franca (SQL) sem precisar importar tudo para um banco de dados tradicional ou fatiar arquivos grandes que travam o Excel.

## Decision

Adotei o **Trino** como motor de query federada.

O Trino permite consultar dados onde eles estão (no MinIO/S3) usando SQL padrão ANSI, atuando como a ferramenta unificada de interrogação dos dados, independentemente do formato ou volume.

## Alternatives Considered

**Apache Spark:**

- **Pros:** Poderoso para Machine Learning.
- **Cons:** Curva de aprendizado íngreme (Python/Scala) para repórteres acostumados com SQL. Lento para consultas exploratórias (ad-hoc).
- **Rejeitado por:** A latência alta prejudica o fluxo de "conversa com os dados" típico da fase exploratória da reportagem.

**PostgreSQL Local:**

- **Pros:** Familiaridade.
- **Cons:** Performance degrada rapidamente com bases na casa dos Gigabytes (comum em vazamentos ou dados públicos federais).
- **Rejeitado por:** Limitação de escala vertical no notebook do jornalista.

## Consequences

**Positivos:**

- **Democratização do Acesso:** Jornalistas com conhecimento de SQL podem interrogar bases gigantes (Big Data) que não caberiam na memória do computador, pois o processamento é otimizado pelo Trino.
- **Conformidade com Padrões:** O uso de SQL ANSI facilita a contratação ou colaboração com analistas de mercado, sem exigir aprendizado de linguagens proprietárias.
- **Agilidade na Apuração:** Respostas em segundos/minutos para perguntas complexas sobre grandes volumes de dados.

**Negativos:**

- Requer ajuste fino de memória (JVM) para rodar estável em hardware limitado (16GB).

## Notes

O Trino atua como a "Redação Unificada", onde dados de diferentes origens se encontram para virar informação.
