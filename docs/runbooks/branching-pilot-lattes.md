# Runbook — Teste Ponta a Ponta do Branching Nessie (issue #59)

Pipeline piloto: `ingestao_lattes_ssd`

Este runbook valida o fluxo completo de branching por execução de ingestão
conforme ADR 007. Execute os checkpoints na ordem — cada um depende do anterior.

---

## Pré-condições

Antes de disparar o DAG, confirme que a infraestrutura está saudável e os
dados de entrada existem.

### 1. Serviços rodando e saudáveis

```bash
docker compose ps
```

Esperado: `lakehouse-nessie`, `lakehouse-trino`, `lakehouse-minio` e
`lakehouse-airflow` com status `Up` ou `healthy`.

### 2. Nessie acessível e branch `main` existente

```bash
curl -s http://localhost:19120/api/v2/trees | jq '.references[] | select(.name=="main") | {name, hash: .hash}'
```

Esperado: objeto JSON com `name: "main"` e um hash de 64 caracteres.

### 3. Tabela `iceberg.bronze.lattes_raw` existe no Trino

```bash
docker exec lakehouse-trino trino --execute "SHOW TABLES IN iceberg.bronze"
```

Esperado: `lattes_raw` na lista. Se não existir, crie antes de prosseguir:

```sql
-- rodar no Trino (via DBeaver ou CLI)
CREATE TABLE iceberg.bronze.lattes_raw (
    data_extracao       TIMESTAMP,
    id_lattes           VARCHAR,
    nome                VARCHAR,
    atuacoes_profissionais VARCHAR,
    projetos_pesquisa   VARCHAR,
    producoes_bibliograficas VARCHAR
    -- ajuste as colunas conforme o schema real do JSONL
)
WITH (format = 'PARQUET');
```

### 4. Arquivo JSONL de teste disponível no MinIO

Para o teste piloto, não é necessário rodar o Scrapy completo. Deposite um
arquivo JSONL mínimo no bucket bronze:

```bash
# Cria um JSONL de teste com 3 registros
cat > /tmp/lote_teste.jsonl << 'JSONL'
{"id_lattes": "1234567890123456", "nome": "Pesquisador Teste A", "professional_performances": "[...]", "research_projects": "[...]", "bibliographic_productions": "[...]"}
{"id_lattes": "9876543210987654", "nome": "Pesquisadora Teste B", "professional_performances": "[]", "research_projects": "[]", "bibliographic_productions": "[]"}
{"id_lattes": "1111111111111111", "nome": "Doutor Teste C", "professional_performances": null, "research_projects": null, "bibliographic_productions": null}
JSONL

# Faz upload para o MinIO via CLI do mc (MinIO Client)
docker exec lakehouse-minio mc alias set local http://localhost:9000 minioadmin minioadmin 2>/dev/null
docker exec -i lakehouse-minio sh -c 'cat > /tmp/lote_teste.jsonl' < /tmp/lote_teste.jsonl
docker exec lakehouse-minio mc cp /tmp/lote_teste.jsonl local/bronze/lattes_raw/lote_teste.jsonl
```

Verifique que o arquivo chegou:

```bash
docker exec lakehouse-minio mc ls local/bronze/lattes_raw/
```

### 5. Airflow Variable `lattes_offset` existe

```bash
docker exec lakehouse-airflow airflow variables get lattes_offset 2>/dev/null || \
docker exec lakehouse-airflow airflow variables set lattes_offset 0
```

---

## Execução do teste

### Passo 1 — Confirme o estado inicial do Nessie

Anote o hash atual de `main` antes do teste para comparar ao final:

```bash
curl -s http://localhost:19120/api/v2/trees \
  | jq -r '.references[] | select(.name=="main") | .hash'
```

Guarde esse valor — chamaremos de `HASH_ANTES`.

### Passo 2 — Dispare o DAG manualmente

