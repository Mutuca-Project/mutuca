# Runbook — Troubleshooting do Gate dbt Pré-Merge (ADR 008)

Este runbook cobre os erros mais prováveis durante a operação do gate `dbt_test_branch`
no pipeline de ingestão. Cada seção descreve o sintoma, a causa raiz e a ação corretiva.

---

## Diagnóstico rápido

Antes de qualquer coisa, verifique os logs do container do gate no Airflow:

1. Airflow UI → DAG → `dbt_test_branch` → View Logs
2. Identifique a linha de erro (procure por `Error`, `Exception`, `FAIL` ou `exit code`)
3. Use o número do erro neste guia

---

## Erro 1: `No module named 'dbt_duckdb.plugins.iceberg'`

**Sintoma:**
```
ModuleNotFoundError: No module named 'dbt_duckdb.plugins.iceberg'
```

**Causa:** O campo `module:` no `profiles.yml` usa o nome completo do módulo, que não existe
nessa forma. O loader de plugins do dbt-duckdb espera o nome curto.

**Solução:** Verifique `dbt/branch_validator/profiles.yml`:

```yaml
# ERRADO
plugins:
  - module: dbt_duckdb.plugins.iceberg

# CORRETO
plugins:
  - module: iceberg
```

---

## Erro 2: `'catalog' is a required argument for the iceberg plugin!`

**Sintoma:**
```
'catalog' is a required argument for the iceberg plugin!
```

**Causa:** A chave `catalog:` está ausente ou está estruturada como dict aninhado no `profiles.yml`.

**Solução:** O plugin chama `load_catalog(catalog, **config)` onde `catalog` é o primeiro
argumento posicional — deve ser uma **string simples** (o nome do catálogo):

```yaml
# ERRADO: catalog como dict
config:
  catalog:
    name: nessie_branch
    type: rest

# ERRADO: chaves com prefixo catalog_
config:
  catalog_name: nessie_branch
  catalog_type: rest

# CORRETO: catalog como string, demais propriedades no mesmo nível flat
config:
  catalog: nessie_branch      # ← string simples
  type: rest
  uri: "{{ env_var('NESSIE_ICEBERG_ENDPOINT') }}"
  prefix: "{{ env_var('NESSIE_BRANCH') }}"
```

---

## Erro 3: `'dict' object has no attribute 'upper'`

**Sintoma:**
```
AttributeError: 'dict' object has no attribute 'upper'
```

**Causa:** O campo `catalog:` no `profiles.yml` é um dict (indentado com filhos), não uma string.
O PyIceberg espera uma string para o nome do catálogo e chama `.upper()` nela internamente.

**Solução:** Idêntica ao Erro 2 — garantir que `catalog: nessie_branch` seja uma string no YAML.

---

## Erro 4: `Found two sources with name 'bronze_lattes_raw'`

**Sintoma:**
```
Found 2 matches for [source: bronze.lattes_raw] which is ambiguous.
```
ou
```
Error: Found two sources named 'bronze_lattes_raw'
```

**Causa:** Existe uma declaração duplicada da fonte `bronze` — provavelmente em `sources.yml`
e em `schema.yml` dentro de `models/bronze/`.

**Solução:** Consolidar tudo em `sources.yml` e deletar `schema.yml`:

```bash
ls dbt/branch_validator/models/bronze/
# Se existir schema.yml junto com sources.yml, delete o schema.yml:
rm dbt/branch_validator/models/bronze/schema.yml
```

---

## Erro 5: `Compilation Error - severity` (sintaxe deprecada)

**Sintoma:**
```
Compilation Error in test not_null_source_bronze_lattes_raw_id_lattes
  'severity' is not a valid test config.
```
ou warning de deprecação sobre `severity` fora de `config:`.

**Causa:** O dbt >= 1.9 exige que `severity` esteja dentro de um bloco `config:` aninhado,
não diretamente sob o nome do teste.

**Solução:**

```yaml
# ERRADO (sintaxe antiga)
- not_null:
    severity: error

# CORRETO (dbt >= 1.9)
- not_null:
    config:
      severity: error
```

---

## Erro 6: Gate falha por dados ruins (o comportamento esperado)

**Sintoma:**
```
Done. PASS=2 WARN=0 ERROR=1 FAIL=1 SKIPPED=0 TOTAL=4
```
O Airflow reporta a task `dbt_test_branch` como FAILED. A task `merge_to_main` é bloqueada.
A task `delete_branch` roda normalmente (TriggerRule.ALL_DONE).

**Isto é o comportamento correto.** O gate funcionou. Os dados ruins não chegaram a `main`.

**Para investigar a causa:**

1. Nos logs do Airflow, identifique qual teste falhou e em qual coluna.
2. Use o runbook de operação manual para inspecionar os dados da branch diretamente:
   ```bash
   # Recuperar o nome da branch via XCom do Airflow
   # Airflow UI → DAG Run → create_nessie_branch → XComs → return_value
   BRANCH_NAME="ingest_lattes_ssd_YYYYMMDD_HHmmss"
   ```
   Ver seção "Inspecionar os dados da branch via Python" no runbook de operação manual.

3. Identifique se o problema está no spider (dados malformados na extração) ou na tabela destino
   (schema divergente).

4. Após corrigir o spider, re-execute o DAG manualmente no Airflow. A branch anterior foi
   deletada pelo `delete_branch` — uma nova branch será criada na próxima execução.

---

## Erro 7: `NESSIE_BRANCH` está vazia ou é `None`

