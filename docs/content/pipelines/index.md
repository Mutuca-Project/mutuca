# Pipelines de coleta

Um pipeline de coleta é o percurso completo que um dado público percorre desde a fonte — um portal governamental, uma API, um diário oficial — até o Lakehouse, onde pode ser consultado, cruzado e analisado.

No Mutuca, cada pipeline é declarado num arquivo YAML. Esse arquivo descreve a fonte, o destino, a frequência de execução e as regras de qualidade que os dados precisam passar antes de serem incorporados à base. O Airflow lê esses arquivos e monta o fluxo de trabalho automaticamente, sem que seja necessário escrever código Python para cada novo pipeline.

---

## Como um pipeline funciona

Todo pipeline segue o mesmo caminho:

```
Fonte pública → Coleta (Scrapy) → MinIO Bronze → Validação (dbt) → Iceberg main
```

A etapa de validação é o que diferencia a abordagem do Mutuca de uma simples raspagem. Antes de qualquer dado chegar à camada consolidada (o Iceberg `main`), ele passa por um conjunto de testes automáticos em uma branch isolada. Se algum teste falhar — campo obrigatório vazio, formato inesperado, volume anômalo — a branch é descartada sem contaminar a base principal. Só dados que passam pela validação chegam ao `main`.

Isso é especialmente importante para jornalismo investigativo: os dados precisam ser defensáveis. Um CNPJ ausente ou um valor mal formatado numa análise publicada pode comprometer a credibilidade de uma reportagem inteira.

---

## Pipelines ativos

| Pipeline | Fonte | Frequência | Status |
|---|---|---|---|
| [Emendas Parlamentares (CGU)](cgu-emendas.md) | Portal da Transparência | Mensal | ✅ Ativo |
| RFB CNPJ | Receita Federal | Manual | ✅ Ativo |
| Lattes (SSD) | CNPq | Manual | ✅ Ativo |

## Pipelines planejados

| Pipeline | Fonte | Hipótese |
|---|---|---|
| TCEs Nordeste | TCE-PE, TCE-PB, TCE-CE, TCE-BA | Rastrear destino municipal dos recursos |
| PNCP (contratações) | Portal Nacional de Contratações | Cruzar favorecidos com QSA |
| Querido Diário | OKBR | Detectar leis de subvenção social em DOMs |
| ANATEL (radiodifusão) | ANATEL dados abertos | Rádios controladas por lideranças religiosas |
| TSE (candidaturas) | TSE dados abertos | Candidatos com origem religiosa |
