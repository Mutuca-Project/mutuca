---
id: a023d0f4-8da9-4742-bf7e-528b2fb72dd7
aliases:
tags:
  - mutuca/docs/arquitetura/armazenamento
created_at: 2026-01-06
status: aceito
description: Definição da metodologia de versionamento e abstração de armazenamento
---
%%
last_modified:: `=dateformat(this.file.mtime, "dd-MM-yyyy")`
%%
___
## Context

No jornalismo investigativo, a **integridade dos dados** e a capacidade de auditoria são fundamentais. Repórteres frequentemente precisam responder: "O que dizia este dado no dia que publicamos a matéria?" ou testar hipóteses sem corromper a base de dados principal.

Arquivos soltos (CSVs/Excel) em pastas compartilhadas sofrem com controle de versão precário ("final_v2_agora_vai.xlsx"), dificultando o _fact-checking_ e aumentando o risco jurídico em caso de contestações da reportagem. É necessário um sistema que permita "viajar no tempo" e criar ramificações seguras para análise.

## Decision

Adotei o **MinIO** como Object Storage e **Apache Iceberg** gerenciado pelo **Project Nessie**.

- **MinIO:** Armazena os objetos brutos, funcionando como o "arquivo morto" digital da redação.
- **Apache Iceberg + Nessie:** Atuam como um "Git para Dados". Permitem que jornalistas criem **Branches** (ex: `investigacao-saude`, `teste-hipotese-gastos`) isolados da base principal (`main`).

## Alternatives Considered

**Hive Metastore (HMS):**

- **Pros:** Padrão legado.
- **Cons:** Estado global mutável. Se um jornalista sobrescreve uma tabela por engano, o dado original é perdido ou difícil de recuperar.
- **Rejeitado por:** Alto risco operacional para equipes de dados distribuídas.

**PostgreSQL (Tradicional):**

- **Pros:** Simples.
- **Cons:** Dificuldade em manter histórico completo de todas as alterações sem modelagem complexa (SCD Type 2).
- **Rejeitado por:** Não oferece a funcionalidade nativa de "Time Travel" (viajar para o estado exato do banco em um timestamp passado).

## Consequences

**Positivos:**

- **Segurança Jurídica e Fact-Checking:** O sistema permite consultar o estado exato dos dados em qualquer ponto do passado (Time Travel), provando a veracidade da informação no momento da publicação.
- **Experimentação Segura:** Jornalistas podem criar branches para testar cruzamentos de dados ou limpezas agressivas sem medo de destruir o trabalho dos colegas ou a fonte primária.
- **Isolamento de Narrativas:** Diferentes investigações podem ocorrer em paralelo na mesma base de dados sem interferência mútua.

**Negativos:**

- Introduz um conceito novo (Git para dados) que pode exigir treinamento para jornalistas acostumados apenas com Excel/SQL básico.

## Notes

Esta arquitetura mimetiza o fluxo de revisão de código (Code Review) aplicado ao conteúdo editorial, elevando o padrão de rigor da apuração.