Via UI do Airflow (http://localhost:8081):
1. Abra o DAG `ingestao_lattes_ssd`
2. Clique em **Trigger DAG** (botão ▶ no canto superior direito)
3. Confirme sem parâmetros adicionais

Ou via CLI:

```bash
docker exec lakehouse-airflow airflow dags trigger ingestao_lattes_ssd
```

### Passo 3 — Monitore `create_nessie_branch`

Na UI do Airflow, acompanhe a primeira task. Quando estiver verde (Success),
valide que a branch foi criada no Nessie:

```bash
# Lista todas as branches — deve aparecer uma ingest_ingestao_lattes_ssd_*
curl -s http://localhost:19120/api/v2/trees \
  | jq '.references[] | select(.name | startswith("ingest_")) | {name, hash}'
```

Esperado: uma branch com nome `ingest_ingestao_lattes_ssd_YYYYMMDD_HHmmss`.

Verifique também o valor no XCom do Airflow:

```bash
# Substitua <run_id> pelo ID da execução atual
docker exec lakehouse-airflow airflow tasks states-for-dag-run \
  ingestao_lattes_ssd <run_id>
```

### Passo 4 — Monitore `setup_docker_env` e `crawl_lattes_ssd`

Estas tasks não mudam com o branching. `crawl_lattes_ssd` depositará o JSONL
no MinIO. Como usamos um arquivo de teste já depositado no Passo 0,
o spider pode falhar (SSD não montado) — nesse caso, avance manualmente:

```bash
# Se o spider não tiver o SSD: marque a task como success manualmente
docker exec lakehouse-airflow airflow tasks clear ingestao_lattes_ssd \
  -t "crawl_lattes_ssd" --yes
```

> ⚠️ Em produção real com o SSD montado, o spider roda normalmente e deposita
> o JSONL automaticamente. O arquivo de teste já depositado no Passo 0 serve
> como substituto para este teste.

### Passo 5 — Monitore `load_to_iceberg`

Quando a task iniciar, confirme nos logs do Airflow que está usando o caminho
PyIceberg (não Trino):

```bash
docker exec lakehouse-airflow airflow tasks logs ingestao_lattes_ssd \
  load_to_iceberg <run_id>
```

Esperado nos logs:
```
[branch=ingest_ingestao_lattes_ssd_...] Lendo bronze/lattes_raw/lote_teste.jsonl...
  lote_teste.jsonl: 3 linhas inseridas na branch 'ingest_ingestao_lattes_ssd_...'
  lote_teste.jsonl movido para processed/.
```

**Validação: dado está na branch, mas ainda NÃO em `main`**

Neste momento, `main` ainda não tem os dados novos. Confirme com o Trino
(que aponta sempre para `main`):

```bash
docker exec lakehouse-trino trino --execute \
  "SELECT COUNT(*) FROM iceberg.bronze.lattes_raw"
```

Esperado: contagem **sem** os 3 registros de teste (ou 0 se a tabela estava vazia).

### Passo 6 — Monitore `merge_to_main`

Quando a task completar, o Nessie registra um novo commit em `main`. Valide:

```bash
curl -s http://localhost:19120/api/v2/trees \
  | jq -r '.references[] | select(.name=="main") | .hash'
```

Esperado: hash diferente do `HASH_ANTES` anotado no Passo 1.

**Validação: dado agora visível em `main` via Trino**

```bash
docker exec lakehouse-trino trino --execute \
  "SELECT id_lattes, nome FROM iceberg.bronze.lattes_raw LIMIT 5"
```

Esperado: os 3 registros de teste aparecem.

### Passo 7 — Monitore `increment_batch_offset`

```bash
docker exec lakehouse-airflow airflow variables get lattes_offset
```

Esperado: `100000` (incremento do batch_size definido no YAML).

### Passo 8 — Monitore `delete_branch`

Após a task completar, confirme que a branch de ingestão foi removida:

```bash
curl -s http://localhost:19120/api/v2/trees \
  | jq '.references[] | select(.name | startswith("ingest_"))'
```

Esperado: saída vazia — nenhuma branch de ingestão órfã.

---

## Estado final esperado

| Item | Estado |
|------|--------|
| Branch `ingest_*` no Nessie | Deletada |
| Branch `main` no Nessie | Hash avançado (novo commit) |
| Dados em `iceberg.bronze.lattes_raw` | 3 registros visíveis via Trino |
| Arquivo JSONL em `bronze/lattes_raw/` | Movido para `bronze/lattes_raw/processed/` |
| Variable `lattes_offset` | 100000 |
| Todas as tasks do DAG | Success (verde) |

---

## Rollback (se algo der errado)

Se `load_to_iceberg` falhar, a task `delete_branch` roda automaticamente
(TriggerRule.ALL_DONE) e limpa a branch. Nenhum dado chega ao `main`.

Para rollback manual de uma branch órfã:

```bash
source infrastructure/nessie/.venv/bin/activate

# Lista branches de ingestão existentes
curl -s http://localhost:19120/api/v2/trees \
  | jq -r '.references[] | select(.name | startswith("ingest_")) | .name'

# Deleta uma branch específica
python airflow/dags/shared/nessie_client.py delete ingest_ingestao_lattes_ssd_YYYYMMDD_HHmmss
```

Para desfazer um merge já feito para `main` (caso raro):

```bash
# Nessie não tem "revert" nativo — a abordagem é criar uma branch a partir
# do commit anterior ao merge e reassociar main a ela.
# Contate o responsável de dados antes de qualquer operação neste cenário.
```

---

## Troubleshooting rápido

| Sintoma | Causa provável | Ação |
|---------|---------------|------|
| `create_nessie_branch` falha | Nessie indisponível | `docker compose restart nessie` |
| `load_to_iceberg` falha com `TableNotFound` | Tabela não existe no Trino | Criar tabela (ver Pré-condição 3) |
| `load_to_iceberg` falha com `SchemaError` | Colunas do JSONL não batem com a tabela | Ajustar o JSONL de teste ou o schema |
| `merge_to_main` falha com conflito | Outra execução mergeou simultaneamente | Verificar `max_active_runs=1` no DAG |
| Dados aparecem no Trino antes do merge | Escrita foi para `main` diretamente | Verificar se XCom de `create_nessie_branch` está sendo lido pelo loader |