**Sintoma no log do gate:**
```
pyiceberg.exceptions.NoSuchTableError: Table does not exist: bronze.lattes_raw
```
ou
```
pyiceberg.exceptions.NoSuchNamespaceError: ...
```

**Causa provável:** A variável de ambiente `NESSIE_BRANCH` chegou vazia ao container. O template
Jinja `{{ ti.xcom_pull(task_ids='create_nessie_branch') }}` não foi resolvido, ou a task
`create_nessie_branch` falhou e não deixou XCom.

**Diagnóstico:**

```bash
# Verificar XCom da execução
# Airflow UI → DAG Run → create_nessie_branch → XComs
# O valor de 'return_value' deve ser o nome da branch (ex: ingest_lattes_ssd_20260516_143022)
```

**Possíveis causas:**
- `create_nessie_branch` falhou (Nessie indisponível)
- O nome do `task_ids` no `xcom_pull` não bate com o `task_id` real da task

**Solução:** Verificar saúde do Nessie e que o `task_id` no factory.py é `create_nessie_branch`
em ambos os lugares (definição da task e no template do environment).

---

## Erro 8: Container do gate não consegue acessar o MinIO (403 ou Connection Refused)

**Sintoma:**
```
botocore.exceptions.ClientError: An error occurred (403) when calling the HeadObject operation
```
ou
```
ConnectionRefusedError: [Errno 111] Connection refused
```

**Causa A (403):** Credenciais erradas. Verificar se as variáveis `MINIO_ACCESS_KEY` e
`MINIO_SECRET_KEY` na conexão Airflow `minio_s3_connection` estão corretas.

**Causa B (Connection Refused):** O container do gate não está na rede `mutuca-lakehouse_lakehouse-net`.
Verificar o campo `network_mode` no `DockerOperator`:
```python
network_mode="mutuca-lakehouse_lakehouse-net"
```

**Diagnóstico rápido:**
```bash
# Testar conectividade do MinIO de dentro da rede Docker
docker run --rm \
  --network mutuca-lakehouse_lakehouse-net \
  curlimages/curl \
  curl -v http://lakehouse-minio:9000/minio/health/live
```

---

## Erro 9: `build_dbt_validator` falha no Airflow (build da imagem)

**Sintoma:** A task `build_dbt_validator` falha com erro de build Docker.

**Causas comuns:**

```bash
# Ver log completo do build
# Airflow UI → DAG Run → build_dbt_validator → View Logs
```

| Erro no log | Causa | Solução |
|---|---|---|
| `Could not find a version that satisfies dbt-duckdb>=1.8,<2.0` | Versão não disponível no PyPI | Relaxar o constraint ou pinnar versão específica disponível |
| `ERROR [internal] load metadata for docker.io/library/python:3.11-slim` | Sem acesso ao Docker Hub | Verificar acesso à internet do host |
| `No space left on device` | Disco cheio no host | `docker system prune -f` para limpar imagens não usadas |
| `Cannot connect to the Docker daemon` | Socket do Docker não montado | Verificar configuração do DooD (mount do `/var/run/docker.sock`) |

---

## Branches órfãs acumuladas

Se `delete_branch` falhou em execuções anteriores, branches podem se acumular no Nessie.
Isso degrada performance das listagens do catálogo.

**Listar branches de ingestão pendentes:**
```bash
curl -s http://localhost:19120/api/v2/trees \
  | jq -r '.references[] | select(.name | startswith("ingest_")) | .name'
```

**Deletar em lote (todas as branches de ingestão):**
```bash
source infrastructure/nessie/.venv/bin/activate

# Lista e deleta uma a uma
curl -s http://localhost:19120/api/v2/trees \
  | jq -r '.references[] | select(.name | startswith("ingest_")) | .name' \
  | while read branch; do
      echo "Deletando branch: $branch"
      python airflow/dags/shared/nessie_client.py delete "$branch"
    done
```

> ⚠️ **Atenção:** Não delete branches que ainda estão sendo usadas por execuções ativas do Airflow.
> Verifique no Airflow UI se há DAG Runs em andamento antes de fazer limpeza em lote.

---

## Checklist de validação após correção

Após qualquer correção no `profiles.yml`, `sources.yml` ou `Dockerfile`, execute o gate
manualmente antes de re-triggar o DAG no Airflow:

```bash
# 1. Reconstruir a imagem
docker build -t lakehouse-dbt-validator:latest dbt/branch_validator/

# 2. Identificar uma branch válida (ou criar uma para teste)
source infrastructure/nessie/.venv/bin/activate
python airflow/dags/shared/nessie_client.py create "test-dbt-gate" 
# (use uma branch que tenha dados em bronze.lattes_raw)

# 3. Rodar o gate manualmente
docker run --rm \
  --network mutuca-lakehouse_lakehouse-net \
  -e NESSIE_ICEBERG_ENDPOINT="http://lakehouse-nessie:19120/iceberg/" \
  -e NESSIE_BRANCH="test-dbt-gate" \
  -e MINIO_ENDPOINT="http://lakehouse-minio:9000" \
  -e MINIO_ACCESS_KEY="minioadmin" \
  -e MINIO_SECRET_KEY="minioadmin" \
  lakehouse-dbt-validator:latest \
  dbt test --target branch_validation --select source:bronze

# 4. Limpar a branch de teste
python airflow/dags/shared/nessie_client.py delete "test-dbt-gate"

# 5. Se o gate passou, commitar as mudanças e re-triggar o DAG no Airflow
```
