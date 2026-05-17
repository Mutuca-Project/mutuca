---
id: ca843571-ea6b-4d80-bdbd-d910d1061199
aliases:
tags:
  - mutuca/docs/arquitetura/etl
created_at: 2026-01-06
status: aceito
description: Definição da metodologia de transformação e carregamento
---
%%
last_modified:: `=dateformat(this.file.mtime, "dd-MM-yyyy")`
%%
___

## Context

Em reportagens baseadas em dados, a **metodologia** é parte da história. Leitores e editores precisam entender como um número foi calculado (ex: "como chegamos ao total de gastos sem licitação?"). Scripts soltos de limpeza ("spaghetti code") tornam difícil explicar o processo e identificar erros de cálculo, minando a credibilidade da matéria.

## Decision

Adotei o **dbt Core (Data Build Tool)** para transformações declarativas.

O dbt permite escrever a lógica de transformação (limpeza, filtros, agregações) em SQL modular, gerando automaticamente a documentação e a linhagem (origem) do dado.

## Alternatives Considered

**Scripts Python Manuais (Pandas):**

- **Pros:** Flexível.
- **Cons:** "Caixa preta". Difícil para um editor não-técnico auditá a lógica de negócio enterrada em centenas de linhas de código Python.
- **Rejeitado por:** Baixa transparência metodológica.
    

**Stored Procedures:**

- **Pros:** Tradicional.
- **Cons:** Difícil de versionar e visualizar dependências.
- **Rejeitado por:** Dificulta a revisão por pares.
    

## Consequences

**Positivos:**

- **Transparência Radical (Methodology-as-Code):** O comando `dbt docs` gera um site navegável que explica a origem de cada tabela e coluna, servindo como base para a seção "Como fizemos" da reportagem.
- **Revisão por Pares:** A lógica SQL pode ser revisada por outros jornalistas no GitHub antes da publicação, reduzindo drasticamente a chance de erros de cálculo (erratas).
- **Testes Automatizados:** O dbt alerta automaticamente se aparecerem dados duplicados ou nulos onde não deveriam (ex: CPFs inválidos), fundamental para validação e integridade relacional de bases de dados.

**Negativos:**

- Curva de aprendizado inicial para entender o modelo de referências (`{{ ref() }}`) e configuração YAML.

## Notes

O dbt transforma a "cozinha" da investigação em um processo documentado e auditável, essencial para o jornalismo de alta credibilidade.